"""Sensitivity analysis: how does v17.6 council-level accuracy change as
the Reform-emerging threshold varies?

If 93.3% only holds at threshold = 5% (the current default), the
methodology is overfit. If it holds across 3-10%, it generalises.

Tested thresholds: 0% / 3% / 5% / 7% / 10% / 15% / 20%
At 0%: every council flagged Reform-emerging → very aggressive override.
At 20%: only Hartlepool-class councils flagged.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys
import importlib

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.ward_data._slug_pretty import slug_to_pretty  # type: ignore[import-not-found]

# Import via importlib to satisfy strict resolvers
v17_5_mod = importlib.import_module('scripts.ward_data.methodology_v17_5_council_reform')
v17_6_mod = importlib.import_module('scripts.ward_data.methodology_v17_6_council_override')

WARD = REPO / 'data' / 'ward_data'
ACTUALS = REPO / 'data' / 'may7_actuals_full.json'

def evaluate_at_threshold(threshold_pct: float) -> tuple[int, int, list]:
    """Re-evaluate v17.6 with a different council Reform-emerging threshold."""
    # Monkey-patch the threshold and re-import
    original = v17_5_mod.COUNCIL_REFORM_EMERGENCE_THRESHOLD_PCT
    v17_5_mod.COUNCIL_REFORM_EMERGENCE_THRESHOLD_PCT = threshold_pct  # type: ignore[attr-defined]

    actuals = json.loads(ACTUALS.read_text()).get('council_winners_actual_full', {})
    targets = sorted({p.stem.replace('_history','') for p in WARD.glob('*_history.json')})
    n = 0; hits = 0; flips = []

    for slug in targets:
        pretty = slug_to_pretty(slug)
        actual = actuals.get(pretty)
        if not actual: continue
        n += 1
        v17_6_pred = v17_6_mod.predict_council_v17_6(slug)
        winner = v17_6_pred['predicted_council_winner']
        override = v17_6_pred.get('council_override_applied', False)
        hit = winner == actual
        if hit: hits += 1
        if override:
            flips.append({'council': pretty, 'pred': winner, 'actual': actual, 'hit': hit})

    v17_5_mod.COUNCIL_REFORM_EMERGENCE_THRESHOLD_PCT = original  # type: ignore[attr-defined]
    return hits, n, flips

def main():
    print(f"\n=== v17.6 sensitivity to Reform-emerging threshold ===\n")
    print(f"{'Threshold':>10}  {'Hits':>6}  {'Pct':>7}  {'Override fires':>15}  {'Override hit-rate':>18}")
    print('-' * 80)
    for threshold in [0, 3, 5, 7, 10, 15, 20]:
        hits, n, flips = evaluate_at_threshold(threshold)
        n_flips = len(flips)
        flip_hits = sum(1 for f in flips if f['hit'])
        flip_pct = round(100*flip_hits/n_flips, 1) if n_flips else 0
        pct = round(100*hits/n, 1) if n else 0
        print(f"  {threshold:>5}%   {hits:>2}/{n:<3}  {pct:>6}%  {n_flips:>15}  {flip_hits}/{n_flips} = {flip_pct}%")
    print()
    print(f"Interpretation:")
    print(f"  - Threshold 0%: every council flagged → override fires N times")
    print(f"  - Threshold 100%: no overrides, identical to v17.5")
    print(f"  - Production = 5%. Robustness = stays high at 3-10%.")

if __name__ == '__main__':
    main()
