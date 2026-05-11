"""Score the existing v16 per-ward predictions against real Democracy Club ward
results.

Reads:
  - data/ward_level_projections.json (v16's LLM-derived per-ward predictions)
  - data/ward_data/{council}_2026.json (real ward results from DC ingest)

Computes per-council and overall:
  - Per-ward winner accuracy (predicted_winning_party == actual_winning_party)
  - Vote-share calibration (MAE per party share)
  - Sample-size-weighted overall accuracy

This is the FIRST objective measurement of how well v16's per-ward output
actually matches reality. The earlier v16 NEGATIVE finding only checked
whether AGGREGATING those predictions beat v15.1 at the council level —
this checks the ward layer directly. If per-ward accuracy is poor, no
aggregation will save it.

Usage:
  python3 -m scripts.ward_data.score_ward_predictions
  python3 -m scripts.ward_data.score_ward_predictions --council birmingham
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WARD_PRED = REPO / 'data' / 'ward_level_projections.json'
WARD_DATA_DIR = REPO / 'data' / 'ward_data'

def load_predictions() -> dict[str, list]:
    """Return dict {council_name (capitalised): [ward_pred dicts]}."""
    d = json.loads(WARD_PRED.read_text())
    return d.get('ward_results', {})

def load_actuals(council_slug: str) -> dict | None:
    p = WARD_DATA_DIR / f"{council_slug}_2026.json"
    if not p.exists(): return None
    return json.loads(p.read_text())

def normalise_ward_key(s: str) -> str:
    """Match ward names across pred/actual case+punct variations."""
    return s.lower().replace('&', 'and').replace("'", '').replace('-', ' ').strip()

def score_council(council_pretty: str, predictions: list, actuals: dict) -> dict:
    """Match wards by name and compare winners."""
    actual_by_key = {normalise_ward_key(w['ward_name']): w for w in actuals['wards']}
    matched = 0; winner_hit = 0; share_mae_sum = 0.0; share_mae_count = 0
    miss_examples = []
    for p in predictions:
        key = normalise_ward_key(p['ward'])
        a = actual_by_key.get(key)
        if not a: continue
        matched += 1
        actual_winner = a['winning_party']
        pred_winner = p['winner']
        # Normalise pred party ("Liberal Democrats" → "Liberal Democrat") to match
        if pred_winner == 'Liberal Democrats': pred_winner = 'Liberal Democrat'
        if actual_winner == 'Liberal Democrats': actual_winner = 'Liberal Democrat'
        hit = pred_winner == actual_winner
        if hit:
            winner_hit += 1
        else:
            miss_examples.append({
                'ward': p['ward'],
                'predicted': pred_winner,
                'actual': actual_winner,
                'predicted_margin': p.get('margin_pp'),
            })
        # Vote-share MAE - compare predicted shares vs actual shares
        for party, pred_share in p.get('shares', {}).items():
            party_norm = 'Liberal Democrat' if party == 'Liberal Democrats' else party
            actual_share = a['party_shares'].get(party_norm, 0.0)
            share_mae_sum += abs(pred_share - actual_share)
            share_mae_count += 1
    return {
        'council': council_pretty,
        'matched': matched,
        'predictions_total': len(predictions),
        'actuals_total': len(actuals['wards']),
        'winner_hits': winner_hit,
        'winner_pct': round(100*winner_hit/matched, 1) if matched else 0,
        'share_mae': round(share_mae_sum / share_mae_count, 2) if share_mae_count else 0,
        'misses_sample': miss_examples[:5],
    }

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--council', help='Single council slug to score')
    args = ap.parse_args()

    preds = load_predictions()
    # Build slug → pretty mapping by walking ward_data dir
    available_actuals = {p.stem.replace('_2026',''): p for p in WARD_DATA_DIR.glob('*_2026.json')}
    if not available_actuals:
        print(f"No actuals in {WARD_DATA_DIR}. Run ingest_dc_ward_results first.")
        return

    if args.council:
        targets = [args.council]
    else:
        targets = list(available_actuals.keys())

    summaries = []
    overall_matched = 0; overall_hit = 0; overall_mae_sum = 0; overall_mae_n = 0
    for slug in targets:
        actual = load_actuals(slug)
        if not actual:
            print(f"[skip] {slug}: no actuals file")
            continue
        # Pred dict is keyed by capitalised council name; try several mappings
        pretty_candidates = [
            slug.replace('-', ' ').title(),
            slug.replace('-and-', ' and ').title(),  # "barking-and-dagenham" → "Barking and Dagenham"
        ]
        pretty = None
        pred = None
        for cand in pretty_candidates:
            if cand in preds:
                pretty = cand
                pred = preds[cand]
                break
        if not pred:
            # Try direct lookup: predictions dict keys
            for k in preds:
                if normalise_ward_key(k) == normalise_ward_key(slug.replace('-', ' ')):
                    pretty = k
                    pred = preds[k]
                    break
        if not pred or not pretty:
            print(f"[skip] {slug}: no v16 predictions found (tried {pretty_candidates})")
            continue
        s = score_council(pretty, pred, actual)
        summaries.append(s)
        overall_matched += s['matched']
        overall_hit += s['winner_hits']
        overall_mae_n += 1
        overall_mae_sum += s['share_mae']

    print(f"\n=== v16 ward-prediction accuracy vs Democracy Club actuals ===")
    print(f"{'Council':30s}  {'matched':>10s}  {'winner-hit%':>12s}  {'share-MAE pp':>14s}")
    print('-' * 80)
    for s in summaries:
        print(f"  {s['council']:30s}  {s['matched']:4d}/{s['predictions_total']:<5d}  {s['winner_pct']:>11}%  {s['share_mae']:>14}")
        if s['misses_sample']:
            for m in s['misses_sample'][:3]:
                print(f"      MISS {m['ward']:25s} pred={m['predicted']:18s} actual={m['actual']:18s} margin={m.get('predicted_margin','?')}")
    print('-' * 80)
    if overall_matched:
        print(f"  {'OVERALL':30s}  {overall_matched:>10d}  {round(100*overall_hit/overall_matched,1):>11}%  "
              f"{round(overall_mae_sum/overall_mae_n,2) if overall_mae_n else 0:>14}")

if __name__ == '__main__':
    main()
