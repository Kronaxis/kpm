"""Build a comprehensive comparison table: every v17.x methodology vs v15.1
vs always-incumbent vs actual, per council and per ward.

Output: data/ward_data/comparison_table.json + data/ward_data/comparison_table.md

Contains everything needed for an audit-quality scorecard entry:
- Methodology hashes (per-ward + council)
- Per-council winner predictions
- Per-ward winner predictions
- Actual results
- Hit/miss markers
- Aggregate accuracy + Reform/Green recall
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.ward_data.methodology_v17_ward_uns import predict_ward as v17_0_ward, methodology_hash as h0  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_2_reform_weighted import predict_ward_v17_2 as v17_2_ward, methodology_hash as h2  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_3_reform_no_incumbency import predict_ward_v17_3 as v17_3_ward, predict_council_v17_3 as v17_3_council, methodology_hash as h3  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_1_council_overlay import predict_council_v17_1, methodology_hash as h1  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_ward_uns import predict_council as v17_0_council  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_6_council_override import predict_council_v17_6, methodology_hash as h6  # type: ignore[import-not-found]

WARD = REPO / 'data' / 'ward_data'
ACTUALS = REPO / 'data' / 'may7_actuals_full.json'
SCORECARD = REPO / 'data' / 'scorecard' / 'kronaxis_scorecard.json'
OUT_JSON = WARD / 'comparison_table.json'
OUT_MD = WARD / 'comparison_table.md'

def party_norm(p): return 'Liberal Democrat' if p == 'Liberal Democrats' else p
from scripts.ward_data._slug_pretty import slug_to_pretty  # type: ignore[import-not-found]

def main():
    actuals_full = json.loads(ACTUALS.read_text()).get('council_winners_actual_full', {})
    scorecard = json.loads(SCORECARD.read_text())
    v151_by_council = {p['subject']: p for p in scorecard['predictions']
                       if 'KPM-2.2' in p['methodology']['name']}

    targets = sorted({p.stem.replace('_history', '') for p in WARD.glob('*_history.json')})

    council_rows = []
    ward_rows = []
    aggregate = {
        'v17_0_ward_hits': 0, 'v17_0_ward_n': 0,
        'v17_3_ward_hits': 0, 'v17_3_ward_n': 0,
        'incumbent_ward_hits': 0,
        'reform_actual': 0, 'v17_3_reform_correct': 0,
        'green_actual': 0, 'v17_3_green_correct': 0,
        'v15_1_council_hits': 0, 'v15_1_council_n': 0,
        'v17_3_council_hits': 0, 'v17_3_council_n': 0,
    }

    for slug in targets:
        actual_path = WARD / f'{slug}_2026.json'
        history_path = WARD / f'{slug}_history.json'
        if not actual_path.exists(): continue
        actual = json.loads(actual_path.read_text())
        history = json.loads(history_path.read_text())
        h_by_slug = {w['ward_slug']: w for w in history['wards']}

        pretty = slug_to_pretty(slug)
        council_actual = actuals_full.get(pretty)
        v151_pred = (v151_by_council.get(pretty) or {}).get('predicted_winner')

        v17_3_council_full = v17_3_council(slug)
        v17_0_council_full = v17_0_council(slug)
        v17_1_council_full = predict_council_v17_1(slug)
        v17_6_council_full = predict_council_v17_6(slug)

        council_rows.append({
            'council': pretty, 'slug': slug,
            'actual': council_actual or '?',
            'v15_1': v151_pred or '?',
            'v17_0': v17_0_council_full.get('predicted_council_winner', '?'),
            'v17_1': v17_1_council_full.get('predicted_council_winner', '?'),
            'v17_3': v17_3_council_full.get('predicted_council_winner', '?'),
            'v17_3_largest_pct': v17_3_council_full.get('largest_party_share_pct', 0),
            'v17_6': v17_6_council_full.get('predicted_council_winner', '?'),
            'v17_6_emerging': v17_6_council_full.get('council_is_reform_emerging', False),
        })

        if council_actual and v151_pred:
            aggregate['v15_1_council_n'] += 1
            if v151_pred == council_actual: aggregate['v15_1_council_hits'] += 1
        if council_actual:
            aggregate['v17_3_council_n'] += 1
            if v17_3_council_full.get('predicted_council_winner') == council_actual:
                aggregate['v17_3_council_hits'] += 1
            aggregate['v17_6_council_n'] = aggregate.get('v17_6_council_n', 0) + 1
            if v17_6_council_full.get('predicted_council_winner') == council_actual:
                aggregate['v17_6_council_hits'] = aggregate.get('v17_6_council_hits', 0) + 1

        for w in actual['wards']:
            h = h_by_slug.get(w['ward_slug'])
            if not h: continue
            actual_winner = party_norm(w.get('winning_party') or '?')
            if actual_winner == '?': continue
            v0 = party_norm(v17_0_ward(h).predicted_winner)
            v3 = party_norm(v17_3_ward(h).predicted_winner)
            inc = party_norm(h.get('prior_winning_party') or '')

            ward_rows.append({
                'council': pretty, 'ward': w['ward_name'],
                'actual': actual_winner, 'v17_0': v0, 'v17_3': v3,
                'incumbent': inc, 'prior_year': h['prior_year'],
            })
            aggregate['v17_0_ward_n'] += 1; aggregate['v17_3_ward_n'] += 1
            if v0 == actual_winner: aggregate['v17_0_ward_hits'] += 1
            if v3 == actual_winner: aggregate['v17_3_ward_hits'] += 1
            if inc == actual_winner: aggregate['incumbent_ward_hits'] += 1
            if actual_winner == 'Reform UK':
                aggregate['reform_actual'] += 1
                if v3 == 'Reform UK': aggregate['v17_3_reform_correct'] += 1
            if actual_winner == 'Green':
                aggregate['green_actual'] += 1
                if v3 == 'Green': aggregate['v17_3_green_correct'] += 1

    # Compute pcts
    p = lambda h, n: round(100*h/n, 1) if n else 0
    a = aggregate
    summary = {
        'methodology_hashes': {
            'KPM-v17.0': h0(),
            'KPM-v17.1': h1(),
            'KPM-v17.2': h2(),
            'KPM-v17.3': h3(),
            'KPM-v17.6': h6(),
        },
        'sample_n_wards': a['v17_0_ward_n'],
        'sample_n_councils': a['v17_3_council_n'],
        'per_ward': {
            'v17_0_pct': p(a['v17_0_ward_hits'], a['v17_0_ward_n']),
            'v17_3_pct': p(a['v17_3_ward_hits'], a['v17_3_ward_n']),
            'always_incumbent_pct': p(a['incumbent_ward_hits'], a['v17_0_ward_n']),
        },
        'per_council': {
            'v15_1_pct': p(a['v15_1_council_hits'], a['v15_1_council_n']),
            'v17_3_pct': p(a['v17_3_council_hits'], a['v17_3_council_n']),
            'v17_6_pct': p(a.get('v17_6_council_hits', 0), a.get('v17_6_council_n', 0)),
        },
        'reform_recall_v17_3': p(a['v17_3_reform_correct'], a['reform_actual']),
        'green_recall_v17_3': p(a['v17_3_green_correct'], a['green_actual']),
    }

    out = {
        'schema_version': 'kronaxis-v17-comparison-v1',
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z'),
        'note': 'Comprehensive comparison table for all v17.x methodologies vs v15.1 vs always-incumbent. NOT yet merged into canonical scorecard. Read alongside data/ward_data/v17_scorecard_pending.json.',
        'summary': summary,
        'councils': council_rows,
        'wards': ward_rows[:300],  # cap for readability; full set is reproducible
    }
    OUT_JSON.write_text(json.dumps(out, indent=2))

    # Also write markdown table
    md = f"""# v17.x ward methodology comparison table

