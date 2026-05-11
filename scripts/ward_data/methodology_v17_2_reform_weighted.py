"""KPM v17.2 ward-UNS with prior-Reform-weighted swing.

v17.0/v17.1 finding: Reform UK 0/48 recall. Diagnosis: UNS Reform +12pp
applied uniformly fails in Reform-emerging areas (Hartlepool wards had
prior Reform 7-22% and swept the council 11/11 in 2026 — none predicted).

v17.2 hypothesis: scale Reform UNS by prior Reform strength.

  prior Reform % → Reform UNS multiplier
  0-5%           → 1.0×  (use national +12pp)
  5-10%          → 1.3×  (use +15.6pp)
  10-15%         → 1.7×  (use +20.4pp)
  >15%           → 2.0×  (use +24pp — Reform-target tier)

Same principle could apply to Green (urban-core breakthrough), but
v17.2 v0 only handles Reform — the most prominent failure mode.

Per-ward predictions are otherwise identical to v17.0. Council-level
aggregation reuses the v17.1 60% NOC overlay.

This is testable on the existing 188-ward sample without any new data.

Usage:
  python3 -m scripts.ward_data.methodology_v17_2_reform_weighted hartlepool
"""
from __future__ import annotations
import json, hashlib, sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

# Inherit base UNS from v17.0
from scripts.ward_data.methodology_v17_ward_uns import (  # type: ignore[import-not-found]
    UNS_BY_PRIOR_YEAR, PERSONAL_INCUMBENT_BOOST_PP,
)

# Reform-emerging tier thresholds + multipliers
REFORM_SCALING = [
    (0.0, 1.0),     # 0-5% prior → national UNS
    (5.0, 1.3),     # 5-10% → 1.3×
    (10.0, 1.7),    # 10-15% → 1.7×
    (15.0, 2.0),    # >15% → 2.0× (Reform-target tier)
]

@dataclass
class V17_2_Prediction:
    ward_slug: str
    ward_name: str
    predicted_winner: str
    predicted_shares: dict
    prior_winner: str
    prior_year: int
    confidence: str
    reform_multiplier: float
    methodology_name: str = 'KPM-v17.2-ward-uns-reform-weighted'
    methodology_version: str = 'v1.2'
    notes: list = field(default_factory=list)

def reform_multiplier_for(prior_reform_share: float) -> float:
    """Return the UNS multiplier to apply to Reform's national swing."""
    mult = 1.0
    for threshold, m in REFORM_SCALING:
        if prior_reform_share >= threshold:
            mult = m
    return mult

def project_ward_shares_v17_2(prior_shares: dict, prior_year: int,
                              prior_winner: str | None) -> tuple[dict, float]:
    """Apply year-scaled UNS + Reform-weighted multiplier + incumbency. Renormalise."""
    swing = dict(UNS_BY_PRIOR_YEAR.get(prior_year, UNS_BY_PRIOR_YEAR[2024]))
    prior_reform = prior_shares.get('Reform UK', 0)
    reform_mult = reform_multiplier_for(prior_reform)
    swing['Reform UK'] = swing.get('Reform UK', 0) * reform_mult

    out = {}
    for p, s in prior_shares.items():
        new_s = s + swing.get(p, 0.0)
        if prior_winner and p == prior_winner and prior_year >= 2024:
            new_s += PERSONAL_INCUMBENT_BOOST_PP
        out[p] = max(0.0, new_s)
    total = sum(out.values()) or 1
    return {k: round(100*v/total, 2) for k, v in out.items()}, reform_mult

def predict_ward_v17_2(ward_history: dict) -> V17_2_Prediction:
    prior_shares = ward_history.get('prior_party_shares', {})
    prior_winner = ward_history.get('prior_winning_party')
    prior_year = ward_history.get('prior_year', 2024)

    if not prior_shares:
        return V17_2_Prediction(
            ward_slug=ward_history.get('ward_slug','?'),
            ward_name=ward_history.get('ward_name','?'),
            predicted_winner='Unknown', predicted_shares={},
            prior_winner=prior_winner or 'Unknown',
            prior_year=prior_year, confidence='NoData',
            reform_multiplier=1.0,
            notes=['No prior shares'],
        )

    projected, mult = project_ward_shares_v17_2(prior_shares, prior_year, prior_winner)
    sorted_p = sorted(projected.items(), key=lambda kv: -kv[1])
    top, top_share = sorted_p[0]
    runner = sorted_p[1][1] if len(sorted_p) > 1 else 0
    margin = top_share - runner
    confidence = 'Confident' if margin > 15 else ('Lean' if margin > 5 else 'Toss-up')
    notes = []
    if mult > 1.0:
        notes.append(f'Reform-target tier: prior Reform {prior_shares.get("Reform UK",0)}% → {mult}× UNS multiplier')
    return V17_2_Prediction(
        ward_slug=ward_history['ward_slug'],
        ward_name=ward_history['ward_name'],
        predicted_winner=top, predicted_shares=projected,
        prior_winner=prior_winner or 'Unknown',
        prior_year=prior_year, confidence=confidence,
        reform_multiplier=mult, notes=notes,
    )

