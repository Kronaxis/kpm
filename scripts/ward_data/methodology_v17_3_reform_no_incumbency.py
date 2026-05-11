"""KPM v17.3 = v17.2 + suppress incumbency boost in Reform-target wards.

v17.2 trace on De Bruce (Hartlepool):
  Prior: Lab 54.85, Con 23.88, Reform 21.27
  UNS Reform 2× = +24 → Reform 45.27
  UNS Lab -10 + 4 incumbency = -6 → Lab 48.85
  Renormalised: Lab 44.41, Reform 41.15 → Lab still wins by 3.26pp

Without incumbency:
  Lab 44.85, Reform 45.27 → Reform wins by ~0.4pp ✓

Hypothesis: in Reform-target wards (prior Reform ≥10%), the conventional
incumbency boost doesn't apply because the political environment has
shifted enough that the prior incumbent's brand is actively a liability.

v17.3 rule: if Reform multiplier ≥ 1.7 (prior Reform ≥10%) → set
incumbency boost to 0 for the prior winner.
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

# Threshold above which Reform-target classification suppresses incumbency boost
REFORM_TARGET_INCUMBENCY_SUPPRESSION_MULT = 1.7  # prior Reform ≥10% → no incumbency

@dataclass
class V17_3_Prediction:
    ward_slug: str
    ward_name: str
    predicted_winner: str
    predicted_shares: dict
    prior_winner: str
    prior_year: int
    confidence: str
    reform_multiplier: float
    incumbency_applied: bool
    methodology_name: str = 'KPM-v17.3-ward-uns-reform-no-incumbency'
    methodology_version: str = 'v1.3'
    notes: list = field(default_factory=list)

def project_ward_shares_v17_3(prior_shares: dict, prior_year: int,
                               prior_winner: str | None) -> tuple[dict, float, bool]:
    swing = dict(UNS_BY_PRIOR_YEAR.get(prior_year, UNS_BY_PRIOR_YEAR[2024]))
    prior_reform = prior_shares.get('Reform UK', 0)
    reform_mult = reform_multiplier_for(prior_reform)
    swing['Reform UK'] = swing.get('Reform UK', 0) * reform_mult
    suppress_incumbency = reform_mult >= REFORM_TARGET_INCUMBENCY_SUPPRESSION_MULT

    out = {}
    incumbency_applied = False
    for p, s in prior_shares.items():
        new_s = s + swing.get(p, 0.0)
        if (prior_winner and p == prior_winner and prior_year >= 2024
                and not suppress_incumbency):
            new_s += PERSONAL_INCUMBENT_BOOST_PP
            incumbency_applied = True
        out[p] = max(0.0, new_s)
    total = sum(out.values()) or 1
    return {k: round(100*v/total, 2) for k, v in out.items()}, reform_mult, incumbency_applied

def predict_ward_v17_3(ward_history: dict) -> V17_3_Prediction:
    prior_shares = ward_history.get('prior_party_shares', {})
    prior_winner = ward_history.get('prior_winning_party')
    prior_year = ward_history.get('prior_year', 2024)
    if not prior_shares:
        return V17_3_Prediction(
            ward_slug=ward_history.get('ward_slug','?'),
            ward_name=ward_history.get('ward_name','?'),
            predicted_winner='Unknown', predicted_shares={},
            prior_winner=prior_winner or 'Unknown',
            prior_year=prior_year, confidence='NoData',
            reform_multiplier=1.0, incumbency_applied=False,
        )
    projected, mult, incumb = project_ward_shares_v17_3(prior_shares, prior_year, prior_winner)
    sorted_p = sorted(projected.items(), key=lambda kv: -kv[1])
    top, top_share = sorted_p[0]
    runner = sorted_p[1][1] if len(sorted_p) > 1 else 0
    margin = top_share - runner
    confidence = 'Confident' if margin > 15 else ('Lean' if margin > 5 else 'Toss-up')
    notes = []
    if mult >= REFORM_TARGET_INCUMBENCY_SUPPRESSION_MULT:
        notes.append(f'Reform-target tier: incumbency boost suppressed')
    return V17_3_Prediction(
        ward_slug=ward_history['ward_slug'], ward_name=ward_history['ward_name'],
        predicted_winner=top, predicted_shares=projected,
        prior_winner=prior_winner or 'Unknown', prior_year=prior_year,
        confidence=confidence, reform_multiplier=mult,
        incumbency_applied=incumb, notes=notes,
    )

def predict_council_v17_3(council_slug: str) -> dict:
    history_path = REPO / 'data' / 'ward_data' / f'{council_slug}_history.json'
    current_path = REPO / 'data' / 'ward_data' / f'{council_slug}_2026.json'
    if not history_path.exists():
        return {'error': f'No history for {council_slug}'}
    history = json.loads(history_path.read_text())
    current = json.loads(current_path.read_text()) if current_path.exists() else None
    history_by_slug = {w['ward_slug']: w for w in history['wards']}
    seat_counts: dict = {}
    target = current['wards'] if current else history['wards']
    for w_2026 in target:
        h = history_by_slug.get(w_2026['ward_slug'])
        if not h: continue
        pred = predict_ward_v17_3(h)
        if pred.predicted_winner == 'Unknown': continue
        winner_count = w_2026.get('winner_count', 1) if current else h.get('prior_winner_count', 1)
        seat_counts[pred.predicted_winner] = seat_counts.get(pred.predicted_winner, 0) + winner_count
    total_seats = sum(seat_counts.values())
    sorted_seats = sorted(seat_counts.items(), key=lambda kv: -kv[1])
    if not sorted_seats: return {'error': 'no predictions'}
    largest, largest_n = sorted_seats[0]
    share = largest_n / total_seats
    council_winner = largest if share >= 0.60 else 'No overall control'
    return {
        'council_slug': council_slug,
        'methodology': {'name': 'KPM-v17.3', 'version': 'v1.3', 'hash': methodology_hash()},
        'total_seats_predicted': total_seats,
        'seat_counts': dict(sorted_seats),
        'predicted_council_winner': council_winner,
        'largest_party_share_pct': round(100 * share, 1),
    }

METHODOLOGY_RULES = {
    'schema_version': 'kpm-v17.3-no-incumbency-in-reform-target',
    'name': 'kpm_v17_3_reform_no_incumbency',
    'description': (
        'v17.2 (Reform-weighted UNS) + suppress incumbency boost in '
        'Reform-target wards (Reform mult ≥ 1.7, i.e., prior Reform ≥10%). '
        'In Reform-emerging environments the prior incumbent is often a '
        'net liability not an asset.'
    ),
    'reform_scaling_thresholds': REFORM_SCALING,
    'reform_target_incumbency_suppression_mult': REFORM_TARGET_INCUMBENCY_SUPPRESSION_MULT,
    'overlay': 'v17.1 60% NOC threshold',
    'rationale': (
        'v17.2 Reform mult 2× still misses Hartlepool because Lab incumbency +4pp '
        'preserves Lab leads. Removing incumbency in Reform-target wards lets '
        'Reform overtake.'
    ),
}

def methodology_hash():
    canonical = json.dumps(METHODOLOGY_RULES, sort_keys=True, indent=2, default=list)
    return hashlib.sha256(canonical.encode()).hexdigest()

if __name__ == '__main__':
    print(f"KPM-v17.3 hash: {methodology_hash()}\n")
    target = sys.argv[1] if len(sys.argv) > 1 else None
    if target:
        targets = [target]
    else:
        ward_dir = REPO / 'data' / 'ward_data'
        targets = sorted({p.stem.replace('_history','') for p in ward_dir.glob('*_history.json')})
    for slug in targets:
        pred = predict_council_v17_3(slug)
        if pred.get('error'):
            print(f"[skip] {slug}: {pred['error']}")
            continue
        print(f"  {slug:24s}: {pred['predicted_council_winner']:25s} (largest {pred['largest_party_share_pct']}%)")
