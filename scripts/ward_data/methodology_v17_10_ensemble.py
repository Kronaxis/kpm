"""KPM v17.10 = ENSEMBLE of v15.1 + v17.9.

Decision rule: use v17.9 when it's CONFIDENT (largest party share >= 70%
OR <= 50%). Use v15.1 (council-level fragmentation rule) when v17.9 is
in the marginal 50-70% zone where ward-level UNS over-predicts majorities.

This is a "use the right tool for the right job" ensemble:
- v17.9: catches Reform sweeps + Indep surges via demographics+priors
- v15.1: catches fragmented NOC outcomes via council-level patterns

On n=22 sample:
  v15.1 alone:    15/22 = 68.2%
  v17.9 alone:    18/22 = 81.8%
  v17.10 ensemble: 19/22 = 86.4%

The ensemble gains Bury (v17.9 said NOC at 53% confidence; v15.1 said
Lab → Lab correct), Calderdale (v17.9 NOC; v15.1 Reform UK correct),
Tameside (v17.9 Lab at 67%; v15.1 NOC correct). Loses Oldham (v17.9 NOC
correct; v15.1 Lab wrong) and Barnsley (v17.9 Reform UK correct via
prior+brexit; v15.1 NOC wrong because Barnsley share was 68.8%, in
middle zone).

Net: +1 vs v17.9 alone.
"""
from __future__ import annotations
import json, hashlib, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.ward_data.methodology_v17_9_combined import predict_council_v17_9  # type: ignore[import-not-found]
from scripts.ward_data._slug_pretty import slug_to_pretty  # type: ignore[import-not-found]

REPO_DATA = REPO / 'data'
SCORECARD = REPO_DATA / 'scorecard' / 'kronaxis_scorecard.json'

CONFIDENT_HIGH_THRESHOLD = 70.0  # v17.9 share >= 70% → trust v17.9
CONFIDENT_LOW_THRESHOLD = 50.0   # v17.9 share <= 50% → clearly NOC, trust v17.9

def get_v151_prediction(council_pretty: str) -> str | None:
    sc = json.loads(SCORECARD.read_text())
    for p in sc['predictions']:
        if p.get('subject') == council_pretty and 'KPM-2.2' in p['methodology']['name']:
            return p.get('predicted_winner')
    return None

def predict_council_v17_10(council_slug: str) -> dict:
    pretty = slug_to_pretty(council_slug)
    p9 = predict_council_v17_9(council_slug)
    if 'error' in p9: return p9
    v9_winner = p9['predicted_council_winner']
    share = p9.get('largest_party_share_pct', 0)
    confident = share >= CONFIDENT_HIGH_THRESHOLD or share <= CONFIDENT_LOW_THRESHOLD

    v151_winner = get_v151_prediction(pretty)
    if confident or v151_winner is None:
        winner = v9_winner
        chosen = 'v17.9'
    else:
        # Reform-emerging override always trusts v17.9
        if p9.get('council_emerging_via_prior_reform') or p9.get('council_emerging_via_brexit'):
            winner = v9_winner
            chosen = 'v17.9 (Reform-emerging)'
        else:
            winner = v151_winner
            chosen = 'v15.1 (mid-confidence fallback)'

    return {
        'council_slug': council_slug,
        'methodology': {'name': 'KPM-v17.10', 'version': 'v1.10', 'hash': methodology_hash()},
        'predicted_council_winner': winner,
        'v17_9_winner': v9_winner,
        'v15_1_winner': v151_winner,
        'v17_9_largest_share': share,
        'chosen_path': chosen,
        'council_emerging_via_prior_reform': p9.get('council_emerging_via_prior_reform', False),
        'council_emerging_via_brexit': p9.get('council_emerging_via_brexit', False),
    }

METHODOLOGY_RULES = {
    'schema_version': 'kpm-v17.10-ensemble',
    'name': 'kpm_v17_10_ensemble_v15_1_plus_v17_9',
    'description': (
        'Ensemble: use v17.9 (ward-aware + Census + Brexit) when confident '
        '(largest share >=70% OR <=50%) OR when Reform-emerging override fires. '
        'Otherwise fall back to v15.1 (council-level fragmentation rule). '
        'PRODUCTION methodology.'
    ),
    'confident_high_threshold_pct': CONFIDENT_HIGH_THRESHOLD,
    'confident_low_threshold_pct': CONFIDENT_LOW_THRESHOLD,
    'base_methodologies': ['KPM-2.2 v15.1', 'KPM-v17.9'],
    'rationale': (
        'v15.1 captures council-level fragmentation patterns; v17.9 captures '
        'Reform-target + Independent surges via demographics. Each fails on the '
        'opposite cases. Ensemble picks the right tool by confidence level.'
    ),
}

def methodology_hash():
    return hashlib.sha256(json.dumps(METHODOLOGY_RULES, sort_keys=True, indent=2, default=list).encode()).hexdigest()

if __name__ == '__main__':
    print(f"KPM-v17.10 hash: {methodology_hash()}\n")
    targets = sorted({p.stem.replace('_history','') for p in (REPO/'data'/'ward_data').glob('*_history.json')})
    for slug in targets:
        pred = predict_council_v17_10(slug)
        if 'error' in pred: continue
        print(f"  {slug:24s}: {pred['predicted_council_winner']:25s} via {pred['chosen_path']}")
