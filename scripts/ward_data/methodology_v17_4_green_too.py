"""KPM v17.4 = v17.3 + symmetric Green-target detection.

v17.3 catches Reform sweeps via:
  - Reform UNS multiplier (1.0-2.0×) by prior Reform share
  - Suppress incumbency boost in Reform-target wards (Reform ≥10%)

Diagnostic shows 67% of Green wins had prior Green ≥15% — Greens are
MORE predictable from priors than Reform. v17.4 applies the same
mechanism for Green:
  - Green UNS multiplier (1.0-1.5×) by prior Green share
  - Suppress incumbency boost in Green-target wards (Green ≥15%)

Note: Green multipliers are smaller than Reform's. Green's national
swing is +3pp; even 1.5× = +4.5pp is small. The win comes mainly from
removing the prior incumbent's incumbency boost when Green has high
local prior, letting Green's existing lead translate to a 2026 win.

Otherwise identical to v17.3.
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

# Green-target scaling (analogous to Reform but smaller magnitudes)
GREEN_SCALING = [
    (0.0, 1.0),    # 0-10% prior → national UNS (+3pp)
    (10.0, 1.3),   # 10-15% → 1.3×
    (15.0, 1.5),   # >15% → 1.5× (Green-target tier — also suppresses incumbency)
]
GREEN_TARGET_INCUMBENCY_SUPPRESSION_MULT = 1.5  # >15% prior Green
REFORM_TARGET_INCUMBENCY_SUPPRESSION_MULT = 1.7  # ≥10% prior Reform

def green_multiplier_for(prior_green_share: float) -> float:
    mult = 1.0
    for threshold, m in GREEN_SCALING:
        if prior_green_share >= threshold:
            mult = m
    return mult

@dataclass
class V17_4_Prediction:
    ward_slug: str
    ward_name: str
    predicted_winner: str
    predicted_shares: dict
    prior_winner: str
    prior_year: int
    confidence: str
    reform_multiplier: float
    green_multiplier: float
    incumbency_applied: bool
    notes: list = field(default_factory=list)
    methodology_name: str = 'KPM-v17.4-ward-uns-reform-green'
    methodology_version: str = 'v1.4'

def project_ward_shares_v17_4(prior_shares: dict, prior_year: int,
                               prior_winner: str | None) -> tuple[dict, float, float, bool]:
    swing = dict(UNS_BY_PRIOR_YEAR.get(prior_year, UNS_BY_PRIOR_YEAR[2024]))
    prior_reform = prior_shares.get('Reform UK', 0)
    prior_green = prior_shares.get('Green', 0)
    reform_mult = reform_multiplier_for(prior_reform)
    green_mult = green_multiplier_for(prior_green)
    swing['Reform UK'] = swing.get('Reform UK', 0) * reform_mult
    swing['Green'] = swing.get('Green', 0) * green_mult

    suppress_for_reform = reform_mult >= REFORM_TARGET_INCUMBENCY_SUPPRESSION_MULT
    suppress_for_green = green_mult >= GREEN_TARGET_INCUMBENCY_SUPPRESSION_MULT
    suppress_incumbency = suppress_for_reform or suppress_for_green

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
    return {k: round(100*v/total, 2) for k, v in out.items()}, reform_mult, green_mult, incumbency_applied

def predict_ward_v17_4(ward_history: dict) -> V17_4_Prediction:
    prior_shares = ward_history.get('prior_party_shares', {})
    prior_winner = ward_history.get('prior_winning_party')
    prior_year = ward_history.get('prior_year', 2024)
    if not prior_shares:
        return V17_4_Prediction(
            ward_slug=ward_history.get('ward_slug','?'),
            ward_name=ward_history.get('ward_name','?'),
            predicted_winner='Unknown', predicted_shares={},
            prior_winner=prior_winner or 'Unknown',
            prior_year=prior_year, confidence='NoData',
            reform_multiplier=1.0, green_multiplier=1.0,
            incumbency_applied=False,
        )
    projected, rm, gm, incumb = project_ward_shares_v17_4(prior_shares, prior_year, prior_winner)
    sorted_p = sorted(projected.items(), key=lambda kv: -kv[1])
    top, top_share = sorted_p[0]
    runner = sorted_p[1][1] if len(sorted_p) > 1 else 0
    margin = top_share - runner
    confidence = 'Confident' if margin > 15 else ('Lean' if margin > 5 else 'Toss-up')
    notes = []
    if rm >= REFORM_TARGET_INCUMBENCY_SUPPRESSION_MULT:
        notes.append('Reform-target: incumbency suppressed')
    if gm >= GREEN_TARGET_INCUMBENCY_SUPPRESSION_MULT:
        notes.append('Green-target: incumbency suppressed')
    return V17_4_Prediction(
        ward_slug=ward_history['ward_slug'], ward_name=ward_history['ward_name'],
        predicted_winner=top, predicted_shares=projected,
        prior_winner=prior_winner or 'Unknown', prior_year=prior_year,
        confidence=confidence, reform_multiplier=rm, green_multiplier=gm,
        incumbency_applied=incumb, notes=notes,
    )

def predict_council_v17_4(council_slug: str) -> dict:
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
        pred = predict_ward_v17_4(h)
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
        'methodology': {'name': 'KPM-v17.4', 'version': 'v1.4', 'hash': methodology_hash()},
        'total_seats_predicted': total_seats,
        'seat_counts': dict(sorted_seats),
        'predicted_council_winner': council_winner,
        'largest_party_share_pct': round(100 * share, 1),
    }

METHODOLOGY_RULES = {
    'schema_version': 'kpm-v17.4-reform-and-green-targets',
    'name': 'kpm_v17_4_ward_uns_reform_green',
    'description': (
        'v17.3 + symmetric Green-target detection (1.0-1.5× UNS multiplier '
        'by prior Green share, suppress incumbency when prior Green ≥15%).'
    ),
    'reform_scaling_thresholds': REFORM_SCALING,
    'green_scaling_thresholds': GREEN_SCALING,
    'reform_target_incumbency_suppression_mult': REFORM_TARGET_INCUMBENCY_SUPPRESSION_MULT,
    'green_target_incumbency_suppression_mult': GREEN_TARGET_INCUMBENCY_SUPPRESSION_MULT,
    'overlay': 'v17.1 60% NOC threshold',
    'rationale': (
        '67% of 2026 Green ward wins had prior Green ≥15%. v17.3 only '
        'catches 14/52 Greens because incumbency boost preserves prior Lab '
        'leads. Symmetric Green-target rule unblocks Green predictions '
        'in Manchester (Lab→Green wave), Sheffield + Leeds (existing Green strongholds).'
    ),
}

def methodology_hash():
    canonical = json.dumps(METHODOLOGY_RULES, sort_keys=True, indent=2, default=list)
    return hashlib.sha256(canonical.encode()).hexdigest()

if __name__ == '__main__':
    print(f"KPM-v17.4 hash: {methodology_hash()}\n")
    target = sys.argv[1] if len(sys.argv) > 1 else None
    if target:
        targets = [target]
    else:
        ward_dir = REPO / 'data' / 'ward_data'
        targets = sorted({p.stem.replace('_history','') for p in ward_dir.glob('*_history.json')})
    for slug in targets:
        pred = predict_council_v17_4(slug)
        if pred.get('error'):
            print(f"[skip] {slug}: {pred['error']}")
            continue
        print(f"  {slug:24s}: {pred['predicted_council_winner']:25s} (largest {pred['largest_party_share_pct']}%)")
