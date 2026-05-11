"""KPM v17.12 = v17.10 with tighter Brexit threshold (65% instead of 60%).

v17.10 Brexit fires at 60%+ Leave. This causes 2 false positives:
  - Wigan (Brexit 62.7%, Lab actual)
  - Wolverhampton (Brexit 63.4%, NOC actual; v17.10 says Reform UK)

Tightening to 65%:
  - Wakefield (62.8%) → no longer fires (LOSE this catch)
  - Wolverhampton (63.4%) → no longer fires → would say Lab (still wrong but matches v15.1)
  - Wigan (62.7%) → no longer fires → say Lab (correct!)
  - Hartlepool (69.6%) → still fires (already prior+Brexit)
  - Barnsley (68.3%) → still fires
  - Sandwell (66.7%) → still fires
  - Calderdale (55.7%) → never fired

Net trade: lose Wakefield, gain Wigan + Wolverhampton stays-as-Lab-wrong.
On n=35: should be 27/35 - 1 (Wakefield) + 1 (Wigan) = 27/35 (no change in winners count).

Worth checking empirically.
"""
from __future__ import annotations
import json, hashlib, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import scripts.ward_data.methodology_v17_8_brexit as v17_8_mod
from scripts.ward_data.methodology_v17_10_ensemble import predict_council_v17_10  # type: ignore[import-not-found]

BREXIT_THRESHOLD = 0.65

def predict_council_v17_12(council_slug: str) -> dict:
    # Patch threshold temporarily
    original = v17_8_mod.BREXIT_LEAVE_THRESHOLD
    v17_8_mod.BREXIT_LEAVE_THRESHOLD = BREXIT_THRESHOLD  # type: ignore[attr-defined]
    pred = predict_council_v17_10(council_slug)
    v17_8_mod.BREXIT_LEAVE_THRESHOLD = original  # type: ignore[attr-defined]
    if 'methodology' in pred:
        pred['methodology'] = {'name': 'KPM-v17.12', 'version': 'v1.12', 'hash': methodology_hash()}
    return pred

METHODOLOGY_RULES = {
    'schema_version': 'kpm-v17.12-tighter-brexit-65pct',
    'name': 'kpm_v17_12_brexit_65',
    'description': 'v17.10 ensemble with Brexit Reform-target threshold tightened from 60% to 65% Leave.',
    'brexit_leave_threshold': BREXIT_THRESHOLD,
}

def methodology_hash():
    return hashlib.sha256(json.dumps(METHODOLOGY_RULES, sort_keys=True, indent=2, default=list).encode()).hexdigest()

if __name__ == '__main__':
    print(f"v17.12 hash: {methodology_hash()}")
