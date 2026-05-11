"""Score v17 ward predictions against actuals + always-incumbent baseline.

Compares for the same n=119-ward Birmingham+Sheffield+Manchester sample:
  - v16 LLM-derived per-ward (already measured: 21.0%)
  - v17 ward-UNS                   (new — this is what we just built)
  - Always-incumbent baseline       (predict prior winner verbatim)

The point: v17 must beat both v16 AND always-incumbent to be worth using.
If always-incumbent matches or beats v17, the UNS layer adds no signal.

Usage:
  python3 -m scripts.ward_data.score_v17_vs_baselines
  python3 -m scripts.ward_data.score_v17_vs_baselines --council birmingham
"""
from __future__ import annotations
import argparse, json
from collections import defaultdict
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.ward_data.methodology_v17_ward_uns import predict_ward  # type: ignore[import-not-found]

WARD_DATA = REPO / 'data' / 'ward_data'

def normalise_key(s: str) -> str:
    return s.lower().replace('&', 'and').replace("'", '').replace('-', ' ').strip()

def party_norm(p: str) -> str:
    if p == 'Liberal Democrats': return 'Liberal Democrat'
    return p

def score_council(slug: str) -> dict:
    actual_path = WARD_DATA / f'{slug}_2026.json'
    history_path = WARD_DATA / f'{slug}_history.json'
    if not actual_path.exists() or not history_path.exists():
        return {'error': f'missing data for {slug}'}

    actual = json.loads(actual_path.read_text())
    history = json.loads(history_path.read_text())

    history_by_slug = {w['ward_slug']: w for w in history['wards']}
    actual_by_slug = {w['ward_slug']: w for w in actual['wards']}

    n_matched = 0
    v17_hits = 0
    incumbent_hits = 0
    incumbent_can_predict = 0
    v17_predictions = []
    misses = []

    for slug_w in actual_by_slug:
        h = history_by_slug.get(slug_w)
        if not h: continue
        a = actual_by_slug[slug_w]
        n_matched += 1

        actual_winner = party_norm(a.get('winning_party') or '?')
        if actual_winner == '?': continue

        # v17 prediction
        v17_pred = predict_ward(h)
        v17_winner = party_norm(v17_pred.predicted_winner)
        v17_hit = v17_winner == actual_winner
        if v17_hit: v17_hits += 1
        v17_predictions.append({
            'ward': a['ward_name'], 'predicted': v17_winner,
            'actual': actual_winner, 'hit': v17_hit,
            'prior_year': v17_pred.prior_year,
        })

        # Always-incumbent baseline
        prior_winner = party_norm(h.get('prior_winning_party') or '')
        if prior_winner:
            incumbent_can_predict += 1
            if prior_winner == actual_winner:
                incumbent_hits += 1

        if not v17_hit:
            misses.append({
                'ward': a['ward_name'], 'v17_predicted': v17_winner,
                'incumbent_predicted': prior_winner,
                'actual': actual_winner, 'prior_year': v17_pred.prior_year,
            })

    return {
        'council': slug,
        'n_matched': n_matched,
        'v17_hits': v17_hits,
        'v17_pct': round(100*v17_hits/n_matched, 1) if n_matched else 0,
        'incumbent_hits': incumbent_hits,
        'incumbent_pct': round(100*incumbent_hits/n_matched, 1) if n_matched else 0,
        'misses_sample': misses[:5],
        'predictions': v17_predictions,
    }

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--council', help='Single council slug')
    args = ap.parse_args()

    if args.council:
        targets = [args.council]
    else:
        targets = sorted({p.stem.replace('_history','') for p in WARD_DATA.glob('*_history.json')})

    overall = {'matched': 0, 'v17_hits': 0, 'incumbent_hits': 0}
    summaries = []
    for slug in targets:
        s = score_council(slug)
        if s.get('error'):
            print(f"[skip] {slug}: {s['error']}")
            continue
        summaries.append(s)
        overall['matched'] += s['n_matched']
        overall['v17_hits'] += s['v17_hits']
        overall['incumbent_hits'] += s['incumbent_hits']

    print(f"\n=== v17 ward-UNS vs always-incumbent vs (recall: v16 LLM = 21.0%) ===")
    print(f"{'Council':22s}  {'matched':>8s}  {'v17':>10s}  {'incumbent':>10s}  {'lift v17 over incumbent':>25s}")
    print('-' * 90)
    for s in summaries:
        lift = round(s['v17_pct'] - s['incumbent_pct'], 1)
        lift_str = f"+{lift}pp" if lift > 0 else (f"{lift}pp" if lift else " 0pp")
        print(f"  {s['council']:22s}  {s['n_matched']:>8d}  {s['v17_pct']:>9}%  {s['incumbent_pct']:>9}%  {lift_str:>25}")
    print('-' * 90)
    if overall['matched']:
        v17_overall = round(100*overall['v17_hits']/overall['matched'], 1)
        inc_overall = round(100*overall['incumbent_hits']/overall['matched'], 1)
        lift = round(v17_overall - inc_overall, 1)
        lift_str = f"+{lift}pp" if lift > 0 else (f"{lift}pp" if lift else " 0pp")
        print(f"  {'OVERALL':22s}  {overall['matched']:>8d}  {v17_overall:>9}%  {inc_overall:>9}%  {lift_str:>25}")
        print()
        print(f"  Comparison to v16 LLM ({21.0}%): v17 = {v17_overall}% (+{round(v17_overall - 21.0, 1)}pp)")
        print(f"  Comparison to v15.1 council baseline (59.2% on different councils):")
        print(f"    v17 ward predictions aggregated to council level: see methodology_v17_ward_uns.predict_council()")

    # Show some misses
    print()
    print("Sample misses (v17 vs always-incumbent comparison):")
    for s in summaries[:3]:
        for m in s['misses_sample'][:3]:
            print(f"  [{s['council']}] {m['ward']:30s} v17={m['v17_predicted']:18s} incumbent={m['incumbent_predicted']:18s} actual={m['actual']:18s} (prior {m['prior_year']})")

if __name__ == '__main__':
    main()
