"""Build a council-level prediction dataset for LLM tests.
Each record: {council, region, council_type, incumbent, vote_shares, actual_winner}
Pull from KPM-1 published vote shares + merged actuals."""
from __future__ import annotations
import json, random
from pathlib import Path

REPO = Path('/home/jason/projects/kronaxis')

def main():
    kpm1 = json.loads((REPO / 'website' / 'kronaxis' / 'data' / 'election-results-2026.json').read_text())
    councils_kpm1 = {c['name']: c for c in kpm1.get('councils', []) if 'name' in c}

    actuals_orig = json.loads((REPO / 'data' / 'may7_actual_results.json').read_text())['council_winners_actual']
    actuals_full = json.loads((REPO / 'data' / 'may7_actuals_full.json').read_text())['council_winners_actual_full']

    def norm(s):
        s = (s or "").strip()
        return {"NOC":"No overall control","No Overall Control":"No overall control",
                "no overall control":"No overall control","Lib Dem":"Liberal Democrat",
                "Liberal Democrats":"Liberal Democrat","Reform":"Reform UK",
                "Conservatives":"Conservative","Tories":"Conservative"}.get(s, s)

    # Hand-verified wins on overlap
    actuals = dict(actuals_full)
    for k, v in actuals_orig.items():
        actuals[k] = v

    records = []
    for c, w in actuals.items():
        if c not in councils_kpm1: continue
        rec = councils_kpm1[c]
        vs = rec.get('vote_shares', {}) or {}
        if not vs: continue
        records.append({
            'council': c,
            'region': rec.get('region', ''),
            'council_type': rec.get('council_type', ''),
            'incumbent': rec.get('incumbent', ''),
            'vote_shares': {k: round(float(v), 2) for k, v in vs.items()},
            'kpm1_predicted': norm(rec.get('predicted_winner', '')),
            'kpm1_confidence': rec.get('confidence', ''),
            'kpm1_margin_pp': round(float(rec.get('margin_pp', 0)), 2),
            'actual_winner': norm(w),
        })

    # Stable holdout: deterministic seeded split, 20 hold + 110 train
    random.seed(20260509)
    shuffled = sorted(records, key=lambda r: r['council'])
    random.shuffle(shuffled)
    holdout = shuffled[:20]
    train = shuffled[20:]

    out = REPO / 'scripts' / 'llm_test' / 'dataset.json'
    out.write_text(json.dumps({
        'n_total': len(records),
        'n_train': len(train),
        'n_holdout': len(holdout),
        'train': train,
        'holdout': holdout,
        'split_seed': 20260509,
    }, indent=2))
    print(f'Total records: {len(records)}')
    print(f'Train: {len(train)} | Holdout: {len(holdout)}')
    print(f'\nHoldout actuals distribution:')
    from collections import Counter
    c = Counter(r['actual_winner'] for r in holdout)
    for w, n in c.most_common():
        print(f'  {w}: {n}')
    print(f'\nWritten: {out}')

if __name__ == '__main__':
    main()
