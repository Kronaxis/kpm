"""Approach 2: RAG-grounded prediction (proxy with Wikipedia).
For 5 hold-out councils, fetch the Wikipedia 2024 council page (PRE-2026 election
context: last election composition, by-elections, council news through 2024).
Then ask Gemini to predict 2026 winner given the local evidence + vote shares.

NB: This is a proxy. Real RAG would use Local Democracy Reporting Service news,
candidate sites, local Reddit. Wikipedia 2024 page is the best free pre-2026 proxy."""
import os, sys, json, urllib.request, re, time
from html import unescape
from pathlib import Path

REPO = Path('/home/jason/projects/kronaxis')
GEMINI_KEY = next((line.split('=',1)[1].strip() for line in (REPO/'titan-forge-suite'/'.env').read_text().splitlines() if line.startswith('GEMINI_API_KEY=')), None)

ds = json.loads((REPO/'scripts'/'llm_test'/'dataset.json').read_text())
holdout = ds['holdout']

# Pick 5 holdout councils with diverse profiles
TEST_COUNCILS = ['Lewisham', 'Bradford', 'Sunderland', 'St Albans', 'Wolverhampton']
test = [r for r in holdout if r['council'] in TEST_COUNCILS]
print(f"Test councils: {[r['council'] for r in test]}")

UA = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"

def fetch_council_context(council_name):
    """Fetch the Wikipedia 'Council Name' page + last-election page; return summary text."""
    pages = []
    # Try main council page
    main_titles = [
        f"{council_name}_London_Borough_Council",
        f"{council_name}_City_Council",
        f"{council_name}_Council",
        f"{council_name}_Metropolitan_Borough_Council",
        f"{council_name}_District_Council",
        f"{council_name}_Borough_Council",
        f"Metropolitan_Borough_of_{council_name}",
    ]
    last_election_titles = [
        f"2022_{council_name}_London_Borough_Council_election",
        f"2022_{council_name}_City_Council_election",
        f"2022_{council_name}_Council_election",
        f"2022_{council_name}_Metropolitan_Borough_Council_election",
        f"2024_{council_name}_Council_election",
        f"2023_{council_name}_Council_election",
    ]
    for title in main_titles + last_election_titles:
        url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as r:
                html = r.read().decode('utf-8', errors='replace')
            # Extract first 4 paragraphs of body text
            body_match = re.search(r'<div id="mw-content-text"[^>]*>(.*)', html, re.DOTALL)
            if not body_match: continue
            body = body_match.group(1)
            # Strip references / templates / tables for cleaner text
            body = re.sub(r'<table[^>]*>.*?</table>', '', body, flags=re.DOTALL)
            body = re.sub(r'<sup[^>]*>.*?</sup>', '', body, flags=re.DOTALL)
            paras = re.findall(r'<p[^>]*>(.*?)</p>', body, re.DOTALL)
            text_parts = []
            for p in paras[:6]:
                clean = unescape(re.sub(r'<[^>]+>', '', p)).strip()
                clean = re.sub(r'\s+', ' ', clean)
                if len(clean) > 50:
                    text_parts.append(clean)
                if len(' '.join(text_parts)) > 2000: break
            if text_parts:
                summary = ' '.join(text_parts)[:2500]
                pages.append((title, summary))
                if len(pages) >= 2: break  # main + last election
        except Exception as e:
            continue
        time.sleep(0.3)
    return pages

# Build per-council RAG context
contexts = {}
for r in test:
    print(f"\nFetching context for {r['council']}...")
    pages = fetch_council_context(r['council'])
    contexts[r['council']] = pages
    for title, summary in pages:
        print(f"  [{title}] {len(summary)} chars: {summary[:200]}...")

# Build prompt
system = """You are an expert UK psephologist analysing the 7 May 2026 English local elections.

For each council below you have:
1. The KPM-1 model's vote-share predictions
2. Wikipedia context (council article + most recent past election article)

Predict the 2026 winner. The Wikipedia context tells you about composition, recent by-elections, defections, demographics — use it to spot patterns the bare vote-share model misses (e.g. Green strength, Reform breakthrough potential, NOC propensity).

OUTPUT: one line per council, format COUNCIL | WINNER | reasoning(<=200 chars)
Winner must be EXACTLY one of: Labour, Conservative, Liberal Democrat, Reform UK, Green, Independent, No overall control.
"""

