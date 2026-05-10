"""Compute scorecard metrics: hit rate, lift over baselines, by-tier, by-methodology,
calibration. Output: data/scorecard/kronaxis_scorecard_metrics.json — consumed by the
public PHP page."""
from __future__ import annotations
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

REPO = Path('/home/jason/projects/kronaxis')
INP = REPO / 'data' / 'scorecard' / 'kronaxis_scorecard.json'
OUT = REPO / 'data' / 'scorecard' / 'kronaxis_scorecard_metrics.json'

def main():
    sc = json.loads(INP.read_text())
    preds = [p for p in sc['predictions'] if 'hit' in p]
    n = len(preds)
    if n == 0:
        print("No scored predictions yet"); return

    # By methodology
    by_method = defaultdict(lambda: {'n': 0, 'hits': 0, 'pre_registered': True, 'is_backtest': False, 'examples': []})
    for p in preds:
        m = f"{p['methodology']['name']} {p['methodology']['version']}"
        by_method[m]['n'] += 1
        if p.get('hit'): by_method[m]['hits'] += 1
        if p.get('is_backtest'): by_method[m]['is_backtest'] = True

    # Compute pct + lift
    method_summary = {}
    for m, v in by_method.items():
        pct = round(100 * v['hits'] / v['n'], 1) if v['n'] else 0.0
        method_summary[m] = {
            'n': v['n'], 'hits': v['hits'], 'pct': pct,
            'is_backtest': v['is_backtest'],
        }

    # By tier (KPM-1 only since tiers are KPM-1 published)
    by_tier = defaultdict(lambda: {'n': 0, 'hits': 0})
    for p in preds:
        if p['methodology']['name'] != 'KPM-1': continue
        t = p.get('predicted_confidence', 'Unknown')
        by_tier[t]['n'] += 1
        if p.get('hit'): by_tier[t]['hits'] += 1
    tier_summary = {t: {'n': v['n'], 'hits': v['hits'], 'pct': round(100*v['hits']/v['n'],1) if v['n'] else 0.0}
                    for t, v in by_tier.items()}

    # By region (uses any methodology — they share the same councils)
    by_region = defaultdict(lambda: {'n': 0, 'hits_kpm1': 0, 'hits_v151': 0})
    region_seen_for_council = {}
    for p in preds:
        c = p['subject']
        m_name = p['methodology']['name']
        region = p.get('region', 'Unknown')
        if c not in region_seen_for_council:
            region_seen_for_council[c] = region
            by_region[region]['n'] += 1
        if p.get('hit'):
            if m_name == 'KPM-1':
                by_region[region]['hits_kpm1'] += 1
            elif 'KPM-2' in m_name:
                by_region[region]['hits_v151'] += 1
    region_summary = {r: {**v, 'pct_kpm1': round(100*v['hits_kpm1']/v['n'],1) if v['n'] else 0,
                          'pct_v151': round(100*v['hits_v151']/v['n'],1) if v['n'] else 0}
                      for r, v in by_region.items()}

    # By election kind
    by_kind = defaultdict(lambda: {'n_subjects': 0, 'methodologies': set()})
    subj_seen = set()
    for p in preds:
        k = p['kind']
        if (k, p['subject']) not in subj_seen:
            by_kind[k]['n_subjects'] += 1
            subj_seen.add((k, p['subject']))
        by_kind[k]['methodologies'].add(f"{p['methodology']['name']} {p['methodology']['version']}")
    kind_summary = {k: {'n_subjects': v['n_subjects'], 'methodologies': sorted(list(v['methodologies']))}
                    for k, v in by_kind.items()}

    # Honest baselines for context
    # Always-NOC, always-Lab, always-largest-vote-share - on the same n that v15.1 was scored
    v151_subjects_with_hits = {p['subject']: p for p in preds if 'KPM-2' in p['methodology']['name']}
    baseline_n = len(v151_subjects_with_hits)
    baseline_always_noc = sum(1 for p in v151_subjects_with_hits.values() if p.get('actual_winner') == 'No overall control')
    baseline_always_lab = sum(1 for p in v151_subjects_with_hits.values() if p.get('actual_winner') == 'Labour')
    baselines = {
        'always_noc': {'hits': baseline_always_noc, 'n': baseline_n, 'pct': round(100*baseline_always_noc/baseline_n,1) if baseline_n else 0},
        'always_labour': {'hits': baseline_always_lab, 'n': baseline_n, 'pct': round(100*baseline_always_lab/baseline_n,1) if baseline_n else 0},
    }

    # Honest miss highlights
    misses = [p for p in preds if 'KPM-2' in p['methodology']['name'] and not p.get('hit')]
    notable_misses = []
    for actual, label in [('Green', 'Green breakthrough (model did not anticipate)'),
                          ('Reform UK', 'Reform breakthrough'),
                          ('Liberal Democrat', 'Lib Dem hold/pickup')]:
        for m in misses:
            if m.get('actual_winner') == actual:
                notable_misses.append({
                    'council': m['subject'], 'predicted': m['predicted_winner'],
                    'actual': m['actual_winner'], 'category': label,
                })

    out = {
        'schema_version': 'kronaxis-scorecard-metrics-v1',
        'computed_at': datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z'),
        'totals': {'n_scored': n, 'n_predictions': len(sc['predictions'])},
        'by_methodology': method_summary,
        'by_tier_kpm1': tier_summary,
        'by_region': region_summary,
        'by_kind': kind_summary,
        'baselines': baselines,
        'notable_misses': notable_misses[:20],
    }
    OUT.write_text(json.dumps(out, indent=2))
    print(f"Wrote {OUT}")
    print(f"\nBy methodology:")
    for m, v in method_summary.items():
        bt = ' (backtest)' if v['is_backtest'] else ''
        print(f"  {m}{bt}: {v['hits']}/{v['n']} = {v['pct']}%")
    print(f"\nBaselines:")
    for k, v in baselines.items():
        print(f"  {k}: {v['hits']}/{v['n']} = {v['pct']}%")
    print(f"\nKPM-1 by tier:")
    for t, v in tier_summary.items():
        print(f"  {t}: {v['hits']}/{v['n']} = {v['pct']}%")

if __name__ == '__main__':
    main()
