"""Aggregate v17 ward predictions to council-level winner + compare vs v15.1
council-level prediction + actual.

Three-way comparison per council:
  - v15.1 (existing council-level methodology)
  - v17 (aggregated from per-ward predictions)
  - Actual May 7 2026 result

The interesting cell: when v17 disagrees with v15.1, who wins?

Usage:
  python3 -m scripts.ward_data.score_v17_council_level
"""
from __future__ import annotations
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.ward_data.methodology_v17_ward_uns import predict_council  # type: ignore[import-not-found]

WARD_DATA = REPO / 'data' / 'ward_data'
ACTUALS = REPO / 'data' / 'may7_actuals_full.json'
SCORECARD = REPO / 'data' / 'scorecard' / 'kronaxis_scorecard.json'

# Councils for which we have ward history
def get_councils_with_history() -> list[str]:
    return sorted({p.stem.replace('_history','') for p in WARD_DATA.glob('*_history.json')})

def slug_to_pretty(slug: str) -> str:
    return slug.replace('-and-', ' and ').replace('-', ' ').title()

def load_actual(council_pretty: str, actuals: dict) -> str | None:
    full = actuals.get('council_winners_actual_full', {})
    return full.get(council_pretty)

def load_v151(council_pretty: str, scorecard: dict) -> dict | None:
    for p in scorecard['predictions']:
        if (p.get('subject') == council_pretty
                and 'KPM-2.2' in p['methodology']['name']):
            return {
                'predicted': p.get('predicted_winner'),
                'actual': p.get('actual_winner'),
                'hit': p.get('hit'),
            }
    return None

def main():
    actuals = json.loads(ACTUALS.read_text())
    scorecard = json.loads(SCORECARD.read_text())

    rows = []
    for slug in get_councils_with_history():
        pretty = slug_to_pretty(slug)
        actual = load_actual(pretty, actuals)
        v151 = load_v151(pretty, scorecard)

        v17 = predict_council(slug)
        if v17.get('error'):
            continue

        v17_winner = v17['predicted_council_winner']
        v17_hit = (v17_winner == actual) if actual else None

        rows.append({
            'council': pretty,
            'slug': slug,
            'actual': actual or '?',
            'v151_predicted': v151['predicted'] if v151 else '?',
            'v151_hit': v151['hit'] if v151 else None,
            'v17_predicted': v17_winner,
            'v17_hit': v17_hit,
            'v17_seat_counts': v17['seat_counts'],
            'v17_total_seats_predicted': v17['total_seats_predicted'],
        })

    print(f"\n=== Council-level: v17 (ward-aggregated) vs v15.1 vs actual ===")
    print(f"{'Council':22s}  {'Actual':22s}  {'v15.1 pred':22s}  {'v17 pred':22s}  {'v15.1':>6}  {'v17':>6}")
    print('-' * 110)
    n = 0; v151_hits = 0; v17_hits = 0; agree_count = 0
    for r in rows:
        n += 1
        if r['v151_hit']: v151_hits += 1
        if r['v17_hit']: v17_hits += 1
        if r['v151_predicted'] == r['v17_predicted']: agree_count += 1
        v151_mark = '✓' if r['v151_hit'] else '✗'
        v17_mark = '✓' if r['v17_hit'] else '✗' if r['v17_hit'] is False else '?'
        print(f"  {r['council']:22s}  {r['actual']:22s}  {r['v151_predicted']:22s}  {r['v17_predicted']:22s}  {v151_mark:>6}  {v17_mark:>6}")
    print('-' * 110)
    if n:
        print(f"  Total: {n} councils")
        print(f"  v15.1: {v151_hits}/{n} = {round(100*v151_hits/n,1)}%")
        print(f"  v17:   {v17_hits}/{n} = {round(100*v17_hits/n,1)}%")
        print(f"  Agreement v15.1 == v17: {agree_count}/{n}")
    print()
    print("Per-council v17 seat-count details:")
    for r in rows:
        print(f"  {r['council']:22s} v17 seats: {r['v17_seat_counts']} (total predicted: {r['v17_total_seats_predicted']})")

if __name__ == '__main__':
    main()
