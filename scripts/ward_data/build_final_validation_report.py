"""Build the final v17.x cross-validation report.

Outputs:
  data/ward_data/FINAL_VALIDATION_REPORT.md - human-readable comparison
  data/ward_data/FINAL_VALIDATION_REPORT.json - machine-readable

Compares v15.1 + all v17.x methodologies on the largest available
sample, with per-council breakdown and per-party recall.
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
import sys
from collections import defaultdict

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.ward_data._slug_pretty import slug_to_pretty  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_ward_uns import predict_council as v17_0_council, methodology_hash as h0  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_1_council_overlay import predict_council_v17_1, methodology_hash as h1  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_3_reform_no_incumbency import predict_council_v17_3, methodology_hash as h3  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_6_council_override import predict_council_v17_6, methodology_hash as h6  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_7_indep_only import predict_council_v17_7_io, methodology_hash as h7  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_8_brexit import predict_council_v17_8, methodology_hash as h8  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_9_combined import predict_council_v17_9, methodology_hash as h9  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_10_ensemble import predict_council_v17_10, methodology_hash as h10  # type: ignore[import-not-found]

WARD = REPO / 'data' / 'ward_data'
ACTUALS = REPO / 'data' / 'may7_actuals_full.json'
SCORECARD = REPO / 'data' / 'scorecard' / 'kronaxis_scorecard.json'

def main():
    actuals_full = json.loads(ACTUALS.read_text()).get('council_winners_actual_full', {})
    scorecard = json.loads(SCORECARD.read_text())
    v151_by_council = {p['subject']: p for p in scorecard['predictions']
                       if 'KPM-2.2' in p['methodology']['name']}

    targets = sorted({p.stem.replace('_history','') for p in WARD.glob('*_history.json')})

    rows = []
    methodology_hits = defaultdict(int)
    methodology_n = defaultdict(int)

    for slug in targets:
        pretty = slug_to_pretty(slug)
        actual = actuals_full.get(pretty)
        if not actual: continue

        try:
            preds = {
                'v15.1': (v151_by_council.get(pretty) or {}).get('predicted_winner', '?'),
                'v17.0': v17_0_council(slug).get('predicted_council_winner', '?'),
                'v17.1': predict_council_v17_1(slug).get('predicted_council_winner', '?'),
                'v17.3': predict_council_v17_3(slug).get('predicted_council_winner', '?'),
                'v17.6': predict_council_v17_6(slug).get('predicted_council_winner', '?'),
                'v17.7-io': predict_council_v17_7_io(slug).get('predicted_council_winner', '?'),
                'v17.8': predict_council_v17_8(slug).get('predicted_council_winner', '?'),
                'v17.9': predict_council_v17_9(slug).get('predicted_council_winner', '?'),
                'v17.10': predict_council_v17_10(slug).get('predicted_council_winner', '?'),
            }
        except Exception as e:
            print(f"skip {slug}: {e}")
            continue

        for m, p in preds.items():
            if p == '?': continue
            methodology_n[m] += 1
            if p == actual:
                methodology_hits[m] += 1

        rows.append({'council': pretty, 'slug': slug, 'actual': actual, 'preds': preds})

    # Summary table
    summary_lines = []
    summary_lines.append('| Methodology | Hits | Sample n | % | Lift over v15.1 |')
    summary_lines.append('|---|---|---|---|---|')
    base_pct = round(100*methodology_hits['v15.1']/methodology_n['v15.1'], 1) if methodology_n['v15.1'] else 0
    for m in ['v15.1', 'v17.0', 'v17.1', 'v17.3', 'v17.6', 'v17.7-io', 'v17.8', 'v17.9', 'v17.10']:
        n = methodology_n[m]; h = methodology_hits[m]
        pct = round(100*h/n, 1) if n else 0
        lift = round(pct - base_pct, 1)
        lift_str = f'+{lift}pp' if lift > 0 else (f'{lift}pp' if lift else 'baseline')
        marker = ' **PRODUCTION**' if m == 'v17.10' else ''
        summary_lines.append(f'| {m}{marker} | {h} | {n} | {pct}% | {lift_str} |')

    # Hashes
    hashes = {
        'KPM-2.2 v15.1 (current canonical scorecard)': '52df676e792c…',
        'KPM-v17.0': h0(),
        'KPM-v17.1': h1(),
        'KPM-v17.3': h3(),
        'KPM-v17.6': h6(),
        'KPM-v17.7-io': h7(),
        'KPM-v17.8': h8(),
        'KPM-v17.9': h9(),
        'KPM-v17.10 (PRODUCTION)': h10(),
    }

    # Per-council
    council_lines = ['| Council | Actual | v15.1 | v17.6 | v17.9 | **v17.10** |',
                     '|---|---|---|---|---|---|']
    for r in rows:
        cells = [r['council'], r['actual']]
        for m in ['v15.1', 'v17.6', 'v17.9', 'v17.10']:
            p = r['preds'].get(m, '?')
            mark = '✓' if p == r['actual'] else '✗' if p != '?' else '?'
            cells.append(f'{p} {mark}')
        council_lines.append('| ' + ' | '.join(cells) + ' |')

    # Build markdown
    md = f"""# KPM v17.x Final Cross-Validation Report

**Generated**: {datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')}
**Sample**: {len(rows)} councils with both v15.1 prediction + v17.x ward data + actual May 7 result

## Production methodology

**KPM-v17.10 ENSEMBLE** (`{h10()}`) — uses v17.9 (ward-aware + Census + Brexit) when confident OR Reform-emerging override fires; falls back to v15.1 (council-level fragmentation) when v17.9 in mid-confidence zone.

## Aggregate accuracy

{chr(10).join(summary_lines)}

## Per-council comparison

{chr(10).join(council_lines)}

## Methodology hashes

{chr(10).join(f'- {k}: `{v}`' for k, v in hashes.items())}

## Caveats

1. **Sample is biased.** Selected to test Reform-target signals.
   v15.1's published track record on n=130 is 59.2% — different sample.
2. **v17.9's outcome override is OPINIONATED.** Could over-fire on Tory
   shires with high Leave % but no actual Reform interest.
3. **Multi-member ward seats** treated as winner-take-all in v17 — over-predicts
   majorities.
4. **Wolverhampton remains structurally unpredictable** from priors+Census+Brexit.
   Actual NOC; v17.9 says Reform UK (Brexit fired but reality was Reform-fragmented-Lab).

## Next steps

1. Cross-validate on full 130-council May 7 sample (overnight ingest in progress).
2. Stress-test on Conservative shires (untested in current sample).
3. Build multi-member ward seat allocation (defer to v18).
"""

    out_md = WARD / 'FINAL_VALIDATION_REPORT.md'
    out_json = WARD / 'FINAL_VALIDATION_REPORT.json'
    out_md.write_text(md)
    out_json.write_text(json.dumps({
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z'),
        'sample_n': len(rows),
        'methodology_hits': dict(methodology_hits),
        'methodology_n': dict(methodology_n),
        'methodology_hashes': hashes,
        'council_predictions': rows,
    }, indent=2))
    print(f"Wrote {out_md}")
    print(f"Wrote {out_json}")
    print()
    for m in ['v15.1', 'v17.0', 'v17.1', 'v17.3', 'v17.6', 'v17.7-io', 'v17.8', 'v17.9', 'v17.10']:
        n = methodology_n[m]; h = methodology_hits[m]
        pct = round(100*h/n, 1) if n else 0
        print(f"  {m:12s}: {h:>3d}/{n:<3d} = {pct:>5}%")

if __name__ == '__main__':
    main()
