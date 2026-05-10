"""Score baselines on the 20-council holdout for comparison."""
import sys, json
from pathlib import Path
from collections import Counter
sys.path.insert(0, '/home/jason/projects/kronaxis')
from scripts.kpm2.classify import apply_fragmentation_override, Classification

REPO = Path('/home/jason/projects/kronaxis')
ds = json.loads((REPO / 'scripts' / 'llm_test' / 'dataset.json').read_text())
holdout = ds['holdout']
train = ds['train']

def score(records, predictor, label):
    hits = 0
    for r in records:
        pred = predictor(r)
        if pred == r['actual_winner']:
            hits += 1
    pct = 100 * hits / len(records)
    print(f"  {label:40s}: {hits}/{len(records)} = {pct:.1f}%")
    return hits

print(f"=== Baselines on 20-council holdout ===")
print(f"  Holdout class dist: {dict(Counter(r['actual_winner'] for r in holdout))}")
print()

# Always NOC
score(holdout, lambda r: 'No overall control', "Always NOC")
# Always Labour
score(holdout, lambda r: 'Labour', "Always Labour")
# Largest vote share
def largest(r):
    vs = r['vote_shares']
    if not vs: return 'No overall control'
    p, _ = max(vs.items(), key=lambda kv: kv[1])
    norm = {'Lab':'Labour','Con':'Conservative','LD':'Liberal Democrat','Lib Dem':'Liberal Democrat',
            'Reform':'Reform UK','RefUK':'Reform UK','Grn':'Green'}
    return norm.get(p, p)
score(holdout, largest, "Always-largest-vote-share")
# KPM-1 baseline
score(holdout, lambda r: r['kpm1_predicted'], "KPM-1 published prediction")
# v15 fragmentation rule
def v15_pred(r):
    cls = Classification(r['kpm1_predicted'], r['kpm1_confidence'], r['kpm1_margin_pp'], False, 'kpm1')
    cls = apply_fragmentation_override(r['vote_shares'], cls,
        region=r['region'], council_type=r['council_type'],
        incumbent=r['incumbent'], council_name=r['council'])
    return cls.predicted_winner
score(holdout, v15_pred, "KPM-2.2 v15 fragmentation rule")

print()
print(f"=== Same baselines on the 110-council train set ===")
score(train, lambda r: 'No overall control', "Always NOC")
score(train, lambda r: 'Labour', "Always Labour")
score(train, largest, "Always-largest-vote-share")
score(train, lambda r: r['kpm1_predicted'], "KPM-1 published prediction")
score(train, v15_pred, "KPM-2.2 v15 fragmentation rule")
