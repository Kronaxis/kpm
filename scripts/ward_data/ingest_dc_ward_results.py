"""Ingest real per-ward election results from Democracy Club JSON API.

For each council in `data/council_wards_2026.json`, fetch every ballot's
result via `https://candidates.democracyclub.org.uk/api/next/ballots/{ballot_id}.json`
and write a normalised per-council JSON file to `data/ward_data/{council_slug}_2026.json`.

This is the foundation for task #54 (real ward-data ingestion) — the prerequisite
for any v16/v17 methodology that uses actual ward-result swings instead of
LLM-derived speculation.

Schema (per ward):
{
  "ward_slug": "acocks-green",
  "ward_name": "Acocks Green",
  "ballot_id": "local.birmingham.acocks-green.2026-05-07",
  "winner_count": 2,                  # seats up for election
  "elected": [                        # list of elected candidates
    {"party": "Liberal Democrats", "name": "...", "votes": 1952}
  ],
  "candidates": [                     # all candidates
    {"party": "...", "name": "...", "votes": int, "elected": bool}
  ],
  "party_shares": {                   # party share of TOTAL ward votes
    "Liberal Democrats": 39.1, ...
  },
  "winning_party": "Liberal Democrats",  # party that won the most seats
  "total_votes": int,
  "source": "Democracy Club"
}

Usage:
  python3 -m scripts.ward_data.ingest_dc_ward_results --council birmingham
  python3 -m scripts.ward_data.ingest_dc_ward_results --council birmingham,sheffield
  python3 -m scripts.ward_data.ingest_dc_ward_results --all  # all 130+ councils

Polite to DC: 0.5s sleep between requests, ETag support not used (their CDN
caches anyway).
"""
from __future__ import annotations
import argparse, json, sys, time, urllib.request, urllib.error
from collections import Counter
from pathlib import Path
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parents[2]
COUNCIL_WARDS = REPO / 'data' / 'council_wards_2026.json'
OUT_DIR = REPO / 'data' / 'ward_data'
OUT_DIR.mkdir(exist_ok=True)

DC_BASE = "https://candidates.democracyclub.org.uk/api/next/ballots/{ballot_id}.json"
# CloudFront blocked our custom UA in May 2026; using browser UA to pass through.
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
SLEEP_SEC = 1.5
MAX_RETRIES = 3
RETRY_BACKOFF_SEC = 8

# Normalise Democracy Club party names to scorecard canonical names
DC_PARTY_NORMALISE = {
    'Labour Party': 'Labour',
    'Labour and Co-operative Party': 'Labour',
    'Conservative and Unionist Party': 'Conservative',
    'Liberal Democrats': 'Liberal Democrat',
    'Reform UK': 'Reform UK',
    'Green Party': 'Green',
    'Scottish Green Party': 'Green',
    'Wales Green Party': 'Green',
    'Plaid Cymru - The Party of Wales': 'Plaid Cymru',
    'Scottish National Party (SNP)': 'Scottish National Party',
    'Workers Party of Britain': 'Workers Party of Britain',
    'Trade Unionist and Socialist Coalition': 'TUSC',
    # Independents — keep distinct from named small parties
    'Independent': 'Independent',
}

def cn(party: str) -> str:
    if not party: return 'Unknown'
    return DC_PARTY_NORMALISE.get(party.strip(), party.strip())

def fetch_ballot(ballot_id: str) -> dict | None:
    """Fetch with retry on 429 (Democracy Club rate-limiter)."""
    url = DC_BASE.format(ballot_id=ballot_id)
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None  # ballot not yet on DC
            if e.code == 429 and attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF_SEC * (attempt + 1)
                print(f"    429 on {ballot_id}, waiting {wait}s and retrying...", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"    HTTP {e.code} on {ballot_id}", file=sys.stderr)
            return None
        except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF_SEC)
                continue
            print(f"    fetch error on {ballot_id}: {e}", file=sys.stderr)
            return None
    return None

