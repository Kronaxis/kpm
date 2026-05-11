"""Ingest per-ward council election results from Wikipedia.

This is the fallback when Democracy Club API is unavailable or has gaps.
Uses WebFetch (via subprocess) to ask an LLM to parse the page tables.

Workflow:
  1. Run this script manually with a Wikipedia URL
  2. It outputs JSON in our standard ward_data format
  3. Save to data/ward_data/{council_slug}_{year}_wikipedia.json
  4. Use scripts to merge into _2026.json or _history.json

NOTE: This is a SCAFFOLDING script. Wikipedia HTML parsing is fragile.
Each page needs human review. The actual fetch+parse is done interactively
via Claude Code's WebFetch tool, then output saved here.

Manual workflow:
  $ claude  # interactive
  > WebFetch the URL
  > Extract ward results
  > Save to /home/jason/projects/kronaxis/data/ward_data/{slug}_{year}_wikipedia.json
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parents[2]
WARD = REPO / 'data' / 'ward_data'

# Party normalisation (Wikipedia uses different conventions than DC)
WIKI_PARTY_NORMALISE = {
    'Labour': 'Labour',
    'Labour Co-op': 'Labour',
    'Labour and Co-operative Party': 'Labour',
    'Conservative': 'Conservative',
    'Conservatives': 'Conservative',
    'Conservative and Unionist Party': 'Conservative',
    'Liberal Democrats': 'Liberal Democrat',
    'Liberal Democrat': 'Liberal Democrat',
    'Lib Dem': 'Liberal Democrat',
    'Lib Dems': 'Liberal Democrat',
    'Reform UK': 'Reform UK',
    'Reform': 'Reform UK',
    'Green': 'Green',
    'Green Party': 'Green',
    'Independent': 'Independent',
    'Workers Party of Britain': 'Workers Party of Britain',
}

def normalise_party(p: str) -> str:
    return WIKI_PARTY_NORMALISE.get(p.strip(), p.strip())

def convert_wikipedia_to_ward_data(wikipedia_json: dict, council_slug: str,
                                    election_date: str, target: str = 'current') -> dict:
    """Convert Wikipedia-style ward data to our standard schema.

    target: 'current' for 2026-style output (matches _2026.json)
            'history' for prior-election style (matches _history.json)
    """
    wards_out = []
    for w in wikipedia_json.get('wards', []):
        name = w.get('name', '?')
        # Build party_shares
        candidates = w.get('candidates', [])
        if not candidates and w.get('results'):
            # Alternative key
            candidates = w['results']

        total_votes = sum(c.get('votes', 0) for c in candidates)
        if total_votes == 0:
            continue

        party_votes = {}
        for c in candidates:
            party = normalise_party(c.get('party', '?'))
            votes = c.get('votes', 0)
            party_votes[party] = party_votes.get(party, 0) + votes

        party_shares = {k: round(100*v/total_votes, 2) for k, v in party_votes.items()}

        # Determine winner
        winner = w.get('winner') or w.get('winning_party')
        if winner:
            winner = normalise_party(winner)
        else:
            # Infer from largest vote share
            winner = max(party_shares.items(), key=lambda kv: kv[1])[0]

        if target == 'current':
            wards_out.append({
                'ward_slug': name.lower().replace(' ', '-').replace('&', 'and'),
                'ward_name': name,
                'ballot_id': f'wikipedia.{council_slug}.{name.lower().replace(" ","-")}.{election_date}',
                'winner_count': 1,  # Assume single-member; some wards multi-member, manual fix needed
                'elected': [],  # Wikipedia doesn't always have candidate-level data
                'candidates': candidates,
                'party_shares': party_shares,
                'party_seats_won': {winner: 1},
                'winning_party': winner,
                'total_votes': total_votes,
                'source': 'Wikipedia (manual extraction)',
                'fetched_at': datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z'),
            })
        else:  # history
            wards_out.append({
                'ward_slug': name.lower().replace(' ', '-').replace('&', 'and'),
                'ward_name': name,
                'prior_year': int(election_date[:4]),
                'prior_ballot_id': f'wikipedia.{council_slug}.{name.lower().replace(" ","-")}.{election_date}',
                'prior_winning_party': winner,
                'prior_party_shares': party_shares,
                'prior_party_seats_won': {winner: 1},
                'prior_total_votes': total_votes,
                'prior_winner_count': 1,
            })

    return {
        'council_slug': council_slug,
        'source': 'Wikipedia',
        'election_date': election_date,
        'fetched_at': datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z'),
        'wards': wards_out,
        'n_wards_with_results': len(wards_out),
        'n_wards_attempted': len(wikipedia_json.get('wards', [])),
    }

def merge_into_history(council_slug: str, wiki_history: dict) -> dict:
    """Merge Wikipedia history wards INTO existing DC history file
    (DC entries win on conflict, Wikipedia fills gaps)."""
    existing_path = WARD / f'{council_slug}_history.json'
    if existing_path.exists():
        existing = json.loads(existing_path.read_text())
        existing_slugs = {w['ward_slug'] for w in existing['wards']}
        added = 0
        for w in wiki_history['wards']:
            if w['ward_slug'] not in existing_slugs:
                existing['wards'].append(w)
                added += 1
        existing['merged_wikipedia_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
        existing['n_wikipedia_wards_added'] = added
        existing_path.write_text(json.dumps(existing, indent=2))
        return {'existing': len(existing['wards']) - added, 'wikipedia_added': added,
                'total': len(existing['wards'])}
    else:
        existing_path.write_text(json.dumps(wiki_history, indent=2))
        return {'existing': 0, 'wikipedia_added': len(wiki_history['wards']),
                'total': len(wiki_history['wards'])}

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--json-file', required=True, help='Path to Wikipedia-extracted JSON')
    ap.add_argument('--council', required=True, help='Council slug')
    ap.add_argument('--date', required=True, help='Election date YYYY-MM-DD')
    ap.add_argument('--target', choices=['current','history'], default='history')
    ap.add_argument('--merge', action='store_true', help='Merge into existing _history.json')
    args = ap.parse_args()

    wiki_json = json.loads(Path(args.json_file).read_text())
    converted = convert_wikipedia_to_ward_data(wiki_json, args.council, args.date, args.target)

    if args.target == 'history' and args.merge:
        result = merge_into_history(args.council, converted)
        print(f"Merged: {result}")
    else:
        out_path = WARD / f'{args.council}_{args.target}_wikipedia.json'
        out_path.write_text(json.dumps(converted, indent=2))
        print(f"Wrote {out_path}")
        print(f"  {converted['n_wards_with_results']} wards converted from Wikipedia")
