"""Approach 1 v2: same as v1 but minimal output (no reasoning) + higher token cap."""
import os, sys, json, urllib.request, time
from pathlib import Path

REPO = Path('/home/jason/projects/kronaxis')
GEMINI_KEY = next((line.split('=',1)[1].strip() for line in (REPO/'titan-forge-suite'/'.env').read_text().splitlines() if line.startswith('GEMINI_API_KEY=')), None)

ds = json.loads((REPO/'scripts'/'llm_test'/'dataset.json').read_text())
train, holdout = ds['train'], ds['holdout']
VALID = {'Labour','Conservative','Liberal Democrat','Reform UK','Green','Independent','No overall control'}

def fmt(r, with_actual=True):
    vs = r['vote_shares']
    vs_str = " | ".join(f"{k}={v:.1f}" for k, v in sorted(vs.items(), key=lambda kv: -kv[1]))
    s = f"  {r['council']} [{r['region']}] {r['council_type']} incumbent={r['incumbent']} | {vs_str}"
    if with_actual:
        s += f" | ACTUAL={r['actual_winner']}"
    return s

system = """You are an expert UK psephologist analysing the 7 May 2026 English local elections.
Below are 110 councils with vote-share predictions and ACTUAL winners. Then 20 councils with vote shares only — predict each.

OUTPUT (strict): one line per holdout council, format: COUNCIL_NAME | WINNER
Winner must be EXACTLY one of: Labour, Conservative, Liberal Democrat, Reform UK, Green, Independent, No overall control.
NO reasoning. NO commentary. ONLY 20 lines.
"""

prompt = system + "\n=== TRAINING (110 labelled) ===\n"
for r in train: prompt += fmt(r, True) + "\n"
prompt += "\n=== HOLDOUT (predict these 20) ===\n"
for r in holdout: prompt += fmt(r, False) + "\n"
prompt += "\n=== YOUR PREDICTIONS (20 lines, COUNCIL | WINNER, nothing else) ===\n"

print(f"Prompt: {len(prompt)} chars")

def call(model_id):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={GEMINI_KEY}"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 16384}}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type":"application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode())

# Try Pro first (now that minute may have rolled), fall back to Flash
for model in ['gemini-2.5-pro', 'gemini-2.5-flash']:
    print(f"\nCalling {model}...")
    try:
        result = call(model)
        text = result['candidates'][0]['content']['parts'][0]['text']
        print(f"Got {len(text)} chars from {model}")
        used_model = model
        break
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print(f"  429, trying next model")
            continue
        raise
    except Exception as e:
        print(f"  ERROR: {e}")
        continue
else:
    print("All models failed")
    sys.exit(1)

print("\n=== RAW ===")
print(text)

# Parse
preds = {}
for line in text.splitlines():
    line = line.strip().lstrip('-*•0123456789. ')
    if '|' not in line: continue
    parts = [p.strip() for p in line.split('|')]
    if len(parts) >= 2 and parts[1] in VALID:
        preds[parts[0]] = parts[1]

# Score
hits = 0
print(f"\n=== SCORING (model={used_model}) ===")
print(f"{'Council':30s} {'Predicted':25s} {'Actual':25s} Hit?")
print("-" * 90)
for r in holdout:
    pred = preds.get(r['council'], '<NO PREDICTION>')
    actual = r['actual_winner']
    hit = pred == actual
    if hit: hits += 1
    print(f"{r['council']:30s} {pred:25s} {actual:25s} {'YES' if hit else 'no'}")

print(f"\n=== APPROACH 1 v2 RESULT ===")
print(f"  {used_model:30s}: {hits}/{len(holdout)} = {100*hits/len(holdout):.1f}%")
print(f"  Always-NOC baseline: 13/20 = 65.0%")
print(f"  v15 baseline:        11/20 = 55.0%")

(REPO/'scripts'/'llm_test'/'approach1_v2_result.json').write_text(json.dumps({
    'model': used_model, 'predictions': preds, 'raw': text,
    'hits': hits, 'total': len(holdout), 'pct': round(100*hits/len(holdout),1)
}, indent=2))
