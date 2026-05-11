"""Confidence calibration of v17 ward predictions.

A well-calibrated methodology should hit Confident predictions much
more often than Toss-up predictions. If v17's "Confident" wards score
the same as "Toss-up" wards, the confidence label is meaningless.

For each ward in current sample:
  - Take v17 prediction + confidence (Confident / Lean / Toss-up)
  - Compare to actual winner
  - Bucket by confidence + report hit rate per bucket

Usage:
  python3 -m scripts.ward_data.calibration_v17
"""
from __future__ import annotations
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.ward_data.methodology_v17_ward_uns import predict_ward  # type: ignore[import-not-found]

WARD_DIR = REPO / 'data' / 'ward_data'

def party_norm(p): return 'Liberal Democrat' if p == 'Liberal Democrats' else p

def main():
    buckets: dict = {'Confident': {'n': 0, 'hits': 0}, 'Lean': {'n': 0, 'hits': 0},
                     'Toss-up': {'n': 0, 'hits': 0}, 'NoData': {'n': 0, 'hits': 0}}
    for actual_path in WARD_DIR.glob('*_2026.json'):
        slug = actual_path.stem.replace('_2026', '')
        history_path = WARD_DIR / f'{slug}_history.json'
        if not history_path.exists():
            continue
        actual = json.loads(actual_path.read_text())
        history = json.loads(history_path.read_text())
        history_by_slug = {w['ward_slug']: w for w in history['wards']}
        for w in actual['wards']:
            h = history_by_slug.get(w['ward_slug'])
            if not h: continue
            pred = predict_ward(h)
            actual_winner = party_norm(w.get('winning_party') or '?')
            if actual_winner == '?': continue
            v17_winner = party_norm(pred.predicted_winner)
            bucket = pred.confidence
            if bucket not in buckets: buckets[bucket] = {'n': 0, 'hits': 0}
            buckets[bucket]['n'] += 1
            if v17_winner == actual_winner:
                buckets[bucket]['hits'] += 1

    print("\n=== v17 confidence calibration ===")
    print(f"{'Bucket':12s}  {'n':>5s}  {'hits':>5s}  {'pct':>7s}")
    print('-' * 40)
    total_n = 0; total_h = 0
    for b in ['Confident', 'Lean', 'Toss-up', 'NoData']:
        v = buckets.get(b, {'n': 0, 'hits': 0})
        if v['n'] == 0: continue
        pct = round(100*v['hits']/v['n'], 1)
        total_n += v['n']; total_h += v['hits']
        print(f"  {b:12s}  {v['n']:>5d}  {v['hits']:>5d}  {pct:>6}%")
    print('-' * 40)
    if total_n:
        print(f"  {'OVERALL':12s}  {total_n:>5d}  {total_h:>5d}  {round(100*total_h/total_n,1):>6}%")
    print()
    # Calibration signal: confident should be ≥ lean ≥ toss-up
    conf_pct = (buckets['Confident']['hits']/buckets['Confident']['n']*100) if buckets['Confident']['n'] else 0
    toss_pct = (buckets['Toss-up']['hits']/buckets['Toss-up']['n']*100) if buckets['Toss-up']['n'] else 0
    if conf_pct > toss_pct + 10:
        print(f"  Calibration: GOOD — Confident ({conf_pct:.1f}%) significantly beats Toss-up ({toss_pct:.1f}%)")
    elif conf_pct > toss_pct:
        print(f"  Calibration: WEAK — Confident ({conf_pct:.1f}%) only slightly beats Toss-up ({toss_pct:.1f}%)")
    else:
        print(f"  Calibration: BROKEN — Confident ({conf_pct:.1f}%) does NOT beat Toss-up ({toss_pct:.1f}%). Confidence label is meaningless.")

if __name__ == '__main__':
    main()
