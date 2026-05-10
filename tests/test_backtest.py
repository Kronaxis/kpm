"""Reproduce the headline KPM-2.2 v15.1 number on the broader 130-council sample.

Anyone can run this to verify the 59.2% figure independently:

    python3 -m tests.test_backtest

Expected output:
    KPM-1 baseline:    37/130 = 28.5%
    KPM-2.2 v15.1:     77/130 = 59.2%
    Lift:              +30.7pp absolute
    Methodology hash:  52df676e792c29c6c893382a5c390c9b9790663e6e7e0a9c7edb1a54ac6c0741
"""
from __future__ import annotations
import json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.kpm2.classify import apply_fragmentation_override, Classification
from scripts.kpm2.rules import fragmentation_hash

EXPECTED_HASH = "52df676e792c29c6c893382a5c390c9b9790663e6e7e0a9c7edb1a54ac6c0741"
EXPECTED_KPM1_PCT = 28.5
EXPECTED_V151_PCT = 59.2
TOLERANCE_PP = 0.5

def main():
    ds = json.loads((REPO / 'scripts' / 'llm_test' / 'dataset.json').read_text())
    all_rec = ds['train'] + ds['holdout']

    # KPM-1 baseline
    h_kpm1 = sum(1 for r in all_rec if r['kpm1_predicted'] == r['actual_winner'])
    pct_kpm1 = round(100 * h_kpm1 / len(all_rec), 1)

    # v15.1
    def v151(r):
        cls = Classification(r['kpm1_predicted'], r['kpm1_confidence'], r['kpm1_margin_pp'], False, 'kpm1')
        cls = apply_fragmentation_override(r['vote_shares'], cls,
            region=r['region'], council_type=r['council_type'],
            incumbent=r['incumbent'], council_name=r['council'])
        return cls.predicted_winner
    h_v151 = sum(1 for r in all_rec if v151(r) == r['actual_winner'])
    pct_v151 = round(100 * h_v151 / len(all_rec), 1)

    print(f"KPM-1 baseline:    {h_kpm1}/{len(all_rec)} = {pct_kpm1}%")
    print(f"KPM-2.2 v15.1:     {h_v151}/{len(all_rec)} = {pct_v151}%")
    print(f"Lift:              +{pct_v151 - pct_kpm1:.1f}pp absolute")
    print(f"Methodology hash:  {fragmentation_hash()}")

    # Assertions
    assert fragmentation_hash() == EXPECTED_HASH, \
        f"Hash mismatch! Got {fragmentation_hash()}, expected {EXPECTED_HASH}"
    assert abs(pct_kpm1 - EXPECTED_KPM1_PCT) <= TOLERANCE_PP, \
        f"KPM-1 baseline drifted: {pct_kpm1} vs expected {EXPECTED_KPM1_PCT}"
    assert abs(pct_v151 - EXPECTED_V151_PCT) <= TOLERANCE_PP, \
        f"v15.1 drifted: {pct_v151} vs expected {EXPECTED_V151_PCT}"

    print("\n✓ All checks pass. Methodology reproduces published numbers exactly.")

if __name__ == '__main__':
    main()
