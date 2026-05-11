"""KPM v17.11 = ensemble of v17.6 (no Brexit) + v15.1.

v17.10 (which added Brexit) over-fires on Wigan (Lab actual, predicted Reform)
and Wolverhampton (NOC actual, predicted Reform). Both have high Leave % but
Lab held / fragmented to NOC, not Reform.

v17.11 hypothesis: Brexit signal is too aggressive at scale. Drop it.
Use ensemble of v17.6 (which catches Reform sweeps via prior Reform >= 5%)
+ v15.1 fallback for mid-confidence cases.

Result on n=29: should be 23+ (gain Wigan + Wolverhampton fix; possibly lose
Wakefield which Brexit caught).
"""
from __future__ import annotations
import json, hashlib, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.ward_data.methodology_v17_6_council_override import predict_council_v17_6  # type: ignore[import-not-found]
from scripts.ward_data._slug_pretty import slug_to_pretty  # type: ignore[import-not-found]

SCORECARD = REPO / 'data' / 'scorecard' / 'kronaxis_scorecard.json'

CONFIDENT_HIGH_THRESHOLD = 70.0
CONFIDENT_LOW_THRESHOLD = 50.0

def get_v151_prediction(council_pretty: str) -> str | None:
    sc = json.loads(SCORECARD.read_text())
    for p in sc['predictions']:
        if p.get('subject') == council_pretty and 'KPM-2.2' in p['methodology']['name']:
            return p.get('predicted_winner')
    return None

def predict_council_v17_11(council_slug: str) -> dict:
    pretty = slug_to_pretty(council_slug)
    p6 = predict_council_v17_6(council_slug)
    if 'error' in p6: return p6
    v6_winner = p6['predicted_council_winner']
    share = p6.get('largest_party_share', 0)
    confident = share >= CONFIDENT_HIGH_THRESHOLD or share <= CONFIDENT_LOW_THRESHOLD

    v151_winner = get_v151_prediction(pretty)
    if confident or v151_winner is None:
        winner = v6_winner
        chosen = 'v17.6'
    else:
        # Trust v17.6 if Reform-emerging fired
        if p6.get('council_is_reform_emerging'):
            winner = v6_winner
            chosen = 'v17.6 (Reform-emerging)'
        else:
            winner = v151_winner
            chosen = 'v15.1 (mid-confidence fallback)'

    return {
        'council_slug': council_slug,
        'methodology': {'name': 'KPM-v17.11', 'version': 'v1.11', 'hash': methodology_hash()},
        'predicted_council_winner': winner,
        'v17_6_winner': v6_winner,
        'v15_1_winner': v151_winner,
        'v17_6_largest_share': share,
        'chosen_path': chosen,
    }

METHODOLOGY_RULES = {
    'schema_version': 'kpm-v17.11-no-brexit-ensemble',
    'name': 'kpm_v17_11_v17_6_plus_v15_1',
    'description': (
        'Ensemble of v17.6 (no Brexit, no Census Indep) + v15.1. Drops the '
        'Brexit signal which over-fires at scale (Wigan, Wolverhampton).'
    ),
    'confident_high_threshold_pct': CONFIDENT_HIGH_THRESHOLD,
    'confident_low_threshold_pct': CONFIDENT_LOW_THRESHOLD,
    'base_methodologies': ['KPM-2.2 v15.1', 'KPM-v17.6'],
}

def methodology_hash():
    return hashlib.sha256(json.dumps(METHODOLOGY_RULES, sort_keys=True, indent=2, default=list).encode()).hexdigest()

if __name__ == '__main__':
    print(f"KPM-v17.11 hash: {methodology_hash()}\n")
    targets = sorted({p.stem.replace('_history','') for p in (REPO/'data'/'ward_data').glob('*_history.json')})
    for slug in targets:
        pred = predict_council_v17_11(slug)
        if 'error' in pred: continue
        print(f"  {slug:24s}: {pred['predicted_council_winner']:22s} via {pred['chosen_path']}")
