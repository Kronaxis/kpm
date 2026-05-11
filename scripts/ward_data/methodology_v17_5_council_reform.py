"""KPM v17.5 = v17.3 + COUNCIL-level Reform-emergence detection.

v17.3 catches Hartlepool (mean prior Reform 14.8%) but misses Sandwell
(8.2%) and Barnsley (5.8%) — both Reform sweeps. The per-ward Reform
multiplier doesn't fire enough times in these councils.

v17.5 hypothesis: detect Reform-emerging councils (mean prior Reform ≥5%)
and boost Reform multiplier across ALL wards in those councils. The
underlying assumption: Reform breakthroughs are council-wide waves;
ward-level prior is a noisy signal of underlying support that
generalises across the council.

Council-level threshold: mean prior Reform ≥ 5% → all wards in council
get an extra +0.5 Reform multiplier on top of v17.3's per-ward tier.

Reform-emerging councils ALSO get incumbency suppression for ALL Lab
wards (not just Reform-target tier wards).
"""
from __future__ import annotations
import json, hashlib, sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.ward_data.methodology_v17_ward_uns import (  # type: ignore[import-not-found]
    UNS_BY_PRIOR_YEAR, PERSONAL_INCUMBENT_BOOST_PP,
)
from scripts.ward_data.methodology_v17_2_reform_weighted import (  # type: ignore[import-not-found]
    REFORM_SCALING, reform_multiplier_for,
)
from scripts.ward_data.methodology_v17_3_reform_no_incumbency import REFORM_TARGET_INCUMBENCY_SUPPRESSION_MULT  # type: ignore[import-not-found]

# Council-level Reform-emergence thresholds + boosts
COUNCIL_REFORM_EMERGENCE_THRESHOLD_PCT = 5.0
COUNCIL_REFORM_EXTRA_MULT_BOOST = 0.5

@dataclass
class V17_5_Prediction:
    ward_slug: str
    ward_name: str
    predicted_winner: str
    predicted_shares: dict
    prior_winner: str
    prior_year: int
    confidence: str
    reform_multiplier: float
    council_is_reform_emerging: bool
    notes: list = field(default_factory=list)
    methodology_name: str = 'KPM-v17.5-council-reform'
    methodology_version: str = 'v1.5'

def is_reform_emerging_council(history_wards: list) -> bool:
    """Council mean prior Reform ≥ COUNCIL_REFORM_EMERGENCE_THRESHOLD_PCT."""
    if not history_wards: return False
    total = sum(w.get('prior_party_shares', {}).get('Reform UK', 0) for w in history_wards)
    mean = total / len(history_wards)
    return mean >= COUNCIL_REFORM_EMERGENCE_THRESHOLD_PCT

def project_ward_shares_v17_5(prior_shares: dict, prior_year: int,
                               prior_winner: str | None,
                               council_is_reform_emerging: bool) -> tuple[dict, float, bool]:
    swing = dict(UNS_BY_PRIOR_YEAR.get(prior_year, UNS_BY_PRIOR_YEAR[2024]))
    prior_reform = prior_shares.get('Reform UK', 0)
    reform_mult = reform_multiplier_for(prior_reform)
    if council_is_reform_emerging:
        reform_mult += COUNCIL_REFORM_EXTRA_MULT_BOOST
    swing['Reform UK'] = swing.get('Reform UK', 0) * reform_mult
    suppress_incumbency = (
        reform_mult >= REFORM_TARGET_INCUMBENCY_SUPPRESSION_MULT
        or council_is_reform_emerging  # ALL Lab wards in Reform-emerging councils
    )
    out = {}
    for p, s in prior_shares.items():
        new_s = s + swing.get(p, 0.0)
        if (prior_winner and p == prior_winner and prior_year >= 2024
                and not suppress_incumbency):
            new_s += PERSONAL_INCUMBENT_BOOST_PP
        out[p] = max(0.0, new_s)
    total = sum(out.values()) or 1
    return {k: round(100*v/total, 2) for k, v in out.items()}, reform_mult, suppress_incumbency

