"""Approach 3: LLM as rule miner.
Feed Gemini all 130 records (vote shares + actual winners), ask for 5 IF-THEN
decision rules that maximise prediction accuracy. Parse + execute on holdout."""
import os, sys, json, urllib.request, re
from pathlib import Path

REPO = Path('/home/jason/projects/kronaxis')
GEMINI_KEY = next((line.split('=',1)[1].strip() for line in (REPO/'titan-forge-suite'/'.env').read_text().splitlines() if line.startswith('GEMINI_API_KEY=')), None)

ds = json.loads((REPO/'scripts'/'llm_test'/'dataset.json').read_text())
train, holdout = ds['train'], ds['holdout']

def fmt(r):
    vs = r['vote_shares']
    vs_str = " | ".join(f"{k}={v:.1f}" for k, v in sorted(vs.items(), key=lambda kv: -kv[1]))
    return f"  {r['council']} [region={r['region']}] [type={r['council_type']}] incumbent={r['incumbent']} | {vs_str} | ACTUAL={r['actual_winner']}"

system = """You are a rule-mining engine for UK local election prediction.

I will give you 110 labelled examples from the 7 May 2026 English locals: per-council vote-share predictions (KPM-1 model output), region, council type, incumbent party, and the ACTUAL winner.

Your job: derive 5-10 deterministic IF-THEN decision rules that predict the actual winner from the vote shares + features. Rules must be EVALUABLE PYTHON expressions over a record dict r with keys:
  - r['council']  (str)
  - r['region']   (str: e.g. 'Greater London', 'North East', 'West Midlands')
  - r['council_type']  (str: e.g. 'Metropolitan Borough', 'Unitary Authority', 'London Borough')
  - r['incumbent']  (str: e.g. 'Labour', 'Conservative', 'No overall control')
  - r['vote_shares']  (dict: e.g. {'Lab': 38.2, 'Con': 22.1, 'Reform': 18.0, 'LD': 8.5, 'Green': 7.0})
  - r['kpm1_predicted']  (str)

Rules are tried IN ORDER. First match wins. Last rule must be a catch-all.

Available helpers (use freely):
  - top1(r)  -> (party, share) of largest vote
  - top2(r)  -> [(party,share), (party,share)] of top two
  - share(r, 'Lab')  -> Labour share, 0 if missing
  - margin12(r)  -> top1 - top2 share

OUTPUT FORMAT (strict — exactly 5-10 rules):
RULE_N: <one-line description>
CONDITION: <python expression returning bool>
PREDICT: <one of: Labour, Conservative, Liberal Democrat, Reform UK, Green, Independent, No overall control>

Example:
RULE_1: Labour stronghold London borough with clean lead
CONDITION: r['region'] == 'Greater London' and share(r, 'Lab') > 40 and margin12(r) > 10
PREDICT: Labour

Output the rules. Nothing else.
"""

prompt = system + "\n=== TRAINING DATA (110 labelled councils) ===\n"
for r in train: prompt += fmt(r) + "\n"
prompt += "\n=== YOUR RULES ===\n"

print(f"Prompt: {len(prompt)} chars")
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
body = {"contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 8192}}
req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type":"application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=300) as r:
    result = json.loads(r.read().decode())
text = result['candidates'][0]['content']['parts'][0]['text']
print("\n=== RAW RULES ===")
print(text)

# Parse rules
rules = []
current = {}
for line in text.splitlines():
    line = line.strip()
    if line.startswith('RULE_') or re.match(r'^RULE\s*\d+', line, re.IGNORECASE):
        if current:
            rules.append(current)
        current = {'desc': line}
    elif line.upper().startswith('CONDITION:'):
        current['cond'] = line.split(':', 1)[1].strip()
    elif line.upper().startswith('PREDICT:'):
        current['pred'] = line.split(':', 1)[1].strip()
if current and 'cond' in current and 'pred' in current:
    rules.append(current)

print(f"\nParsed {len(rules)} rules")
for i, rl in enumerate(rules, 1):
    print(f"  {i}. {rl.get('desc','')}")
    print(f"     IF {rl.get('cond','')}")
    print(f"     THEN {rl.get('pred','')}")

# Helper functions for rule evaluation
def top1(r):
    if not r['vote_shares']: return ('', 0)
    return max(r['vote_shares'].items(), key=lambda kv: kv[1])
def top2(r):
    if not r['vote_shares']: return [('', 0), ('', 0)]
    s = sorted(r['vote_shares'].items(), key=lambda kv: -kv[1])
    return s[:2] + [('', 0)] * (2 - len(s))
def share(r, p):
    aliases = {'Lab':'Labour','Con':'Conservative','LD':'Liberal Democrat','Lib Dem':'Liberal Democrat',
               'Green':'Green','Reform':'Reform UK'}
    # The KPM-1 vote_shares uses short names like Lab/Con/LD/Reform/Green
    return r['vote_shares'].get(p, 0)
def margin12(r):
    t = top2(r)
    return t[0][1] - t[1][1]

VALID = {'Labour','Conservative','Liberal Democrat','Reform UK','Green','Independent','No overall control'}

def predict_with_rules(r):
    for rl in rules:
        try:
            if eval(rl['cond'], {'r': r, 'top1': top1, 'top2': top2, 'share': share, 'margin12': margin12}):
                return rl['pred']
        except Exception:
            continue
    # Fall through: NOC default
    return 'No overall control'

# Score on holdout
hits_h = 0
print(f"\n=== HOLDOUT (20) ===")
for r in holdout:
    p = predict_with_rules(r)
    h = p == r['actual_winner']
    if h: hits_h += 1
    print(f"  {r['council']:30s} pred={p:25s} actual={r['actual_winner']:25s} {'YES' if h else 'no'}")

# Score on full train + holdout to compare ceiling
hits_t = sum(1 for r in train if predict_with_rules(r) == r['actual_winner'])
all_records = train + holdout
hits_a = sum(1 for r in all_records if predict_with_rules(r) == r['actual_winner'])

print(f"\n=== APPROACH 3 RESULT (LLM rule mining) ===")
print(f"  Holdout (20):    {hits_h}/{len(holdout)} = {100*hits_h/len(holdout):.1f}%")
print(f"  Train (110):     {hits_t}/{len(train)} = {100*hits_t/len(train):.1f}%  (in-sample, expect inflation)")
print(f"  Combined (130):  {hits_a}/{len(all_records)} = {100*hits_a/len(all_records):.1f}%")
print(f"")
print(f"  Baseline comparisons (holdout):")
print(f"    Always-NOC: 13/20 = 65.0%")
print(f"    v15:        11/20 = 55.0%")
print(f"    Gemini fewshot: 10/20 = 50.0%")
print(f"    KPM-1:       5/20 = 25.0%")

(REPO/'scripts'/'llm_test'/'approach3_result.json').write_text(json.dumps({
    'rules': rules,
    'raw': text,
    'holdout': {'hits': hits_h, 'total': len(holdout), 'pct': round(100*hits_h/len(holdout),1)},
    'train': {'hits': hits_t, 'total': len(train), 'pct': round(100*hits_t/len(train),1)},
    'combined': {'hits': hits_a, 'total': len(all_records), 'pct': round(100*hits_a/len(all_records),1)},
}, indent=2))
