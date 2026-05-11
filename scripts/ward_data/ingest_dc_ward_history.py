"""Fetch the MOST RECENT prior election result per ward.

For each ward in `data/ward_data/{council}_2026.json`, try ballot IDs at
2024-05-02, 2023-05-04, 2022-05-05 (in that order). Save the most-recent
one with usable result data (>0 votes recorded) to
`data/ward_data/{council}_history.json`.

This is the prerequisite for any v17 ward-aware methodology that wants
to apply UNS at the ward level (rather than v16's LLM-derived speculation).

Schema (per ward):
{
  "ward_slug": ...,
  "ward_name": ...,
  "prior_year": 2024,         # which year had data
  "prior_ballot_id": "local.sheffield.beighton.2024-05-02",
  "prior_winning_party": ...,
  "prior_party_shares": {Labour: 35.2, ...},
  "prior_party_seats_won": {Labour: 1},
  "prior_total_votes": int,
  "prior_winner_count": 1,
  "fetched_at": ISO,
}

Usage:
  python3 -m scripts.ward_data.ingest_dc_ward_history --council birmingham
  python3 -m scripts.ward_data.ingest_dc_ward_history --council birmingham,sheffield,manchester
"""
from __future__ import annotations
import argparse, json, sys, time, urllib.request, urllib.error
from collections import Counter
from pathlib import Path
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parents[2]
WARD_DATA_DIR = REPO / 'data' / 'ward_data'

PRIOR_DATES = ['2024-05-02', '2023-05-04', '2022-05-05']
DC_BASE = "https://candidates.democracyclub.org.uk/api/next/ballots/{ballot_id}.json"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
SLEEP_SEC = 1.5
MAX_RETRIES = 3
RETRY_BACKOFF_SEC = 8

DC_PARTY_NORMALISE = {
    'Labour Party': 'Labour',
    'Labour and Co-operative Party': 'Labour',
    'Conservative and Unionist Party': 'Conservative',
    'Liberal Democrats': 'Liberal Democrat',
    'Reform UK': 'Reform UK',
    'Brexit Party': 'Reform UK',  # 2019 only — included for completeness
    'Green Party': 'Green',
    'Scottish Green Party': 'Green',
    'Wales Green Party': 'Green',
    'Plaid Cymru - The Party of Wales': 'Plaid Cymru',
    'Scottish National Party (SNP)': 'Scottish National Party',
    'Workers Party of Britain': 'Workers Party of Britain',
    'Trade Unionist and Socialist Coalition': 'TUSC',
    'Independent': 'Independent',
}

def cn(party: str) -> str:
    if not party: return 'Unknown'
    return DC_PARTY_NORMALISE.get(party.strip(), party.strip())

def fetch_ballot(ballot_id: str) -> dict | None:
    url = DC_BASE.format(ballot_id=ballot_id)
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code == 429 and attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF_SEC * (attempt + 1))
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

def normalise_prior(ballot: dict, ward_meta: dict, prior_year: int) -> dict | None:
    """Convert DC ballot JSON → our canonical prior result. Returns None if no votes."""
    cands = ballot.get('candidacies', [])
    if not cands: return None

    party_votes: Counter = Counter()
    party_seats: Counter = Counter()
    total_votes = 0

    for c in cands:
        party = cn(c.get('party_name') or c.get('party', {}).get('name', '?'))
        result = c.get('result') or {}
        votes = result.get('num_ballots') or 0
        is_elected = bool(result.get('elected'))
        if is_elected:
            party_seats[party] += 1
        if isinstance(votes, int):
            party_votes[party] += votes
            total_votes += votes

    if total_votes == 0:
        return None  # ballot exists but no result data

    party_shares = {p: round(100*v/total_votes, 2) for p, v in party_votes.items()}

    if party_seats:
        winning_party = max(party_seats.items(), key=lambda kv: (kv[1], party_votes.get(kv[0], 0)))[0]
    elif party_votes:
        winning_party = max(party_votes.items(), key=lambda kv: kv[1])[0]
    else:
        winning_party = None

    return {
        'ward_slug': ward_meta['ward_slug'],
        'ward_name': ward_meta['ward_name'],
        'prior_year': prior_year,
        'prior_ballot_id': ballot.get('ballot_paper_id'),
        'prior_winning_party': winning_party,
        'prior_party_shares': party_shares,
        'prior_party_seats_won': dict(party_seats),
        'prior_total_votes': total_votes,
        'prior_winner_count': ballot.get('winner_count', 1),
    }

def fetch_ward_history(council_slug: str, ward_meta: dict) -> dict | None:
    """Try each prior date, return first one with usable data."""
    for date in PRIOR_DATES:
        prior_ballot_id = f"local.{council_slug}.{ward_meta['ward_slug']}.{date}"
        ballot = fetch_ballot(prior_ballot_id)
        time.sleep(SLEEP_SEC)
        if not ballot:
            continue
        norm = normalise_prior(ballot, ward_meta, prior_year=int(date[:4]))
        if norm:
            return norm
    return None

def ingest_council_history(council_slug: str) -> dict:
    current_path = WARD_DATA_DIR / f"{council_slug}_2026.json"
    if not current_path.exists():
        print(f"[skip] {council_slug}: no 2026 data; run ingest_dc_ward_results first")
        return {}
    current = json.loads(current_path.read_text())
    out = {
        'council_slug': council_slug,
        'source': 'https://candidates.democracyclub.org.uk/api/next/',
        'fetched_at': datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z'),
        'wards': [],
        'n_wards_attempted': len(current['wards']),
        'n_wards_with_history': 0,
        'n_wards_no_history': 0,
        'prior_year_distribution': {},
    }
    year_counter: Counter = Counter()
    for w in current['wards']:
        history = fetch_ward_history(council_slug, w)
        if not history:
            out['n_wards_no_history'] += 1
            continue
        out['wards'].append(history)
        out['n_wards_with_history'] += 1
        year_counter[history['prior_year']] += 1
    out['prior_year_distribution'] = dict(year_counter)
    return out

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--council', required=True, help='Council slug(s), comma-separated')
    args = ap.parse_args()

    targets = args.council.split(',')
    summary = []
    for slug in targets:
        print(f"[history] {slug}: fetching prior ballots for each 2026 ward")
        result = ingest_council_history(slug)
        if not result: continue
        out_path = WARD_DATA_DIR / f"{slug}_history.json"
        out_path.write_text(json.dumps(result, indent=2))
        print(f"  wrote {out_path}: {result['n_wards_with_history']}/{result['n_wards_attempted']} wards have prior data")
        print(f"  Year distribution: {result['prior_year_distribution']}")
        summary.append(result)

    print(f"\nDone. Total wards with history: {sum(s['n_wards_with_history'] for s in summary)}")

if __name__ == '__main__':
    main()
