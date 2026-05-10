# LLM-test triple experiment — verdict (2026-05-09)

**Question**: can our LLM (Gemini 2.5 Pro/Flash) actually add signal to council-level UK election prediction, or is the hand-crafted KPM-2.2 v15 rule the ceiling?

**Setup**: 130-council merged dataset (52 hand-verified + 78 strict-scraped Wiki actuals). Deterministic 110/20 train/holdout split (seed=20260509). Holdout class distribution: 13 NOC, 4 Lab, 1 each Green/Reform/LD.

## Baselines on the 20-council holdout

| Method | Hits | Pct |
|---|---|---|
| Always-NOC (majority class) | 13/20 | **65.0%** |
| KPM-2.2 v15 fragmentation rule (hand-crafted) | 11/20 | 55.0% |
| Always-largest-vote-share | 3/20 | 15.0% |
| Always-Labour | 4/20 | 20.0% |
| KPM-1 published prediction | 5/20 | 25.0% |

## Three LLM approaches tested

### Approach 1: Few-shot in-context (110 labelled examples → 20 holdout)
- Prompt: 110 council records with vote shares + actual winners, ask Gemini 2.5 Flash to predict 20 holdout
- **Result: 10/20 = 50.0%** (Gemini 2.5 Pro hit 429 rate-limit; Flash succeeded)
- Verdict: **FAIL** — below Always-NOC (65%) and below v15 (55%)
- Head-to-head vs v15: v15 +1 net (3 wins for v15 where Gemini wrong, 2 wins for Gemini where v15 wrong, 1 both wrong)

### Approach 2: RAG-grounded (Wikipedia per-council pages)
- For 5 test councils (Lewisham, Sunderland, Bradford, Wolverhampton, St Albans), fetch Wikipedia council article + last-election article, prompt Gemini with the local context
- **Result: 1/5** — but the one win (Bradford) was a methodological leak (Wikipedia article had been updated to say "under No Overall Control since 2026")
- Honest score WITHOUT the leak: **0/5**
- Verdict: **FAIL** — Wikipedia summaries don't capture the local dynamics that drive election outcomes; real RAG would need point-in-time-snapshotted local news

### Approach 3: LLM as rule miner
- Feed Gemini 110 labelled records, ask for 5-10 IF-THEN decision rules
- Parse rules + execute on holdout
- **Result: 6/20 = 30.0%** on holdout (39% on train)
- LLM-derived rules: 4 rules parsed (5th truncated), all naive (e.g. "Lab clean lead → Lab", "Reform breakthrough → Reform")
- Verdict: **FAIL** — far below v15's hand-crafted rules

## Bottom line

**All three LLM approaches under-perform v15 (55%) AND the trivial Always-NOC baseline (65%) on this holdout.**

The LLM has no useful signal for council-level UK election prediction:
- It can't simulate voters (KPM-1 = "always guess Labour")
- It can't pattern-match from labelled examples (50% on NOC-heavy holdout)
- It can't mine better rules than a human can (30%)
- Wikipedia-grounded RAG doesn't help (0/5 without leakage)

What the LLM IS good for (already validated):
- **PNS national vote share**: 1.64pp MAE — competitive with major pollsters (1-2pp range)

**Implication for KPM-2.2 production**: Drop LLM from per-council prediction entirely. Keep v15 rules. If we want to push past 56% on broader sample, we need:
1. Real local news ingestion (Local Democracy Reporting Service, council websites)
2. Ward-level result history (Wikipedia per-council 2018-2024 detail pages)
3. By-election result tracker (ALDC by-election database)

None of these are LLM problems — they are data engineering problems. The LLM was the wrong tool for this job.

**The system isn't broken. The framing was broken.** v15 rules (no LLM) deliver +27.7pp over baseline. That's a real product. The LLM was a marketing layer.
