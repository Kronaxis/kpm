"""Score v17.2 (Reform-weighted UNS) per-ward against actuals."""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.ward_data.methodology_v17_2_reform_weighted import predict_ward_v17_2  # type: ignore[import-not-found]

WARD_DIR = REPO / 'data' / 'ward_data'

def party_norm(p): return 'Liberal Democrat' if p == 'Liberal Democrats' else p

def main():
    confusion: dict = defaultdict(int)
    per_council: dict = defaultdict(lambda: {'n': 0, 'hits': 0})
    for actual_path in WARD_DIR.glob('*_2026.json'):
        slug = actual_path.stem.replace('_2026', '')
        history_path = WARD_DIR / f'{slug}_history.json'
        if not history_path.exists(): continue
        actual = json.loads(actual_path.read_text())
        history = json.loads(history_path.read_text())
        history_by_slug = {w['ward_slug']: w for w in history['wards']}
        for w in actual['wards']:
            h = history_by_slug.get(w['ward_slug'])
            if not h: continue
            pred = predict_ward_v17_2(h)
            actual_winner = party_norm(w.get('winning_party') or '?')
            v17_2_winner = party_norm(pred.predicted_winner)
            if actual_winner == '?' or v17_2_winner == 'Unknown': continue
            confusion[(actual_winner, v17_2_winner)] += 1
            per_council[slug]['n'] += 1
            if actual_winner == v17_2_winner: per_council[slug]['hits'] += 1

    print(f"\n=== v17.2 per-ward accuracy ===")
    print(f"{'Council':24s}  {'n':>6s}  {'v17.2':>8s}")
    print('-' * 50)
    total_n = 0; total_hits = 0
    for slug, v in sorted(per_council.items()):
        pct = round(100*v['hits']/v['n'], 1) if v['n'] else 0
        print(f"  {slug:24s}  {v['n']:>6d}  {pct:>7}%")
        total_n += v['n']; total_hits += v['hits']
    print('-' * 50)
    print(f"  {'OVERALL':24s}  {total_n:>6d}  {round(100*total_hits/total_n,1):>7}%")

    # Per-party recall
    print(f"\n=== v17.2 per-party recall ===")
    parties = sorted({p for k in confusion for p in k})
    print(f"{'Party':22s}  {'actual':>8s}  {'predicted':>10s}  {'correct':>8s}  {'recall':>7s}")
    print('-' * 60)
    for p in parties:
        n_actual = sum(c for (a, _), c in confusion.items() if a == p)
        n_pred = sum(c for (_, pp), c in confusion.items() if pp == p)
        correct = confusion.get((p, p), 0)
        recall = round(100*correct/n_actual, 1) if n_actual else 0
        marker = '  ← v17.2 still 0' if n_actual >= 3 and recall == 0 else ''
        print(f"  {p:22s}  {n_actual:>8d}  {n_pred:>10d}  {correct:>8d}  {recall:>6}%{marker}")

if __name__ == '__main__':
    main()