def predict_council_v17_5(council_slug: str) -> dict:
    history_path = REPO / 'data' / 'ward_data' / f'{council_slug}_history.json'
    current_path = REPO / 'data' / 'ward_data' / f'{council_slug}_2026.json'
    if not history_path.exists():
        return {'error': f'No history for {council_slug}'}
    history = json.loads(history_path.read_text())
    current = json.loads(current_path.read_text()) if current_path.exists() else None
    history_by_slug = {w['ward_slug']: w for w in history['wards']}

    council_emerging = is_reform_emerging_council(history['wards'])
    seat_counts: dict = {}
    target = current['wards'] if current else history['wards']
    ward_predictions = []
    for w_2026 in target:
        h = history_by_slug.get(w_2026['ward_slug'])
        if not h: continue
        projected, reform_mult, _ = project_ward_shares_v17_5(
            h.get('prior_party_shares', {}), h.get('prior_year', 2024),
            h.get('prior_winning_party'), council_emerging,
        )
        if not projected: continue
        sorted_p = sorted(projected.items(), key=lambda kv: -kv[1])
        winner = sorted_p[0][0]
        winner_count = w_2026.get('winner_count', 1) if current else h.get('prior_winner_count', 1)
        seat_counts[winner] = seat_counts.get(winner, 0) + winner_count
        ward_predictions.append({
            'ward_name': h.get('ward_name', w_2026['ward_slug']),
            'predicted_winner': winner,
            'projected_shares': projected,
            'reform_mult': reform_mult,
        })
    total_seats = sum(seat_counts.values())
    sorted_seats = sorted(seat_counts.items(), key=lambda kv: -kv[1])
    if not sorted_seats: return {'error': 'no predictions'}
    largest, largest_n = sorted_seats[0]
    share = largest_n / total_seats
    council_winner = largest if share >= 0.60 else 'No overall control'
    return {
        'council_slug': council_slug,
        'methodology': {'name': 'KPM-v17.5', 'version': 'v1.5', 'hash': methodology_hash()},
        'council_is_reform_emerging': council_emerging,
        'total_seats_predicted': total_seats,
        'seat_counts': dict(sorted_seats),
        'predicted_council_winner': council_winner,
        'largest_party_share_pct': round(100 * share, 1),
        'ward_predictions': ward_predictions,
    }

METHODOLOGY_RULES = {
    'schema_version': 'kpm-v17.5-council-reform-emergence',
    'name': 'kpm_v17_5_council_reform_detection',
    'description': (
        'v17.3 + COUNCIL-level Reform-emergence detection. If council mean '
        f'prior Reform ≥ {COUNCIL_REFORM_EMERGENCE_THRESHOLD_PCT}%, all wards '
        f'get +{COUNCIL_REFORM_EXTRA_MULT_BOOST} Reform multiplier AND all '
        'Lab incumbents lose incumbency boost.'
    ),
    'reform_scaling_thresholds': REFORM_SCALING,
    'council_reform_emergence_threshold_pct': COUNCIL_REFORM_EMERGENCE_THRESHOLD_PCT,
    'council_reform_extra_mult_boost': COUNCIL_REFORM_EXTRA_MULT_BOOST,
    'overlay': 'v17.1 60% NOC threshold',
    'rationale': (
        'v17.3 misses Sandwell (mean prior Reform 8.2%) and Barnsley (5.8%) '
        'because per-ward detection only fires in Reform-prior wards. Council-'
        'wide Reform sweeps need council-wide signal. Hartlepool 14.8% mean '
        'is the canonical positive case (already caught by v17.3).'
    ),
}

def methodology_hash():
    canonical = json.dumps(METHODOLOGY_RULES, sort_keys=True, indent=2, default=list)
    return hashlib.sha256(canonical.encode()).hexdigest()

if __name__ == '__main__':
    print(f"KPM-v17.5 hash: {methodology_hash()}\n")
    target = sys.argv[1] if len(sys.argv) > 1 else None
    if target:
        targets = [target]
    else:
        ward_dir = REPO / 'data' / 'ward_data'
        targets = sorted({p.stem.replace('_history','') for p in ward_dir.glob('*_history.json')})
    for slug in targets:
        pred = predict_council_v17_5(slug)
        if pred.get('error'):
            print(f"[skip] {slug}: {pred['error']}")
            continue
        emerging = ' (REFORM-EMERGING)' if pred['council_is_reform_emerging'] else ''
        print(f"  {slug:24s}: {pred['predicted_council_winner']:25s} (largest {pred['largest_party_share_pct']}%){emerging}")