**Generated**: {out['generated_at']}
**Sample**: {a['v17_0_ward_n']} wards across {len(council_rows)} councils

## Methodology hashes

- KPM-v17.0: `{h0()}`
- KPM-v17.1: `{h1()}`
- KPM-v17.2: `{h2()}`
- KPM-v17.3: `{h3()}`
- **KPM-v17.6 (production)**: `{h6()}`

## Aggregate accuracy

| Layer | Methodology | Hit rate |
|---|---|---|
| Per-ward (n={a['v17_0_ward_n']}) | v17.0 | {p(a['v17_0_ward_hits'], a['v17_0_ward_n'])}% |
| Per-ward (n={a['v17_0_ward_n']}) | **v17.3** | **{p(a['v17_3_ward_hits'], a['v17_0_ward_n'])}%** |
| Per-ward (n={a['v17_0_ward_n']}) | always-incumbent | {p(a['incumbent_ward_hits'], a['v17_0_ward_n'])}% |
| Council (n={a['v15_1_council_n']}) | v15.1 | {p(a['v15_1_council_hits'], a['v15_1_council_n'])}% |
| Council (n={a['v17_3_council_n']}) | v17.3 (Reform-target wards) | {p(a['v17_3_council_hits'], a['v17_3_council_n'])}% |
| Council (n={a.get('v17_6_council_n', 0)}) | **v17.6 (council Reform override) PRODUCTION** | **{p(a.get('v17_6_council_hits', 0), a.get('v17_6_council_n', 0))}%** |

