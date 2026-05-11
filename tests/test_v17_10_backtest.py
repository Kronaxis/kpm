"""Reproduce the KPM-v17.10 ensemble methodology on its n=40 sample.

Anyone can run this to verify the published v17.10 numbers independently:

    python3 -m tests.test_v17_10_backtest

Expected output:
    KPM-v17.10 ensemble: 29/40 = 72.5%
    KPM-2.2 v15.1:        29/40 = 72.5%
    Difference:           +0.0pp (tied at n=40)
    Methodology hash:     2ea86b8d1e25ee68ebf66c6f59496e2480a43dba2a81ff17012ce0094531f018
"""
from __future__ import annotations
import json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.ward_data.methodology_v17_10_ensemble import (
    predict_council_v17_10, methodology_hash
)
from scripts.ward_data._slug_pretty import slug_to_pretty

EXPECTED_HASH = "2ea86b8d1e25ee68ebf66c6f59496e2480a43dba2a81ff17012ce0094531f018"
EXPECTED_V17_10_PCT = 72.5
EXPECTED_V15_1_PCT = 72.5
TOLERANCE_PP = 1.0

WARD = REPO / 'data' / 'ward_data'

def main():
    # Load 2026 actuals from the scorecard (canonical source)
    scorecard = json.loads((REPO / 'data' / 'scorecard' / 'kronaxis_scorecard.json').read_text())

    actuals_map = {}
    for p in scorecard['predictions']:
        if 'KPM-2.2' in p['methodology']['name']:
            subj = p.get('subject')
            actual = p.get('actual_winner')
            if subj and actual: actuals_map[subj] = actual

    # Find councils with both pre-2024 wards (real history) and v17.10 applicable
    councils = sorted({p.stem.replace('_history','') for p in WARD.glob('*_history.json')})
    real_councils = []
    for slug in councils:
        h = json.loads((WARD / f'{slug}_history.json').read_text())
        if h.get('n_wards_with_history', 0) > 0:
            real_councils.append(slug)

    v17_hits = 0; v15_hits = 0; total = 0
    for slug in real_councils:
        pretty = slug_to_pretty(slug)
        actual = actuals_map.get(pretty)
        if not actual: continue
        p = predict_council_v17_10(slug)
        if 'error' in p: continue
        v17 = p['predicted_council_winner']
        v15 = p['v15_1_winner']
        if v17 == actual: v17_hits += 1
        if v15 == actual: v15_hits += 1
        total += 1

    pct_v17 = round(100 * v17_hits / total, 1)
    pct_v15 = round(100 * v15_hits / total, 1)

    print(f"KPM-v17.10 ensemble: {v17_hits}/{total} = {pct_v17}%")
    print(f"KPM-2.2 v15.1:        {v15_hits}/{total} = {pct_v15}%")
    print(f"Difference:           {pct_v17 - pct_v15:+.1f}pp")
    print(f"Methodology hash:     {methodology_hash()}")

    # Assertions
    assert methodology_hash() == EXPECTED_HASH, \
        f"v17.10 hash mismatch! Got {methodology_hash()}, expected {EXPECTED_HASH}"
    assert abs(pct_v17 - EXPECTED_V17_10_PCT) <= TOLERANCE_PP, \
        f"v17.10 drifted: {pct_v17} vs expected {EXPECTED_V17_10_PCT}"
    assert abs(pct_v15 - EXPECTED_V15_1_PCT) <= TOLERANCE_PP, \
        f"v15.1 drifted: {pct_v15} vs expected {EXPECTED_V15_1_PCT}"

    print("\n✓ v17.10 methodology reproduces published n=40 tied result.")

if __name__ == '__main__':
    main()
