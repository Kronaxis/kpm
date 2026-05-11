"""Three-way council-level scoreboard: v15.1 vs v17.0 vs v17.1.

v17.1 is v17.0 + tighter NOC overlay (largest party needs ≥60% of
predicted seats, else NOC).

Goal: confirm v17.1 council-level beats v17.0 without underperforming
v15.1 across the 7-council sample.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.ward_data.methodology_v17_ward_uns import predict_council as v17_predict  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_1_council_overlay import predict_council_v17_1  # type: ignore[import-not-found]

WARD_DATA = REPO / 'data' / 'ward_data'
ACTUALS = REPO / 'data' / 'may7_actuals_full.json'
SCORECARD = REPO / 'data' / 'scorecard' / 'kronaxis_scorecard.json'

def slug_to_pretty(slug):
    return slug.replace('-and-', ' and ').replace('-', ' ').title()

def main():
    actuals_full = json.loads(ACTUALS.read_text()).get('council_winners_actual_full', {})
    scorecard = json.loads(SCORECARD.read_text())

    targets = sorted({p.stem.replace('_history','') for p in WARD_DATA.glob('*_history.json')})

    rows = []
    for slug in targets:
        pretty = slug_to_pretty(slug)
        actual = actuals_full.get(pretty)
        v17_0_pred = v17_predict(slug).get('predicted_council_winner', '?')
        v17_1_full = predict_council_v17_1(slug)
        v17_1_pred = v17_1_full.get('predicted_council_winner', '?')
        v17_1_share = v17_1_full.get('largest_party_share', 0)

        v15_1_pred = '?'
        for p in scorecard['predictions']:
            if p.get('subject') == pretty and 'KPM-2.2' in p['methodology']['name']:
                v15_1_pred = p.get('predicted_winner', '?')
                break

        rows.append({
            'council': pretty, 'actual': actual or '?',
            'v15_1': v15_1_pred,
            'v17_0': v17_0_pred,
            'v17_1': v17_1_pred,
            'v17_1_share': v17_1_share,
        })

    print(f"\n=== Council-level: v15.1 vs v17.0 vs v17.1 ===")
    print(f"{'Council':22s}  {'Actual':22s}  {'v15.1':22s}  {'v17.0':22s}  {'v17.1':22s}  {'L%':>5s}")
    print('-' * 130)
    n=0; v151_h=0; v170_h=0; v171_h=0
    for r in rows:
        if r['actual'] == '?': continue
        n += 1
        v151_hit = r['v15_1'] == r['actual']
        v170_hit = r['v17_0'] == r['actual']
        v171_hit = r['v17_1'] == r['actual']
        if v151_hit: v151_h += 1
        if v170_hit: v170_h += 1
        if v171_hit: v171_h += 1
        marks = ('✓' if v151_hit else '✗', '✓' if v170_hit else '✗', '✓' if v171_hit else '✗')
        print(f"  {r['council']:22s}  {r['actual']:22s}  {r['v15_1']:20s} {marks[0]:>2s}  {r['v17_0']:20s} {marks[1]:>2s}  {r['v17_1']:20s} {marks[2]:>2s}  {r['v17_1_share']:>4}%")
    print('-' * 130)
    print(f"  Total scored councils: {n}")
    print(f"  v15.1: {v151_h}/{n} = {round(100*v151_h/n,1) if n else 0}%")
    print(f"  v17.0: {v170_h}/{n} = {round(100*v170_h/n,1) if n else 0}%")
    print(f"  v17.1: {v171_h}/{n} = {round(100*v171_h/n,1) if n else 0}%")
    print()
    print(f"  v17.1 lift vs v17.0: +{v171_h - v170_h} councils ({round(100*(v171_h-v170_h)/n,1)}pp)")

if __name__ == '__main__':
    main()
