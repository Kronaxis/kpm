# KPM — Kronaxis Polling Method

**Public, falsifiable UK election forecasting with cryptographic pre-registration.**

This repository contains the code, methodology, hashes, and full audit trail behind every Kronaxis election prediction. Each prediction is committed to git with a SHA-256 hash *before* the event happens, so anyone can verify after results land that nothing was retroactively adjusted.

The companion public scorecard at <https://kronaxis.co.uk/scorecard> displays every prediction alongside its actual outcome — hits and misses with equal prominence.

## Why this exists

UK polling and AI forecasting are full of claims that can't be verified after the fact. The KPM project is the inverse: every prediction is hashed and committed before the event, code is open-source, results are auto-scored against actuals, and misses are reported with the same prominence as hits.

This is the foundational pattern Kronaxis applies to every product — software vulnerability claims, behavioural simulations, system performance — but elections are the cleanest test case because outcomes are unambiguous and timing is fixed.

## What's in this repo

| Directory | Purpose |
|---|---|
| `scripts/kpm2/` | KPM-2.2 v15.1 — rule-based fragmentation override on KPM-1's vote shares. Hand-crafted, hash-anchored. |
| `scripts/scorecard/` | Public scorecard generator. Seeds + computes metrics + publishes JSON for the website to render. |
| `scripts/byelection/` | Continuous by-election engine. ALDC RSS ingest → v15.1 prediction → hash → scorecard append → outcome scoring. |
| `scripts/llm_test/` | The honest LLM-failure experiments. Three approaches tested, all failed, full results published. |
| `data/kpm/` | Hand-verified May 7 2026 actuals + historical NOC priors + full session gold log. |
| `data/scorecard/` | Source-of-truth scorecard JSON + computed metrics JSON. |
| `data/byelection/` | By-election calendar (auto-populated from ALDC RSS). |
| `tests/` | Reproducibility tests — verify the methodology hash + reproduce the 59.2% v15.1 number. |

## The KPM-1 → KPM-2.2 → KPM-* trajectory

- **KPM-1** (separate repo: <https://github.com/Kronaxis/kpm1-election-projections>) — synthetic-panel forecasting via DYNAMICS-8 personas. Pre-registered before May 7 2026 with SHA-256 hash committed at <https://github.com/Kronaxis/kpm1-election-projections/commit/...>. **Result: 28.5% on broader 130-council sample**, ~PNS MAE 1.64pp on national vote share.
- **KPM-2.2** (this repo) — hand-crafted rule-based fragmentation override on KPM-1's vote shares. Six rules (LD-incumbent retain, NW Lab retain, historical NOC prior, LD strong-leader, Reform metro sweep, fragmentation NOC). **Result: 59.2% on the same 130 councils, +30.7pp lift over KPM-1.**
- **KPM-3 (planned)** — ward-level FPTP simulator with Monte Carlo. Uses last-result + uniform regional swing + incumbency. Targets 70-75% accuracy by replacing council-level vote-share guessing with the actual electoral mechanism.

## Methodology hash (v15.1)

```
SHA-256: 52df676e792c29c6c893382a5c390c9b9790663e6e7e0a9c7edb1a54ac6c0741
Schema:  kpm2-fragmentation-v15.1
Commit:  see git log for scripts/kpm2/rules.py
```

Anyone can verify by running:
```bash
python3 -c "import scripts.kpm2.rules as r; print(r.fragmentation_hash())"
```

## The honest LLM-failure record

Three LLM approaches were tested before settling on hand-crafted rules. **All three failed.** Full report in [`scripts/llm_test/SUMMARY.md`](scripts/llm_test/SUMMARY.md).

| Method | 20-council holdout |
|---|---|
| Always-NOC (trivial baseline) | **65.0%** |
| KPM-2.2 v15.1 hand-crafted rules | 55.0% |
| Approach 1: Gemini 2.5 few-shot (110 labelled examples) | 50.0% |
| Approach 3: LLM rule mining | 30.0% |
| KPM-1 LLM panel | 25.0% |
| Approach 2: RAG with Wikipedia | 1/5 (the one win was a Wiki post-event leak; honest 0/5) |

The LLM has no useful signal for council-level UK election prediction. It remains useful for national PNS calibration (1.64pp MAE — competitive with major pollsters). Reported here so that future readers can challenge the conclusion or repeat the experiment.

## Reproducing the 59.2% number

```bash
git clone https://github.com/Kronaxis/kpm.git
cd kpm
python3 -m pip install --quiet -e .  # no third-party deps; pure stdlib
python3 -m tests.test_backtest
# Expected: KPM-2.2 v15.1 = 77/130 = 59.2%
```

The dataset (`scripts/llm_test/dataset.json`) is the merged 130-council set: 52 hand-verified actuals + 78 from a strict scrape of the Wikipedia 2026 results table, with hand-verified winning on overlap.

## Falsifiability principles

1. **Hash-and-commit before the event.** Every prediction is in git history with a SHA-256 hash before the result is known.
2. **Open-source the code.** This repo. MIT-style permissions on the code; CC BY 4.0 on the methodology and data.
3. **Auto-score against actuals.** When results land, the scorecard updates automatically with hit/miss markers.
4. **Misses with equal prominence as hits.** The Hackney/Lewisham/Waltham Forest Green sweep miss is as visible as any hit. The 1/8 lean-track is reported alongside the 59.2% v15.1.
5. **Methodology evolves in public.** Each successor version (v14 → v15 → v15.1 → v16) shows its lift over the prior version transparently. Backtests are marked as backtests, never claimed as pre-registered predictions.

## Next-up roadmap

- **Week 4**: Ward-level FPTP simulator (KPM-3). Per-ward swing model + Monte Carlo + seat counting. Target: 70-75% on broader council sample.
- **Month 2**: Parliamentary by-election predictor (MRP-light). Mayoral/PCC predictors (AV/SV simulators).
- **Month 3**: Scotland 2026 + Wales 2026 devolved elections. Same scorecard, same hash discipline.
- **Ongoing**: Every Thursday a UK council by-election happens. Every one gets predicted, hashed, scored. Within 12 months the scorecard will hold 250-300 predictions vs ~5 from any major pollster.

## Licence

Code: BSL 1.1 (Business Source Licence) — converts to Apache 2.0 on 10 May 2031. See [`LICENSE`](LICENSE).
Data and methodology: CC BY 4.0.

## Contact

- Project lead: Jason Duke <jason@kronaxis.co.uk>
- Issues: <https://github.com/Kronaxis/kpm/issues>
- Public scorecard: <https://kronaxis.co.uk/scorecard>
- Methodology paper: KPM-2 Methodology document forthcoming