prompt = system + "\n=== TEST COUNCILS WITH RAG CONTEXT ===\n"
for r in test:
    vs = r['vote_shares']
    vs_str = " | ".join(f"{k}={v:.1f}" for k, v in sorted(vs.items(), key=lambda kv: -kv[1]))
    prompt += f"\n--- {r['council']} ---\n"
    prompt += f"Region: {r['region']}  | Type: {r['council_type']}  | Incumbent: {r['incumbent']}\n"
    prompt += f"KPM-1 vote shares: {vs_str}\n"
    prompt += f"KPM-1 prediction: {r['kpm1_predicted']} ({r['kpm1_confidence']}, margin {r['kpm1_margin_pp']}pp)\n"
    prompt += f"Wikipedia context:\n"
    for title, summary in contexts.get(r['council'], []):
        prompt += f"  [{title}]: {summary}\n"
    if not contexts.get(r['council']):
        prompt += "  (no Wikipedia context retrieved)\n"

prompt += "\n=== YOUR PREDICTIONS (one line per council) ===\n"

print(f"\nPrompt: {len(prompt)} chars")
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
body = {"contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 4096}}
req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type":"application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=180) as r:
    result = json.loads(r.read().decode())
text = result['candidates'][0]['content']['parts'][0]['text']
print("\n=== RAG OUTPUT ===")
print(text)

# Parse + score
VALID = {'Labour','Conservative','Liberal Democrat','Reform UK','Green','Independent','No overall control'}
preds = {}
for line in text.splitlines():
    line = line.strip().lstrip('-*•0123456789. ')
    if '|' not in line: continue
    parts = [p.strip() for p in line.split('|')]
    if len(parts) < 2: continue
    council = re.sub(r'\s*\[.*?\]\s*', '', parts[0]).strip()
    winner = parts[1].strip()
    if winner in VALID:
        for r in test:
            if r['council'].lower() == council.lower() or council.lower() in r['council'].lower():
                preds[r['council']] = winner
                break

# Score
import sys as s2
s2.path.insert(0, '/home/jason/projects/kronaxis')
from scripts.kpm2.classify import apply_fragmentation_override, Classification
def v15(r):
    cls = Classification(r['kpm1_predicted'], r['kpm1_confidence'], r['kpm1_margin_pp'], False, 'kpm1')
    cls = apply_fragmentation_override(r['vote_shares'], cls,
        region=r['region'], council_type=r['council_type'],
        incumbent=r['incumbent'], council_name=r['council'])
    return cls.predicted_winner

print(f"\n=== APPROACH 2 (RAG) on {len(test)} test councils ===")
print(f"{'Council':25s} {'RAG':25s} {'KPM-1':25s} {'v15':25s} {'Actual':25s}")
print("-" * 130)
hits_rag = 0; hits_kpm1 = 0; hits_v15 = 0
for r in test:
    rp = preds.get(r['council'], '<NONE>')
    kp = r['kpm1_predicted']
    vp = v15(r)
    actual = r['actual_winner']
    if rp == actual: hits_rag += 1
    if kp == actual: hits_kpm1 += 1
    if vp == actual: hits_v15 += 1
    print(f"{r['council']:25s} {rp:25s} {kp:25s} {vp:25s} {actual:25s}")

print(f"\n  RAG-grounded Gemini: {hits_rag}/{len(test)}")
print(f"  KPM-1 baseline:      {hits_kpm1}/{len(test)}")
print(f"  v15:                 {hits_v15}/{len(test)}")

(REPO/'scripts'/'llm_test'/'approach2_result.json').write_text(json.dumps({
    'councils_tested': [r['council'] for r in test],
    'predictions': preds,
    'raw': text,
    'hits_rag': hits_rag, 'hits_kpm1': hits_kpm1, 'hits_v15': hits_v15,
    'total': len(test),
}, indent=2))
