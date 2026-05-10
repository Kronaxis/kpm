"""Approach 1: Few-shot in-context with Gemini 2.5 Pro.
Prompt = 110 labelled training records + 20 holdout (vote shares only) + ask for predictions."""
import os, sys, json, urllib.request
from pathlib import Path
from collections import Counter

REPO = Path('/home/jason/projects/kronaxis')

# Read API key
GEMINI_KEY = None
for line in (REPO / 'titan-forge-suite' / '.env').read_text().splitlines():
    if line.startswith('GEMINI_API_KEY='):
        GEMINI_KEY = line.split('=', 1)[1].strip()
        break
assert GEMINI_KEY, "No GEMINI_API_KEY found"

ds = json.loads((REPO / 'scripts' / 'llm_test' / 'dataset.json').read_text())
train = ds['train']
holdout = ds['holdout']

VALID_WINNERS = {'Labour','Conservative','Liberal Democrat','Reform UK','Green','Independent','No overall control'}

def fmt_record(r, include_actual=True):
    vs = r['vote_shares']
    vs_str = " | ".join(f"{k}={v:.1f}" for k, v in sorted(vs.items(), key=lambda kv: -kv[1]))
    s = f"  {r['council']:30s} [{r['region']:20s}] {r['council_type']:15s} incumbent={r['incumbent']:20s} | {vs_str}"
    if include_actual:
        s += f" | ACTUAL={r['actual_winner']}"
    return s

system = """You are an expert UK psephologist analysing the 7 May 2026 English local elections.
You will be given vote-share predictions and contextual features for 110 councils with their actual winners (training set).
Then you will be given 20 councils with vote-share predictions only (holdout) and asked to predict the winner of each.

Output FORMAT (strict): one line per holdout council, in this exact format:
COUNCIL_NAME | PREDICTED_WINNER | one-line reasoning

Predicted winner must be EXACTLY one of: Labour, Conservative, Liberal Democrat, Reform UK, Green, Independent, No overall control.

Look for patterns in the training data. Common patterns to consider:
- Vote-share fragmentation -> NOC
- Strong incumbent + clean lead -> incumbent retains
- Reform breakthrough in working-class metropolitan
- Green strength in inner London (rare but happened in 3 boroughs)
- LD pickup in southern shires
- Tactical voting against Reform
"""

prompt = system + "\n\n=== TRAINING DATA (110 labelled councils) ===\n"
for r in train:
    prompt += fmt_record(r, include_actual=True) + "\n"

prompt += f"\n=== HOLDOUT TO PREDICT (20 councils, no labels) ===\n"
for r in holdout:
    prompt += fmt_record(r, include_actual=False) + "\n"

prompt += "\n=== YOUR PREDICTIONS (one line per holdout council, strict format) ===\n"

print(f"Prompt length: {len(prompt)} chars (~{len(prompt)//4} tokens)")
print(f"Calling Gemini 2.5 Pro...")

# Call Gemini
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
body = {
    "contents": [{"parts": [{"text": prompt}]}],
    "generationConfig": {"temperature": 0.0, "maxOutputTokens": 8192},
}
req = urllib.request.Request(url, data=json.dumps(body).encode(),
                              headers={"Content-Type": "application/json"}, method="POST")

try:
    with urllib.request.urlopen(req, timeout=180) as resp:
        result = json.loads(resp.read().decode())
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)

# Extract text
try:
    text = result['candidates'][0]['content']['parts'][0]['text']
except Exception as e:
    print(f"Could not extract text: {e}")
    print(json.dumps(result, indent=2)[:2000])
    sys.exit(1)

print("\n=== RAW OUTPUT ===")
print(text)
print("\n=== PARSING ===")

# Parse predictions
preds = {}
for line in text.splitlines():
    line = line.strip()
    if '|' not in line: continue
    parts = [p.strip() for p in line.split('|')]
    if len(parts) < 2: continue
    council = parts[0].strip(' -*•').lstrip('0123456789. ')
    winner = parts[1].strip()
    if winner in VALID_WINNERS:
        preds[council] = winner

print(f"\nParsed {len(preds)} predictions")

# Score
hits = 0
print(f"\n=== HOLDOUT SCORING ===")
print(f"{'Council':30s} {'LLM pred':25s} {'Actual':25s} {'Hit?':6s}")
print("-" * 90)
for r in holdout:
    pred = preds.get(r['council'], '<NO PREDICTION>')
    actual = r['actual_winner']
    hit = pred == actual
    if hit: hits += 1
    print(f"{r['council']:30s} {pred:25s} {actual:25s} {'YES' if hit else 'no'}")

print(f"\n=== APPROACH 1 RESULT ===")
print(f"  Few-shot Gemini 2.5 Pro: {hits}/{len(holdout)} = {100*hits/len(holdout):.1f}%")
print(f"  Always-NOC baseline:    13/{len(holdout)} = 65.0%")
print(f"  v15 baseline:           11/{len(holdout)} = 55.0%")

# Save full result
out = REPO / 'scripts' / 'llm_test' / 'approach1_result.json'
out.write_text(json.dumps({
    'predictions': preds,
    'raw_output': text,
    'hits': hits,
    'total': len(holdout),
    'pct': round(100*hits/len(holdout), 1),
}, indent=2))
print(f"\nSaved {out}")
