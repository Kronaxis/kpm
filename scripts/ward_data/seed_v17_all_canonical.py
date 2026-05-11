"""Seed all v17.x methodology predictions directly into canonical scorecard.

Runs every v17.x methodology on every council with ward+history data,
builds scorecard-format entries, appends to canonical kronaxis_scorecard.json.
Idempotent on id.

Should be added to scripts/scorecard/refresh.sh so v17 entries survive
refresh cycles. v17.10 is the PRODUCTION methodology; others are kept
for transparency.
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.ward_data._slug_pretty import slug_to_pretty  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_ward_uns import predict_council as v17_0_pred, methodology_hash as v17_0_hash  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_1_council_overlay import predict_council_v17_1, methodology_hash as v17_1_hash  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_3_reform_no_incumbency import predict_council_v17_3, methodology_hash as v17_3_hash  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_6_council_override import predict_council_v17_6, methodology_hash as v17_6_hash  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_7_indep_only import predict_council_v17_7_io, methodology_hash as v17_7_hash  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_8_brexit import predict_council_v17_8, methodology_hash as v17_8_hash  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_9_combined import predict_council_v17_9, methodology_hash as v17_9_hash  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_10_ensemble import predict_council_v17_10, methodology_hash as v17_10_hash  # type: ignore[import-not-found]

WARD = REPO / 'data' / 'ward_data'
SCORECARD = REPO / 'data' / 'scorecard' / 'kronaxis_scorecard.json'
ACTUALS = REPO / 'data' / 'may7_actuals_full.json'

METHODOLOGIES = [
    ('KPM-v17-ward-uns', 'v1.0', v17_0_pred, v17_0_hash,
     'Baseline ward-UNS. n=21 sample = 11/21 = 52.4%.'),
    ('KPM-v17.1-ward-uns-overlay', 'v1.1', predict_council_v17_1, v17_1_hash,
     '60% NOC overlay on v17.0. n=21 = 14/21 = 66.7%.'),
    ('KPM-v17.3-ward-uns-reform-no-incumbency', 'v1.3', predict_council_v17_3, v17_3_hash,
     'v17.1 + Reform-target detection + suppress incumbency in Reform-target wards. n=21 = 14/21 = 66.7%.'),
    ('KPM-v17.6-council-reform-override', 'v1.6', predict_council_v17_6, v17_6_hash,
     'v17.3 + council-level Reform-emergence outcome override. n=21 = 16/21 = 76.2%.'),
    ('KPM-v17.7-io-census-indep', 'v1.7-io', predict_council_v17_7_io, v17_7_hash,
     'v17.6 + per-ward Indep override (Census Muslim>=60%). n=21 = 16/21 = 76.2%.'),
    ('KPM-v17.8-brexit', 'v1.8', predict_council_v17_8, v17_8_hash,
     'v17.6 + Brexit 2016 council Leave>=60% Reform-target. n=21 = 17/21 = 81.0%.'),
    ('KPM-v17.9-brexit-and-indep', 'v1.9', predict_council_v17_9, v17_9_hash,
     'v17.8 + v17.7-io combined. n=21 = 17/21 = 81.0%.'),
    ('KPM-v17.10-ensemble', 'v1.10', predict_council_v17_10, v17_10_hash,
     'PRODUCTION ENSEMBLE: v17.9 when confident OR Reform-emerging fires; v15.1 fallback otherwise. n=37 = 28/37 = 75.7%.'),
]

def main():
    sc = json.loads(SCORECARD.read_text())
    actuals = json.loads(ACTUALS.read_text()).get('council_winners_actual_full', {})
    existing_ids = {p['id'] for p in sc['predictions']}
    now_iso = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')

    targets = sorted({p.stem.replace('_history','') for p in WARD.glob('*_history.json')})
    n_added = 0
    by_method = {}
    for mname, mver, predict_fn, hash_fn, rationale in METHODOLOGIES:
        method_hash = hash_fn()
        is_production = (mname == 'KPM-v17.10-ensemble')
        for slug in targets:
            pretty = slug_to_pretty(slug)
            actual = actuals.get(pretty)
            if not actual: continue
            try:
                pred = predict_fn(slug)
                if 'error' in pred: continue
                winner = pred.get('predicted_council_winner', '?')
                if winner == '?': continue
            except Exception:
                continue

            slug_safe = mname.lower().replace('.','-').replace(' ','-')
            entry_id = f"{slug_safe}-2026-05-07-{slug}"
            if entry_id in existing_ids: continue

            hit = winner == actual
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
                    'name': mname,
                    'version': mver,
                    'hash_sha256': method_hash,
                    'is_retrospective_backtest': True,
                    'is_production': is_production,
                    'rationale': rationale,
                    'data_source': 'Democracy Club JSON API ward priors + ONS Census 2021 NOMIS bulk + Hanretty Brexit 2016',
                },
                'actual_winner': actual,
                'actual_at': '2026-05-09T12:00:00Z',
                'hit': hit,
            })
            existing_ids.add(entry_id)
            n_added += 1
            by_method.setdefault(mname, [0, 0])
            by_method[mname][0] += 1
            if hit: by_method[mname][1] += 1

    sc['last_updated'] = now_iso
    SCORECARD.write_text(json.dumps(sc, indent=2))
    print(f"Appended {n_added} v17.x entries")
    print(f"Scorecard now: {len(sc['predictions'])} predictions")
    for m, (n, h) in sorted(by_method.items()):
        print(f"  {m}: {h}/{n} = {round(100*h/n,1) if n else 0}%")

if __name__ == '__main__':
    main()
