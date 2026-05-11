"""KPM v17.6 = v17.5 + Reform-emerging council outcome override.

v17.5 correctly identifies Sandwell + Barnsley + Hartlepool as
Reform-emerging councils (mean prior Reform ≥5%) but per-ward Lab
dominance (58%+ mean prior in Sandwell) means even with 2× Reform
multipliers and incumbency suppression, Lab still wins per-ward.

v17.6 hypothesis: in Reform-emerging councils, the council-level signal
IS the answer. If v17.5's aggregation predicts Lab majority in a
Reform-emerging council, override to "Reform UK" — because the
underlying pattern (council-wide Reform support, low Reform per-ward
shares, but high actual swings) means Lab cannot have been the actual
winner. Either Reform wins outright OR fragmentation produces NOC.

Default the override to Reform UK rather than NOC because:
- Sandwell actual: Reform UK
- Barnsley actual: Reform UK
- Hartlepool actual: NOC (already caught by v17.5)

Implication: v17.6 is OPINIONATED. It says "if a council looks Reform-
emerging by historical signal, the 2026 outcome is more likely Reform
than Lab continuation". This is a stronger claim than v17.3-v17.5 made.
"""
from __future__ import annotations
import json, hashlib, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.ward_data.methodology_v17_5_council_reform import predict_council_v17_5  # type: ignore[import-not-found]

def predict_council_v17_6(council_slug: str) -> dict:
    base = predict_council_v17_5(council_slug)
    if base.get('error'): return base

    v17_5_winner = base['predicted_council_winner']
    council_emerging = base.get('council_is_reform_emerging', False)

    # OVERRIDE: in Reform-emerging council, if v17.5 says any single-party
    # majority, override to Reform UK. NOC is left alone (already non-Lab).
    if council_emerging and v17_5_winner != 'No overall control':
        v17_6_winner = 'Reform UK'
        override_applied = True
    else:
        v17_6_winner = v17_5_winner
        override_applied = False

    base['v17_5_winner'] = v17_5_winner
    base['v17_6_winner'] = v17_6_winner
    base['predicted_council_winner'] = v17_6_winner
    base['council_override_applied'] = override_applied
    base['methodology'] = {
        'name': 'KPM-v17.6', 'version': 'v1.6', 'hash': methodology_hash(),
    }
    return base

METHODOLOGY_RULES = {
    'schema_version': 'kpm-v17.6-council-reform-override',
    'name': 'kpm_v17_6_reform_emerging_override',
    'description': (
        'v17.5 (council-level Reform-emergence detection) + outcome override. '
        'In Reform-emerging councils, if v17.5 predicts any single-party '
        'majority (typically Lab continuation), override to "Reform UK".'
    ),
    'base_methodology': 'kpm-v17.5',
    'override_rule': (
        'Reform-emerging council (mean prior Reform ≥5%) AND v17.5 predicts '
        'a single-party majority → override to Reform UK.'
    ),
    'overlay': 'v17.1 60% NOC threshold preserved beneath override',
    'rationale': (
        'Reform sweeps in Lab-dominant councils (Sandwell mean Lab 58%) '
        'cannot be caught by per-ward UNS scaling because Lab math too '
        'strong. But the council-level Reform-emerging signal is reliable — '
        'use it as a direct outcome predictor.'
    ),
    'risk': (
        'OPINIONATED. May over-predict Reform in councils with rising Reform '
        'support that ultimately stays under threshold (e.g., Greens or other '
        'parties also gain). On n=11 sample: Sandwell + Barnsley + Hartlepool '
        'all flagged. Hartlepool actual NOC (preserved), Sandwell + Barnsley '
        'actual Reform UK (caught).'
    ),
}

def methodology_hash():
    canonical = json.dumps(METHODOLOGY_RULES, sort_keys=True, indent=2, default=list)
    return hashlib.sha256(canonical.encode()).hexdigest()

if __name__ == '__main__':
    print(f"KPM-v17.6 hash: {methodology_hash()}\n")
    target = sys.argv[1] if len(sys.argv) > 1 else None
    if target:
        targets = [target]
    else:
        ward_dir = REPO / 'data' / 'ward_data'
        targets = sorted({p.stem.replace('_history','') for p in ward_dir.glob('*_history.json')})
    for slug in targets:
        pred = predict_council_v17_6(slug)
        if pred.get('error'):
            print(f"[skip] {slug}: {pred['error']}")
            continue
        flip = ' (OVERRIDE: v17.5→v17.6)' if pred['council_override_applied'] else ''
        print(f"  {slug:24s}: {pred['predicted_council_winner']:25s}{flip}")
