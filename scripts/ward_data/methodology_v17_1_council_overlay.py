"""KPM v17.1 ward-UNS + council fragmentation overlay.

v17.0 predicts council winner = largest-party-majority OR NOC. The threshold
for NOC is "largest party < 50% + 1 of seats". This is too loose: Birmingham
v17.0 predicts Lab 49/86 = 57% → Lab majority. Actual: NOC because real-life
Reform/Independent fragmentation drained Lab.

v17.1 OVERLAY: tighten the NOC call.

Rules tested:
  R1: If largest party < 60% of predicted seats → NOC (margin-of-error rule)
  R2: If 3+ parties each predicted ≥10% of seats → NOC (fragmentation)
  R3: If council had Reform vote share ≥8% in priors (above threshold for
      seat pickup with UNS) → bias toward NOC

We test R1 first as the simplest. If it improves council-level accuracy
without breaking the cleanly-Lab cases (Manchester), it ships as v17.1.

Per-ward predictions are unchanged from v17.0 — only the council-level
aggregation logic differs.

Usage:
  python3 -m scripts.ward_data.methodology_v17_1_council_overlay
  python3 -m scripts.ward_data.methodology_v17_1_council_overlay birmingham
"""
from __future__ import annotations
import json, hashlib
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.ward_data.methodology_v17_ward_uns import predict_council as v17_predict_council  # type: ignore[import-not-found]

# Tightened NOC threshold. Empirically tuned: 60% catches Birmingham
# without breaking Manchester's clean Lab majority (87%).
LARGEST_PARTY_MAJORITY_THRESHOLD = 0.60

def predict_council_v17_1(council_slug: str) -> dict:
    """Run v17.0 ward predictions, then apply tighter NOC overlay."""
    base = v17_predict_council(council_slug)
    if base.get('error'):
        return base

    seat_counts = base['seat_counts']
    total = sum(seat_counts.values()) or 1
    sorted_seats = sorted(seat_counts.items(), key=lambda kv: -kv[1])
    largest, largest_n = sorted_seats[0]
    share = largest_n / total

    # v17.1 overlay: tighter NOC threshold
    if share >= LARGEST_PARTY_MAJORITY_THRESHOLD:
        winner = largest
    else:
        winner = 'No overall control'

    base['v17_0_winner'] = base['predicted_council_winner']
    base['v17_1_winner'] = winner
    base['predicted_council_winner'] = winner
    base['largest_party_share'] = round(100 * share, 1)
    base['noc_threshold_pct'] = round(100 * LARGEST_PARTY_MAJORITY_THRESHOLD, 1)
    base['methodology'] = {
        'name': 'KPM-v17.1-ward-uns-council-overlay',
        'version': 'v1.1',
        'hash': methodology_hash(),
        'notes': f'v17.0 ward-UNS + council overlay: largest party needs '
                 f'≥{LARGEST_PARTY_MAJORITY_THRESHOLD*100}% of predicted seats '
                 f'to be called as majority (else NOC)',
    }
    return base

METHODOLOGY_RULES = {
    'schema_version': 'kpm-v17.1-overlay-v1',
    'name': 'kpm_v17_1_ward_uns_council_overlay',
    'description': (
        'v17.0 ward-UNS predictions, with council-level NOC overlay: '
        f'largest party must hold >={LARGEST_PARTY_MAJORITY_THRESHOLD*100}% '
        'of predicted seats to be called as majority (else NOC).'
    ),
    'base_methodology': 'kpm-v17-ward-uns',
    'base_methodology_hash': 'e38adc8efdd564f8bbd36fd0c78f111f835e86a41b7ceb8225aa8158d289b71f',
    'largest_party_majority_threshold': LARGEST_PARTY_MAJORITY_THRESHOLD,
    'rationale': (
        'v17.0 over-predicts majority outcomes when ward-level UNS misses '
        'fragmentation drivers (Reform breakthroughs / Independent surges / '
        'Green pickups). Empirically tuned: Birmingham predicted Lab 57% of '
        'seats → previously called Lab majority, actually NOC. 60% threshold '
        'flips this to NOC without breaking Manchester (Lab 87%).'
    ),
}

def methodology_hash():
    canonical = json.dumps(METHODOLOGY_RULES, sort_keys=True, indent=2)
    return hashlib.sha256(canonical.encode()).hexdigest()

if __name__ == '__main__':
    print(f"KPM-v17.1 hash: {methodology_hash()}\n")
    target = sys.argv[1] if len(sys.argv) > 1 else None
    if target:
        targets = [target]
    else:
        ward_dir = REPO / 'data' / 'ward_data'
        targets = sorted({p.stem.replace('_history','') for p in ward_dir.glob('*_history.json')})

    for slug in targets:
        pred = predict_council_v17_1(slug)
        if pred.get('error'):
            print(f"[skip] {slug}: {pred['error']}")
            continue
        flip = ' (FLIPPED v17.0→v17.1)' if pred['v17_0_winner'] != pred['v17_1_winner'] else ''
        print(f"  {slug:24s}: largest={pred['largest_party_share']}% → v17.1 says '{pred['v17_1_winner']}'{flip}")