def predict_council_v17_2(council_slug: str) -> dict:
    history_path = REPO / 'data' / 'ward_data' / f'{council_slug}_history.json'
    current_path = REPO / 'data' / 'ward_data' / f'{council_slug}_2026.json'
    if not history_path.exists():
        return {'error': f'No history for {council_slug}'}

    history = json.loads(history_path.read_text())
    current = json.loads(current_path.read_text()) if current_path.exists() else None

    history_by_slug = {w['ward_slug']: w for w in history['wards']}
    seat_counts: dict = {}
    ward_predictions = []
    target = current['wards'] if current else history['wards']

    for w_2026 in target:
        slug = w_2026['ward_slug']
        h = history_by_slug.get(slug)
        if not h: continue
        pred = predict_ward_v17_2(h)
        if pred.predicted_winner == 'Unknown': continue
        winner_count = w_2026.get('winner_count', 1) if current else h.get('prior_winner_count', 1)
        seat_counts[pred.predicted_winner] = seat_counts.get(pred.predicted_winner, 0) + winner_count
        ward_predictions.append({
            'ward_name': pred.ward_name, 'predicted_winner': pred.predicted_winner,
            'reform_multiplier': pred.reform_multiplier,
            'projected_shares': pred.predicted_shares,
        })

    total_seats = sum(seat_counts.values())
    sorted_seats = sorted(seat_counts.items(), key=lambda kv: -kv[1])
    if not sorted_seats:
        return {'error': 'no predictions'}
    largest, largest_n = sorted_seats[0]
    share = largest_n / total_seats
    # Apply v17.1 60% overlay
    council_winner = largest if share >= 0.60 else 'No overall control'

    return {
        'council_slug': council_slug,
        'methodology': {'name': 'KPM-v17.2-ward-uns-reform-weighted', 'version': 'v1.2',
                        'hash': methodology_hash()},
        'total_seats_predicted': total_seats,
        'seat_counts': dict(sorted_seats),
        'predicted_council_winner': council_winner,
        'largest_party_share_pct': round(100 * share, 1),
        'ward_predictions': ward_predictions,
    }

METHODOLOGY_RULES = {
    'schema_version': 'kpm-v17.2-reform-weighted-v1',
    'name': 'kpm_v17_2_ward_uns_reform_weighted',
    'description': (
        'v17.0 ward-UNS with prior-Reform-weighted multiplier (1.0-2.0×) '
        'on Reform national swing, plus v17.1 60% NOC council overlay.'
    ),
    'reform_scaling_thresholds': REFORM_SCALING,
    'base_methodology': 'kpm-v17-ward-uns',
    'overlay': 'v17.1 60% NOC threshold',
    'rationale': (
        'Reform UK 0/48 recall in v17.0/v17.1 — UNS Reform +12pp uniform fails in '
        'Reform-emerging areas. Hartlepool wards had prior Reform 7-22% and swept '
        '11/11 in 2026 with zero v17 predictions. Scaling Reform UNS by prior '
        'Reform strength is the cheapest data-driven fix that needs no new data.'
    ),
}

def methodology_hash():
    canonical = json.dumps(METHODOLOGY_RULES, sort_keys=True, indent=2, default=list)
    return hashlib.sha256(canonical.encode()).hexdigest()

if __name__ == '__main__':
    print(f"KPM-v17.2 hash: {methodology_hash()}\n")
    target = sys.argv[1] if len(sys.argv) > 1 else None
    if target:
        targets = [target]
    else:
        ward_dir = REPO / 'data' / 'ward_data'
        targets = sorted({p.stem.replace('_history','') for p in ward_dir.glob('*_history.json')})
    for slug in targets:
        pred = predict_council_v17_2(slug)
        if pred.get('error'):
            print(f"[skip] {slug}: {pred['error']}")
            continue
        n_reform_target = sum(1 for w in pred['ward_predictions'] if w['reform_multiplier'] > 1.0)
        print(f"  {slug:24s}: {pred['predicted_council_winner']:25s} (largest {pred['largest_party_share_pct']}%, {n_reform_target} Reform-target wards)")
