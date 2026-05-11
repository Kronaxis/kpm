"""Explain a v17.10 prediction — what signals fired, per-ward breakdown.

Usage:
  python3 -m scripts.ward_data.explain_v17_10 <council_slug>

Example:
  python3 -m scripts.ward_data.explain_v17_10 wakefield
  python3 -m scripts.ward_data.explain_v17_10 birmingham
"""
from __future__ import annotations
import json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.ward_data._slug_pretty import slug_to_pretty  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_10_ensemble import predict_council_v17_10  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_9_combined import predict_council_v17_9  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_3_reform_no_incumbency import predict_ward_v17_3  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_7_indep_only import is_indep_surge_ward  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_8_brexit import is_brexit_reform_target, council_leave_pct  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_5_council_reform import is_reform_emerging_council  # type: ignore[import-not-found]

WARD = REPO / 'data' / 'ward_data'

def explain(slug: str):
    pretty = slug_to_pretty(slug)
    history_path = WARD / f'{slug}_history.json'
    current_path = WARD / f'{slug}_2026.json'

    if not history_path.exists():
        print(f"No history file for {slug}. Run:")
        print(f"  python3 -m scripts.ward_data.ingest_dc_ward_results --council {slug}")
        print(f"  python3 -m scripts.ward_data.ingest_dc_ward_history --council {slug}")
        return

    history = json.loads(history_path.read_text())
    current = json.loads(current_path.read_text()) if current_path.exists() else None

    # Council-level signals
    council_prior_emerging = is_reform_emerging_council(history['wards'])
    brexit_pct = council_leave_pct(pretty)
    council_brexit_emerging = is_brexit_reform_target(slug, history['wards'])

    # Ward count + sample
    n_wards = len(history['wards'])

    # v17.9 + v17.10 predictions
    p9 = predict_council_v17_9(slug)
    p10 = predict_council_v17_10(slug)
    if 'error' in p10:
        print(f"Error: {p10['error']}")
        return

    print(f"\n=== v17.10 EXPLANATION for {pretty} ===\n")
    print(f"COUNCIL SIGNALS:")
    print(f"  Mean prior Reform vote share: {round(sum(w.get('prior_party_shares',{}).get('Reform UK',0) for w in history['wards'])/max(n_wards,1),1)}%")
    print(f"  → Reform-emerging via prior (≥5%): {'YES' if council_prior_emerging else 'no'}")
    print(f"  2016 Brexit Leave % (Hanretty constituency mean): {round(brexit_pct*100,1) if brexit_pct else 'no data'}%")
    print(f"  → Reform-emerging via Brexit (≥60% + Lab incumbent): {'YES' if council_brexit_emerging else 'no'}")
    print()

    if council_prior_emerging or council_brexit_emerging:
        print(f"  ⚡ COUNCIL FLAGGED as Reform-emerging (Wakefield-class)")
        print()

    print(f"PER-WARD PREDICTIONS (v17.9 base + Census Indep override):")
    print(f"  {'Ward':30s}  {'Prior winner':18s}  {'v17.3 ward':18s}  {'Signals'}")
    if current:
        current_by_slug = {w['ward_slug']: w for w in current['wards']}
        n_indep = 0; n_reform = 0; n_target = 0
        seat_summary = {}
        for w in history['wards']:
            ward_census = current_by_slug.get(w['ward_slug'], {}).get('census', {})
            v3 = predict_ward_v17_3(w)
            if v3.predicted_winner == 'Unknown': continue
            signals = []
            if v3.reform_multiplier > 1.0:
                signals.append(f"Reform mult {v3.reform_multiplier}×")
                n_target += 1
            if v3.incumbency_applied:
                signals.append(f"{v3.prior_winner} incumbency +4pp")
            if is_indep_surge_ward(w, ward_census):
                v3_winner = 'Independent (Muslim override)'
                signals.append(f"Muslim {ward_census.get('muslim_pct')}% override")
                n_indep += 1
            else:
                v3_winner = v3.predicted_winner
            if v3_winner.startswith('Reform'): n_reform += 1
            print(f"  {w['ward_name']:30s}  {w.get('prior_winning_party','?'):18s}  {v3_winner:18s}  {'; '.join(signals)}")
            seat_summary[v3_winner.split(' (')[0]] = seat_summary.get(v3_winner.split(' (')[0], 0) + 1
        print()
        print(f"PER-WARD COUNTS: {n_target} Reform-target wards, {n_indep} Indep-override wards, {n_reform} Reform-predicted")

    print()
    print(f"COUNCIL-LEVEL DECISION:")
    print(f"  v17.9 prediction:                   {p9.get('predicted_council_winner','?')}")
    print(f"  v17.9 largest party share:          {p9.get('largest_party_share_pct','?')}%")
    print(f"  v17.9 seat counts:                  {p9.get('seat_counts','?')}")
    print(f"  v15.1 fallback:                     {p10.get('v15_1_winner','?')}")
    print(f"  v17.10 chosen path:                 {p10.get('chosen_path','?')}")
    print()
    print(f"  ★ FINAL v17.10 PREDICTION: {p10['predicted_council_winner']}")
    print()
    print(f"  Methodology hash: {p10['methodology']['hash']}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("usage: explain_v17_10.py <council_slug>")
        sys.exit(1)
    explain(sys.argv[1])
