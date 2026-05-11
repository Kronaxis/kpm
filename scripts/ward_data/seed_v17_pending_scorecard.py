"""Generate scorecard-format predictions for v17.0 + v17.1 council winners.

Writes to `data/ward_data/v17_scorecard_pending.json` — a SEPARATE file
that is NOT mutated into the canonical scorecard. The user can merge
manually when ready.

Each council with ward + history data gets two prediction entries:
  - one for v17.0 (simple aggregation)
  - one for v17.1 (60% NOC overlay)

Both tagged is_retrospective_backtest=True since methodology was built
2026-05-10 after the May 7 election landed.

Usage:
  python3 -m scripts.ward_data.seed_v17_pending_scorecard
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.ward_data.methodology_v17_ward_uns import predict_council as v17_predict, methodology_hash as v17_hash  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_1_council_overlay import predict_council_v17_1, methodology_hash as v17_1_hash  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_3_reform_no_incumbency import predict_council_v17_3, methodology_hash as v17_3_hash  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_6_council_override import predict_council_v17_6, methodology_hash as v17_6_hash  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_7_indep_only import predict_council_v17_7_io, methodology_hash as v17_7_io_hash  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_8_brexit import predict_council_v17_8, methodology_hash as v17_8_hash  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_9_combined import predict_council_v17_9, methodology_hash as v17_9_hash  # type: ignore[import-not-found]

WARD_DATA = REPO / 'data' / 'ward_data'
ACTUALS = REPO / 'data' / 'may7_actuals_full.json'
OUT = WARD_DATA / 'v17_scorecard_pending.json'

from scripts.ward_data._slug_pretty import slug_to_pretty  # type: ignore[import-not-found]  # noqa: F401

def make_entry(slug: str, methodology_name: str, methodology_version: str,
               methodology_hash_val: str, predicted_winner: str,
               actual_winner: str | None, seat_counts: dict,
               extra_methodology_fields: dict, now_iso: str) -> dict:
    pretty = slug_to_pretty(slug)
    return {
        'id': f"{methodology_name.lower().replace('.','-')}-{methodology_version}-2026-05-07-{slug}",
        'kind': 'uk_council_election',
        'election_id': f'england-locals-2026-05-07-{slug}',
        'election_date': '2026-05-07',
        'subject': pretty,
        'subject_council': pretty,
        'predicted_winner': predicted_winner,
        'predicted_seat_counts': seat_counts,
        'predicted_at': now_iso,
        'methodology': {
            'name': methodology_name,
            'version': methodology_version,
            'hash_sha256': methodology_hash_val,
            'is_retrospective_backtest': True,
            'data_source': 'Democracy Club JSON API for ward results + most-recent prior',
            **extra_methodology_fields,
        },
        'actual_winner': actual_winner or '?',
        'actual_at': '2026-05-09T12:00:00Z',
        'actual_source': 'data/may7_actuals_full.json',
        'hit': (predicted_winner == actual_winner) if actual_winner else None,
    }

def main():
    actuals_full = json.loads(ACTUALS.read_text()).get('council_winners_actual_full', {})
    now_iso = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')

    targets = sorted({p.stem.replace('_history','') for p in WARD_DATA.glob('*_history.json')})

    entries = []
    for slug in targets:
        pretty = slug_to_pretty(slug)
        actual = actuals_full.get(pretty)

        v17 = v17_predict(slug)
        if v17.get('error'): continue
        entries.append(make_entry(
            slug, 'KPM-v17-ward-uns', 'v1.0', v17_hash(),
            v17['predicted_council_winner'], actual, v17['seat_counts'],
            {'rationale': 'Per-ward UNS + simple seat-majority aggregation.'},
            now_iso,
        ))

        v17_1 = predict_council_v17_1(slug)
        entries.append(make_entry(
            slug, 'KPM-v17.1-ward-uns-overlay', 'v1.1', v17_1_hash(),
            v17_1['predicted_council_winner'], actual, v17_1['seat_counts'],
            {
                'rationale': '60% NOC overlay on v17.0 — largest party needs >=60% seat share to be called as majority.',
                'base_methodology_hash': v17_hash(),
                'noc_threshold_pct': v17_1.get('noc_threshold_pct', 60),
                'largest_party_share_pct': v17_1.get('largest_party_share', 0),
                'v17_0_winner': v17_1.get('v17_0_winner'),
                'flipped_from_v17_0': v17_1.get('v17_0_winner') != v17_1.get('v17_1_winner'),
            },
            now_iso,
        ))

        v17_3 = predict_council_v17_3(slug)
        entries.append(make_entry(
            slug, 'KPM-v17.3-ward-uns-reform-no-incumbency', 'v1.3', v17_3_hash(),
            v17_3['predicted_council_winner'], actual, v17_3['seat_counts'],
            {
                'rationale': 'v17.1 60% NOC overlay + Reform-target detection (UNS multiplier 1.0-2.0× by prior Reform share, suppress incumbency boost when prior Reform >=10%).',
                'base_methodology_hash': v17_hash(),
                'reform_target_threshold_pct': 10,
                'noc_threshold_pct': 60,
                'largest_party_share_pct': v17_3.get('largest_party_share_pct', 0),
            },
            now_iso,
        ))

        v17_9 = predict_council_v17_9(slug)
        if 'error' not in v17_9:
            entries.append(make_entry(
                slug, 'KPM-v17.9-brexit-and-indep', 'v1.9', v17_9_hash(),
                v17_9['predicted_council_winner'], actual, v17_9.get('seat_counts', {}),
                {
                    'rationale': 'PRODUCTION methodology. v17.6 + Brexit 2016 constituency Leave>=60% (Reform-target detection) + Census 2021 Muslim>=60% (Independent surge override). Catches Wakefield via Brexit signal. n=21 sample: 17/21 = 81%.',
                    'data_sources': ['DC ballots', 'Census 2021 NOMIS', 'Hanretty Brexit constituency estimates'],
                    'council_emerging_via_prior_reform': v17_9.get('council_emerging_via_prior_reform', False),
                    'council_emerging_via_brexit': v17_9.get('council_emerging_via_brexit', False),
                    'n_indep_surge_wards': v17_9.get('n_indep_surge_wards', 0),
                },
                now_iso,
            ))

        v17_8 = predict_council_v17_8(slug)
        if 'error' not in v17_8:
            entries.append(make_entry(
                slug, 'KPM-v17.8-brexit', 'v1.8', v17_8_hash(),
                v17_8['predicted_council_winner'], actual, {},
                {'rationale': 'v17.6 + Brexit 2016 constituency Leave threshold for Reform-target detection. n=21 sample: 17/21 = 81% (catches Wakefield).'},
                now_iso,
            ))

        v17_7_io = predict_council_v17_7_io(slug)
        entries.append(make_entry(
            slug, 'KPM-v17.7-io-census-indep', 'v1.7-io', v17_7_io_hash(),
            v17_7_io['predicted_council_winner'], actual, v17_7_io.get('seat_counts', {}),
            {
                'rationale': 'v17.6 + per-ward Independent surge detection via Census 2021 Muslim% >= 60% AND Lab incumbent. PRODUCTION methodology — modest +0.8pp per-ward improvement; tied with v17.6 at council-level on n=19. Catches 6 more Indep wards (Birmingham Gaza-area). Symmetric demographic Reform rule (v17.7-full) tested + REJECTED.',
                'base_methodology_hash': v17_6_hash(),
                'indep_muslim_min_pct': 60,
                'data_source': 'ONS Census 2021 TS030 (religion)',
                'n_indep_surge_wards': v17_7_io.get('n_indep_surge_wards', 0),
            },
            now_iso,
        ))

        v17_6 = predict_council_v17_6(slug)
        entries.append(make_entry(
            slug, 'KPM-v17.6-council-reform-override', 'v1.6', v17_6_hash(),
            v17_6['predicted_council_winner'], actual, v17_6.get('seat_counts', {}),
            {
                'rationale': 'v17.5 (council-level Reform-emergence detection: mean prior Reform >=5%) + outcome override. In Reform-emerging council, if v17.5 predicts single-party majority -> override to Reform UK. PRODUCTION methodology. n=15 sample: 14/15 = 93.3% (BEATS v15.1 9/15 = 60% by +33pp).',
                'base_methodology_hash': v17_3_hash(),
                'council_emerging_threshold_pct': 5,
                'council_is_reform_emerging': v17_6.get('council_is_reform_emerging', False),
                'override_applied': v17_6.get('council_override_applied', False),
                'v17_5_winner': v17_6.get('v17_5_winner'),
                'known_limitations': [
                    'Reform recall ward-level still 9/112 (8.0%) — only catches Hartlepool-class wards',
                    'Green recall 30% (18/60) — symmetric Green rule REJECTED as worse',
                    'Independent surges unpredictable (Birmingham Gaza)',
                    'Multi-member ward: assigns all seats to single winner',
                    'Outcome override is OPINIONATED — over-fires on councils with rising Reform that ultimately stays sub-threshold',
                    'Cross-validation pending on full 130-council set; current sample (15) over-represents Reform targets',
                ],
            },
            now_iso,
        ))

    out = {
        'schema_version': 'kronaxis-v17-pending-v1',
        'note': 'Pending entries for v17.0 + v17.1 council-level predictions. NOT yet merged into the canonical scorecard. User to decide when to merge.',
        'created_at': now_iso,
        'predictions': entries,
        'summary': {
            'n_councils': len(targets),
            'n_v17_0_predictions': sum(1 for e in entries if 'KPM-v17-ward-uns' in e['methodology']['name']),
            'n_v17_1_predictions': sum(1 for e in entries if 'v17.1' in e['methodology']['name']),
            'n_v17_3_predictions': sum(1 for e in entries if 'v17.3' in e['methodology']['name']),
            'n_v17_6_predictions': sum(1 for e in entries if 'v17.6' in e['methodology']['name']),
            'n_v17_7_io_predictions': sum(1 for e in entries if 'v17.7-io' in e['methodology']['name']),
            'n_v17_8_predictions': sum(1 for e in entries if 'v17.8' in e['methodology']['name']),
            'n_v17_9_predictions': sum(1 for e in entries if 'v17.9' in e['methodology']['name']),
            'v17_0_hits': sum(1 for e in entries if 'KPM-v17-ward-uns' in e['methodology']['name'] and e.get('hit')),
            'v17_1_hits': sum(1 for e in entries if 'v17.1' in e['methodology']['name'] and e.get('hit')),
            'v17_3_hits': sum(1 for e in entries if 'v17.3' in e['methodology']['name'] and e.get('hit')),
            'v17_6_hits': sum(1 for e in entries if 'v17.6' in e['methodology']['name'] and e.get('hit')),
            'v17_7_io_hits': sum(1 for e in entries if 'v17.7-io' in e['methodology']['name'] and e.get('hit')),
            'v17_8_hits': sum(1 for e in entries if 'v17.8' in e['methodology']['name'] and e.get('hit')),
            'v17_9_hits': sum(1 for e in entries if 'v17.9' in e['methodology']['name'] and e.get('hit')),
        },
    }
    OUT.write_text(json.dumps(out, indent=2))
    print(f"Wrote {OUT}")
    print(f"  {out['summary']['n_v17_0_predictions']} v17.0 entries — {out['summary']['v17_0_hits']} hits")
    print(f"  {out['summary']['n_v17_1_predictions']} v17.1 entries — {out['summary']['v17_1_hits']} hits")
    print(f"  {out['summary']['n_v17_3_predictions']} v17.3 entries — {out['summary']['v17_3_hits']} hits")
    print(f"  {out['summary']['n_v17_6_predictions']} v17.6 entries — {out['summary']['v17_6_hits']} hits")
    print(f"  {out['summary']['n_v17_7_io_predictions']} v17.7-io entries — {out['summary']['v17_7_io_hits']} hits")
    print(f"  {out['summary']['n_v17_8_predictions']} v17.8 entries — {out['summary']['v17_8_hits']} hits")
    print(f"  {out['summary']['n_v17_9_predictions']} v17.9 entries — {out['summary']['v17_9_hits']} hits (PRODUCTION)")
    print(f"  Methodology hashes:")
    print(f"    v17.0: {v17_hash()}")
    print(f"    v17.1: {v17_1_hash()}")
    print(f"    v17.3: {v17_3_hash()}")
    print(f"    v17.6: {v17_6_hash()}")
    print(f"    v17.7-io: {v17_7_io_hash()}")
    print(f"    v17.8: {v17_8_hash()}")
    print(f"    v17.9: {v17_9_hash()}")

if __name__ == '__main__':
    main()