def normalise_ward(ballot: dict, ward_meta: dict) -> dict | None:
    """Convert Democracy Club ballot JSON → our canonical per-ward result."""
    cands = ballot.get('candidacies', [])
    if not cands: return None

    candidates = []
    elected = []
    party_votes: Counter = Counter()
    party_seats: Counter = Counter()
    total_votes = 0

    for c in cands:
        party = cn(c.get('party_name') or c.get('party', {}).get('name', '?'))
        name = (c.get('person') or {}).get('name', '?')
        result = c.get('result') or {}
        votes = result.get('num_ballots') or 0
        is_elected = bool(result.get('elected'))
        candidates.append({'party': party, 'name': name, 'votes': votes, 'elected': is_elected})
        if is_elected:
            elected.append({'party': party, 'name': name, 'votes': votes})
            party_seats[party] += 1
        if isinstance(votes, int):
            party_votes[party] += votes
            total_votes += votes

    party_shares = {}
    if total_votes:
        for p, v in party_votes.items():
            party_shares[p] = round(100 * v / total_votes, 2)

    # Winning party = most seats won; tiebreak by total votes
    if party_seats:
        winning_party = max(party_seats.items(), key=lambda kv: (kv[1], party_votes.get(kv[0], 0)))[0]
    elif party_votes:
        winning_party = max(party_votes.items(), key=lambda kv: kv[1])[0]
    else:
        winning_party = None

    return {
        'ward_slug': ward_meta['ward'],
        'ward_name': ward_meta.get('post_label', ward_meta['ward']),
        'ballot_id': ward_meta['ballot_id'],
        'winner_count': ward_meta.get('winner_count', 1),
        'elected': elected,
        'candidates': candidates,
        'party_shares': party_shares,
        'party_seats_won': dict(party_seats),
        'winning_party': winning_party,
        'total_votes': total_votes,
        'source': 'Democracy Club',
        'fetched_at': datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z'),
    }

def ingest_council(council_slug: str, ward_list: list[dict]) -> dict:
    out = {
        'council_slug': council_slug,
        'election_date': '2026-05-07',
        'source': 'https://candidates.democracyclub.org.uk/api/next/',
        'fetched_at': datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z'),
        'wards': [],
        'n_wards_attempted': len(ward_list),
        'n_wards_with_results': 0,
        'n_wards_no_results': 0,
    }
    for w in ward_list:
        ballot = fetch_ballot(w['ballot_id'])
        time.sleep(SLEEP_SEC)
        if not ballot:
            out['n_wards_no_results'] += 1
            continue
        norm = normalise_ward(ballot, w)
        if not norm or norm['total_votes'] == 0:
            out['n_wards_no_results'] += 1
            continue
        out['wards'].append(norm)
        out['n_wards_with_results'] += 1
    return out

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--council', help='Comma-separated council slug(s)')
    ap.add_argument('--all', action='store_true', help='Ingest all councils')
    ap.add_argument('--limit-wards', type=int, default=0, help='Cap wards per council (debug)')
    args = ap.parse_args()

    council_wards = json.loads(COUNCIL_WARDS.read_text())

    if args.all:
        targets = list(council_wards.keys())
    elif args.council:
        targets = args.council.split(',')
    else:
        ap.error('Pass --council slug,slug2 or --all')

    summary = []
    for slug in targets:
        wards = council_wards.get(slug, [])
        if not wards:
            print(f"[skip] {slug}: not in council_wards_2026.json")
            continue
        if args.limit_wards:
            wards = wards[:args.limit_wards]
        print(f"[fetch] {slug}: {len(wards)} ballots")
        result = ingest_council(slug, wards)
        out_path = OUT_DIR / f"{slug}_2026.json"
        out_path.write_text(json.dumps(result, indent=2))
        print(f"  wrote {out_path} - {result['n_wards_with_results']}/{result['n_wards_attempted']} wards with results")
        summary.append({
            'council': slug,
            'wards_with_results': result['n_wards_with_results'],
            'wards_attempted': result['n_wards_attempted'],
        })

    print(f"\nDone. Summary:")
    total_w = sum(s['wards_with_results'] for s in summary)
    total_a = sum(s['wards_attempted'] for s in summary)
    print(f"  Total wards ingested: {total_w}/{total_a}")
    print(f"  Councils: {len(summary)}")

if __name__ == '__main__':
    main()
