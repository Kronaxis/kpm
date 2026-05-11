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
| `scripts/ward_data/` | KPM-v17 ward-level methodology (v17.0 → v17.10 ensemble). Per-ward UNS + Reform-target detection + ONS Census + Hanretty Brexit. Honest negative results documented alongside the positive findings. |
| `scripts/scorecard/` | Public scorecard generator. Seeds + computes metrics + publishes JSON for the website to render. |
| `scripts/byelection/` | Continuous by-election engine. ALDC RSS ingest → v15.1 prediction → hash → scorecard append → outcome scoring. |
| `scripts/llm_test/` | The honest LLM-failure experiments. Three approaches tested, all failed, full results published. |
| `data/kpm/` | Hand-verified May 7 2026 actuals + historical NOC priors + full session gold log. |
| `data/ward_data/` | Per-ward election results from Democracy Club JSON API (36 councils with prior-history data + 4 Wikipedia-filled held-out councils + 26 pre-2024 priors for attempted cross-cycle backtest). |
| `data/brexit2016/` | Hanretty 2016 Brexit Leave % per constituency (Harvard Dataverse). |
| `data/census2021/` | ONS NOMIS bulk ward-level demographics (5 tables: age, ethnicity, religion, tenure, qualifications). |
| `data/scorecard/` | Source-of-truth scorecard JSON + computed metrics JSON. |
| `data/byelection/` | By-election calendar (auto-populated from ALDC RSS). |
| `tests/` | Reproducibility tests — verify both methodology hashes + reproduce the 59.2% v15.1 and 72.5% v17.10 numbers. |

## The KPM-1 → KPM-2.2 → KPM-v17 trajectory

- **KPM-1** (separate repo: <https://github.com/Kronaxis/kpm1-election-projections>) — synthetic-panel forecasting via DYNAMICS-8 personas. Pre-registered before May 7 2026 with SHA-256 hash committed at <https://github.com/Kronaxis/kpm1-election-projections/commit/...>. **Result: 28.5% on broader 130-council sample**, ~PNS MAE 1.64pp on national vote share.
- **KPM-2.2 v15.1** (this repo, `scripts/kpm2/`) — hand-crafted rule-based fragmentation override on KPM-1's vote shares. Six rules (LD-incumbent retain, NW Lab retain, historical NOC prior, LD strong-leader, Reform metro sweep, fragmentation NOC). **Result: 59.2% on the same 130 councils, +30.7pp lift over KPM-1.**
- **KPM-v17 ward-level methodology** (this repo, `scripts/ward_data/`) — per-ward UNS projection + Reform-target detection + ONS Census 2021 demographics + Hanretty 2016 Brexit Leave estimates. v17.10 production hash `2ea86b8d1e25ee68…`. **Result on n=40 sample (36 DC + 4 Wikipedia-held-out): 72.5%, tied with v15.1 at 72.5%.** Bootstrap 95% CI on the difference is [-17.5, +17.5]pp — we cannot reject the null hypothesis that v17.10 = v15.1. The substantive structural finding: v17.10 has ~2× Reform UK recall (83% vs 46%) on the broader v15.1 sample, at comparable precision. Both methodologies have 0% recall for Conservative and Green council wins (14 of 130 cases — systematic blind spot).

## Methodology hashes

**v15.1 (council-fragmentation):**
```
SHA-256: 52df676e792c29c6c893382a5c390c9b9790663e6e7e0a9c7edb1a54ac6c0741
Schema:  kpm2-fragmentation-v15.1
Verify:  python3 -c "import scripts.kpm2.rules as r; print(r.fragmentation_hash())"
```

**v17.10 (ward-level ensemble):**
```
SHA-256: 2ea86b8d1e25ee68ebf66c6f59496e2480a43dba2a81ff17012ce0094531f018
Schema:  kpm-v17.10-ensemble
Verify:  python3 -c "import scripts.ward_data.methodology_v17_10_ensemble as m; print(m.methodology_hash())"
```

Both hashes are frozen. Any rule change → new hash → new methodology row in the scorecard.

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

## Reproducing the published numbers

**v15.1 (59.2% on n=130):**
```bash
git clone https://github.com/Kronaxis/kpm.git
cd kpm
python3 -m pip install --quiet -e .  # no third-party deps; pure stdlib
python3 -m tests.test_backtest
# Expected: KPM-2.2 v15.1 = 77/130 = 59.2%
```

**v17.10 (72.5% on n=40, tied with v15.1):**
```bash
python3 -m tests.test_v17_10_backtest
# Expected: KPM-v17.10 ensemble = 29/40 = 72.5%
#           KPM-2.2 v15.1         = 29/40 = 72.5%
#           Difference            = +0.0pp (tied)
```

The v15.1 dataset (`scripts/llm_test/dataset.json`) is the merged 130-council set: 52 hand-verified actuals + 78 from a strict scrape of the Wikipedia 2026 results table, with hand-verified winning on overlap. The v17.10 dataset (`data/ward_data/*_history.json`) is real per-ward results from the Democracy Club JSON API, augmented with Wikipedia for 4 held-out councils where DC data is incomplete.

## Honest negative results

In the spirit of falsifiable research, this repo also documents what **didn't** work:

- **`scripts/llm_test/`** — three LLM approaches (few-shot, RAG, rule-mining) all under-performed always-NOC baseline. Full results published.
- **`scripts/ward_data/FINDING_n36_honest_plateau.md`** — v17.10 ties v15.1 at n=40. The earlier +25pp lift at n=15 was a Reform-heavy sampling artefact. Both methodologies have 0% recall for Conservative and Green council wins.
- **`scripts/ward_data/FINDING_2024_backtest_data_limit.md`** — cross-cycle 2024 backtest attempted on 26 metropolitan boroughs; 81% had ward boundary review 2022→2024 making ward-level retrospective validation empirically impossible for that cycle. The 5 stable-boundary cases were uninformative (Lab landslide year).
- **`scripts/ward_data/FINDING_v17_per_party_failure_modes.md`** — the methodology over-predicts Reform UK in Brexit-voting Lab strongholds with low prior Reform share (Wigan, Wolverhampton, Dudley false positives).

The credibility of any positive claim rests on these negative results being equally visible.

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
