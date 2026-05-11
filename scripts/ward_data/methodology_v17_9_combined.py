"""KPM v17.9 = v17.8 (Brexit-extended) + per-ward Independent surge.

Combines the two empirically validated extensions:
- v17.8's Brexit-Reform-target detection (catches Wakefield)
- v17.7-io's Census Muslim>=60% Indep override (catches 6 more Indep wards)

This is the current PRODUCTION methodology if both extensions are
beneficial in combination.
"""
from __future__ import annotations
import json, hashlib, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.ward_data.methodology_v17_5_council_reform import is_reform_emerging_council  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_3_reform_no_incumbency import predict_ward_v17_3  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_7_indep_only import is_indep_surge_ward  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_8_brexit import is_brexit_reform_target  # type: ignore[import-not-found]

WARD = REPO / 'data' / 'ward_data'

def predict_council_v17_9(council_slug: str) -> dict:
    history_path = WARD / f'{council_slug}_history.json'
    current_path = WARD / f'{council_slug}_2026.json'
    if not history_path.exists():
        return {'error': f'No history for {council_slug}'}
    history = json.loads(history_path.read_text())
    current = json.loads(current_path.read_text()) if current_path.exists() else None
    history_by_slug = {w['ward_slug']: w for w in history['wards']}
    current_by_slug = {w['ward_slug']: w for w in current['wards']} if current else {}

    seat_counts: dict = {}
    target = current['wards'] if current else history['wards']
    indep_wards = 0
    for w_2026 in target:
        h = history_by_slug.get(w_2026['ward_slug'])
        if not h: continue
        v3 = predict_ward_v17_3(h)
        winner = v3.predicted_winner
        if winner == 'Unknown': continue
        # Indep override
        ward_census = current_by_slug.get(w_2026['ward_slug'], {}).get('census', {})
        if is_indep_surge_ward(h, ward_census):
            winner = 'Independent'
            indep_wards += 1
        winner_count = w_2026.get('winner_count', 1) if current else h.get('prior_winner_count', 1)
        seat_counts[winner] = seat_counts.get(winner, 0) + winner_count

    total_seats = sum(seat_counts.values())
    sorted_seats = sorted(seat_counts.items(), key=lambda kv: -kv[1])
    if not sorted_seats: return {'error': 'no predictions'}
    largest, largest_n = sorted_seats[0]
    share = largest_n / total_seats
    initial_winner = largest if share >= 0.60 else 'No overall control'

    # Reform-emerging detection: prior OR brexit
    council_emerging_prior = is_reform_emerging_council(history['wards'])
    council_emerging_brexit = is_brexit_reform_target(council_slug, history['wards'])
    council_emerging = council_emerging_prior or council_emerging_brexit

    if council_emerging and initial_winner not in ('No overall control', 'Independent'):
        council_winner = 'Reform UK'
    else:
        council_winner = initial_winner

    return {
        'council_slug': council_slug,
        'methodology': {'name': 'KPM-v17.9', 'version': 'v1.9', 'hash': methodology_hash()},
        'predicted_council_winner': council_winner,
        'largest_party_share_pct': round(100 * share, 1),
        'council_emerging_via_prior_reform': council_emerging_prior,
        'council_emerging_via_brexit': council_emerging_brexit,
        'n_indep_surge_wards': indep_wards,
        'seat_counts': dict(sorted_seats),
    }

METHODOLOGY_RULES = {
    'schema_version': 'kpm-v17.9-brexit-and-indep',
    'name': 'kpm_v17_9_combined',
    'description': (
        'v17.8 (Brexit Reform-target) + v17.7-io (Census Muslim>=60% Indep '
        'surge). Combines the two empirically validated extensions on top of '
        'v17.6 base.'
    ),
    'data_sources': [
        'Democracy Club JSON API (ballots + history)',
        'ONS Census 2021 NOMIS bulk TS030 (religion)',
        'Hanretty Brexit 2016 constituency Leave estimates',
    ],
}

def methodology_hash():
    return hashlib.sha256(json.dumps(METHODOLOGY_RULES, sort_keys=True, indent=2, default=list).encode()).hexdigest()

if __name__ == '__main__':
    print(f"KPM-v17.9 hash: {methodology_hash()}\n")
    targets = sorted({p.stem.replace('_history','') for p in WARD.glob('*_history.json')})
    for slug in targets:
        pred = predict_council_v17_9(slug)
        if 'error' in pred: continue
        flags = []
        if pred['council_emerging_via_prior_reform']: flags.append('prior')
        if pred['council_emerging_via_brexit']: flags.append('brexit')
        if pred['n_indep_surge_wards']: flags.append(f'IndepW={pred["n_indep_surge_wards"]}')
        flag_str = ' [' + ','.join(flags) + ']' if flags else ''
        print(f"  {slug:24s}: {pred['predicted_council_winner']:25s} (largest {pred['largest_party_share_pct']}%){flag_str}")
