"""Per-party recall + precision analysis for v17.

For each party that won wards in 2026:
  - How many actual ward wins did this party get? (n_actual)
  - How many of those did v17 predict correctly? (n_correctly_predicted)
  - Recall = correctly predicted / actual wins
  - How often does v17 predict this party? (n_predicted_total)
  - How often is v17 right when it predicts this party? (precision)

A high-recall low-precision party = v17 over-predicts it (false positives)
A low-recall high-precision party = v17 under-predicts it (false negatives)

Pattern matters for v17.1: which parties does the methodology systematically
miss vs over-predict?
"""
from __future__ import annotations
import json
from pathlib import Path
import sys
from collections import defaultdict

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.ward_data.methodology_v17_ward_uns import predict_ward  # type: ignore[import-not-found]

WARD_DIR = REPO / 'data' / 'ward_data'

def party_norm(p): return 'Liberal Democrat' if p == 'Liberal Democrats' else p

def main():
    # confusion[(actual, predicted)] = count
    confusion: dict = defaultdict(int)
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
            v17_winner = party_norm(pred.predicted_winner)
            if actual_winner == '?' or v17_winner == 'Unknown': continue
            confusion[(actual_winner, v17_winner)] += 1

    parties = sorted({p for k in confusion for p in k})
    print(f"\n=== v17 per-party recall + precision ===")
    print(f"{'Party':22s}  {'n_actual':>10s}  {'n_predicted':>12s}  {'correct':>8s}  {'recall':>7s}  {'precision':>10s}")
    print('-' * 80)
    overall_correct = 0; overall_n = 0
    for p in parties:
        n_actual = sum(c for (a, _), c in confusion.items() if a == p)
        n_predicted = sum(c for (_, pp), c in confusion.items() if pp == p)
        correct = confusion.get((p, p), 0)
        recall = round(100*correct/n_actual, 1) if n_actual else 0
        precision = round(100*correct/n_predicted, 1) if n_predicted else 0
        overall_correct += correct; overall_n += n_actual
        marker = ''
        if n_actual > 0 and recall == 0:
            marker = '  ← v17 NEVER predicts this party correctly'
        elif n_actual >= 5 and recall < 20:
            marker = '  ← v17 systematically misses'
        elif n_predicted >= 10 and precision < 30:
            marker = '  ← v17 over-predicts (false positives)'
        print(f"  {p:22s}  {n_actual:>10d}  {n_predicted:>12d}  {correct:>8d}  {recall:>6}%  {precision:>9}%{marker}")
    print('-' * 80)
    print(f"  Overall: {overall_correct}/{overall_n} = {round(100*overall_correct/overall_n,1) if overall_n else 0}%")
    print()
    print("Confusion matrix (rows=actual, cols=v17 predicted):")
    print(f"{'':22s}  " + ''.join(f'{p[:10]:>11}' for p in parties))
    for actual in parties:
        row = []
        for pred in parties:
            c = confusion.get((actual, pred), 0)
            row.append(f'{c:>11d}' if c else '          .')
        print(f"  {actual:22s}  " + ''.join(row))

if __name__ == '__main__':
    main()