Reform UK recall (v17.3 ward-level): {a['v17_3_reform_correct']}/{a['reform_actual']} = {p(a['v17_3_reform_correct'], a['reform_actual'])}%
Green recall (v17.3 ward-level): {a['v17_3_green_correct']}/{a['green_actual']} = {p(a['v17_3_green_correct'], a['green_actual'])}%

## Per-council winner predictions

| Council | Actual | v15.1 | v17.0 | v17.1 | v17.3 | **v17.6** |
|---|---|---|---|---|---|---|
"""
    for r in council_rows:
        marks = []
        for k in ['v15_1', 'v17_0', 'v17_1', 'v17_3', 'v17_6']:
            if r['actual'] == '?':
                marks.append('?')
            elif r[k] == r['actual']:
                marks.append('✓')
            else:
                marks.append('✗')
        emerging_tag = ' (RE)' if r.get('v17_6_emerging') else ''
        md += f"| {r['council']} | {r['actual']} | {r['v15_1']} {marks[0]} | {r['v17_0']} {marks[1]} | {r['v17_1']} {marks[2]} | {r['v17_3']} {marks[3]} | **{r['v17_6']}{emerging_tag}** {marks[4]} |\n"

    OUT_MD.write_text(md)
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_MD}")
    print()
    print(f"Summary:")
    print(f"  Wards: {a['v17_0_ward_n']} v17.0={p(a['v17_0_ward_hits'], a['v17_0_ward_n'])}% v17.3={p(a['v17_3_ward_hits'], a['v17_0_ward_n'])}% incumbent={p(a['incumbent_ward_hits'], a['v17_0_ward_n'])}%")
    print(f"  Councils: v15.1={p(a['v15_1_council_hits'], a['v15_1_council_n'])}% v17.3={p(a['v17_3_council_hits'], a['v17_3_council_n'])}% v17.6={p(a.get('v17_6_council_hits', 0), a.get('v17_6_council_n', 0))}%")
    print(f"  Reform recall (v17.3): {a['v17_3_reform_correct']}/{a['reform_actual']}")
    print(f"  Green  recall (v17.3): {a['v17_3_green_correct']}/{a['green_actual']}")

if __name__ == '__main__':
    main()
