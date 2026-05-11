"""KPM v17.7-indep-only = v17.6 + per-ward Independent surge detection ONLY.

v17.7-full added BOTH demographic Reform-target detection AND Indep-surge.
The Reform demographic rule over-fired (Rochdale + Tameside misses).

This variant keeps ONLY the per-ward Independent surge rule:
  ward Muslim% > 50% AND prior winner = Lab → predict Independent

Hypothesis: catches Birmingham wards without false-positives elsewhere.
"""
from __future__ import annotations
import json, hashlib, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.ward_data.methodology_v17_6_council_override import predict_council_v17_6  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_5_council_reform import is_reform_emerging_council  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_3_reform_no_incumbency import predict_ward_v17_3  # type: ignore[import-not-found]

WARD = REPO / 'data' / 'ward_data'
INDEP_MUSLIM_MIN = 60.0  # tightened from 50% after empirical sweep on n=19

def is_indep_surge_ward(history_ward: dict, current_census: dict) -> bool:
    if not current_census.get('matched'): return False
    if current_census.get('muslim_pct', 0) < INDEP_MUSLIM_MIN: return False
    if history_ward.get('prior_winning_party') != 'Labour': return False
    return True

def predict_council_v17_7_io(council_slug: str) -> dict:
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
        v17_3_pred = predict_ward_v17_3(h)
        winner = v17_3_pred.predicted_winner
        if winner == 'Unknown': continue
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

    # Use v17.6 council emergence (prior-only, NOT demographic)
    council_emerging = is_reform_emerging_council(history['wards'])

    initial_winner = largest if share >= 0.60 else 'No overall control'

    if council_emerging and initial_winner != 'No overall control' and initial_winner != 'Independent':
        council_winner = 'Reform UK'
    else:
        council_winner = initial_winner

    return {
        'council_slug': council_slug,
        'methodology': {'name': 'KPM-v17.7-io', 'version': 'v1.7-io', 'hash': methodology_hash()},
        'total_seats_predicted': total_seats,
        'seat_counts': dict(sorted_seats),
        'predicted_council_winner': council_winner,
        'largest_party_share_pct': round(100 * share, 1),
        'n_indep_surge_wards': indep_wards,
    }

METHODOLOGY_RULES = {
    'schema_version': 'kpm-v17.7-indep-only-v1',
    'name': 'kpm_v17_7_indep_only',
    'description': (
        'v17.6 + per-ward Independent surge detection (Muslim>50% + Lab incumbent → '
        'predict Independent). Drops the v17.7-full demographic Reform-target rule '
        'because it over-fired in n=18 testing (Rochdale + Tameside false positives).'
    ),
    'indep_surge_muslim_min_pct': INDEP_MUSLIM_MIN,
    'data_source': 'ONS Census 2021 TS030 (religion) ward-level',
}

def methodology_hash():
    canonical = json.dumps(METHODOLOGY_RULES, sort_keys=True, indent=2, default=list)
    return hashlib.sha256(canonical.encode()).hexdigest()

if __name__ == '__main__':
    print(f"KPM-v17.7-io hash: {methodology_hash()}\n")
    target = sys.argv[1] if len(sys.argv) > 1 else None
    if target:
        targets = [target]
    else:
        targets = sorted({p.stem.replace('_history','') for p in WARD.glob('*_history.json')})
    for slug in targets:
        pred = predict_council_v17_7_io(slug)
        if pred.get('error'):
            print(f"[skip] {slug}: {pred['error']}")
            continue
        indep = f' (IndepWards={pred["n_indep_surge_wards"]})' if pred['n_indep_surge_wards'] else ''
        print(f"  {slug:24s}: {pred['predicted_council_winner']:25s} (largest {pred['largest_party_share_pct']}%){indep}")
