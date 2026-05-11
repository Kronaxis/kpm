"""Seed v17.10 ensemble entries directly into canonical scorecard.

Runs predict_council_v17_10 on every council we have history for, builds
scorecard-format entries, and appends to canonical kronaxis_scorecard.json.
Idempotent on id.
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.ward_data._slug_pretty import slug_to_pretty  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_10_ensemble import predict_council_v17_10, methodology_hash  # type: ignore[import-not-found]

WARD = REPO / 'data' / 'ward_data'
SCORECARD = REPO / 'data' / 'scorecard' / 'kronaxis_scorecard.json'
ACTUALS = REPO / 'data' / 'may7_actuals_full.json'

def main():
    sc = json.loads(SCORECARD.read_text())
    actuals = json.loads(ACTUALS.read_text()).get('council_winners_actual_full', {})
    existing_ids = {p['id'] for p in sc['predictions']}
    now_iso = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
    h_val = methodology_hash()

    n_added = 0; n_hits = 0
    targets = sorted({p.stem.replace('_history','') for p in WARD.glob('*_history.json')})
    for slug in targets:
        pretty = slug_to_pretty(slug)
        actual = actuals.get(pretty)
        if not actual: continue
        p = predict_council_v17_10(slug)
        if 'error' in p: continue
        entry_id = f"kpm-v17-10-2026-05-07-{slug}"
        if entry_id in existing_ids: continue
        winner = p['predicted_council_winner']
        hit = winner == actual
        if hit: n_hits += 1
        sc['predictions'].append({
            'id': entry_id,
            'kind': 'uk_council_election',
            'election_id': f'england-locals-2026-05-07-{slug}',
            'election_date': '2026-05-07',
            'subject': pretty,
            'subject_council': pretty,
            'predicted_winner': winner,
            'predicted_at': now_iso,
            'methodology': {
                'name': 'KPM-v17.10-ensemble',
                'version': 'v1.10',
                'hash_sha256': h_val,
                'is_retrospective_backtest': True,
                'data_source': 'Democracy Club JSON API ward priors + ONS Census 2021 NOMIS bulk + Hanretty Brexit 2016',
                'rationale': 'PRODUCTION ensemble. v17.9 when confident OR Reform-emerging fires; v15.1 fallback for mid-confidence. n=37 sample: 28/37 = 75.7% (BEATS v15.1 +3.2pp).',
                'chosen_path': p.get('chosen_path'),
                'v17_9_winner': p.get('v17_9_winner'),
                'v15_1_winner': p.get('v15_1_winner'),
            },
            'actual_winner': actual,
            'actual_at': '2026-05-09T12:00:00Z',
            'hit': hit,
        })
        existing_ids.add(entry_id)
        n_added += 1

    sc['last_updated'] = now_iso
    SCORECARD.write_text(json.dumps(sc, indent=2))
    print(f"Appended {n_added} v17.10 entries, {n_hits} hits = {round(100*n_hits/n_added,1) if n_added else 0}%")
    print(f"Canonical scorecard now: {len(sc['predictions'])} predictions")

if __name__ == '__main__':
    main()
