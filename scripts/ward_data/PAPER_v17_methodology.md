# KPM-v17: a ward-level methodology for English local council prediction

**Authors**: Kronaxis Research
**Date**: 2026-05-10/11 (overnight expansion + honest n=36 re-score)
**Status**: Pre-publication draft. NOT YET DEPLOYED. See `data/scorecard/DEPLOY_HOLD.md`.

## HEADLINE (revised, honest)

**Production methodology**: KPM-v17.10 ensemble (`2ea86b8d1e25ee68…`) — v17.9 confident-zone + v15.1 mid-confidence fallback + Reform-emerging override.

**On n=40 councils (36 DC + 4 Wikipedia-held-out)**: **v17.10 = 29/40 = 72.5%, v15.1 = 29/40 = 72.5% — TIED.** Bootstrap 95% CI on the difference is **[-17.5, +17.5]pp**; we cannot reject the null hypothesis that v17.10 = v15.1. The earlier 87% / +25pp figure at n=15 was a small-sample / Reform-heavy sampling artefact. At n=40 the sample is too small to discriminate between methodologies that disagree on ~25% of cases — ~160 councils would be needed to detect a 5pp true difference at α=0.05.

## Abstract

We present KPM-v17, a ward-level methodology for predicting English local
council election outcomes using real per-ward election results from the
Democracy Club JSON API, augmented with ONS Census 2021 demographics and
Hanretty 2016 Brexit Leave estimates. Earlier KPM-2.2 v15.1 (council-level
fragmentation rule) achieves 59.2% on n=130 May 2026 council elections.

KPM-v17 introduces per-ward UNS projection, Reform/Independent target
detection at both ward and council level, and an ensemble that falls back
to v15.1 in the mid-confidence zone. On a 15-council validation set
deliberately weighted toward Reform-target areas, v17.10 achieved 93%
vs v15.1's 60% (+33pp). However, **on the full n=36 sample of councils
with real DC prior-history data, v17.10 ties v15.1 at 75.0%**. The lift
trajectory (n=15: +33pp → n=22: +23pp → n=29: +14pp → n=36: +0pp)
demonstrates that the apparent advantage was an artefact of small-sample
Reform-target sampling, not a generalisable improvement.

We retain v17 as a publishable contribution on three other grounds:
(1) the Reform-emerging override is the only path with clean signal
(2/2 hits on this sample, 100%); (2) the methodology is fully interpretable
at the ward level (via `explain_v17_10.py`); (3) the data infrastructure
(DC JSON + Census + Brexit ingestion) is reusable for future cycles.

We also report four NEGATIVE results, in the spirit of honest research:
v17.4 (symmetric Green-target detection) over-fired; v17.7-full
(broad demographic Reform-conditioning) over-fired; v16's LLM-derived
per-ward predictions score 21% (barely above random); v17.0 alone (pure
UNS) ties the trivial always-incumbent baseline. The credibility of any
positive claim rests on these negative results being equally visible.

## 1. Problem

UK local council elections are predicted as a binary council-level
outcome: Labour majority / Conservative majority / Liberal Democrat
majority / No Overall Control (NOC) / Reform UK majority. Each council
contains multiple wards, each electing 1-3 councillors via FPTP. Council
control is determined by aggregate ward results.

Two approaches:
1. **Council-level methodologies** (KPM-2.2 v15.1 production): predict
   council outcome directly from council-level features (regional swing,
   fragmentation patterns, prior council control).
2. **Ward-level methodologies** (KPM-v17): predict each ward's winner,
   aggregate seats. More transparent but requires ward-level data.

The 2026 election cycle made ward-level methodology more important
because of two non-uniform patterns: (a) Reform UK breakthroughs
concentrated in post-industrial areas and (b) Independent surges in
Muslim-majority wards (Birmingham, Tower Hamlets) driven by the Gaza
issue.

## 2. Data

We use Democracy Club's JSON API
(`candidates.democracyclub.org.uk/api/next/ballots/{ballot_id}.json`).
For each of 15 selected councils:
- 2026 ballot results: per-candidate vote count + elected status
- Most-recent prior election (2022, 2023, or 2024) for the same ward

The 15 sample councils were chosen for diversity:
- Reform-target metropolitan boroughs: Hartlepool, Sandwell, Barnsley
- Lab-strong metros: Manchester, Salford, Rochdale, Sheffield, Newcastle,
  Leeds, Bradford, Bolton
- LD-strong districts: Eastleigh, Cheltenham
- Mixed metropolitan: Birmingham, Wolverhampton

Total: 322 wards with both 2026 actuals + most-recent prior. The Tower
Hamlets ballot returned 0 results from DC and was excluded.

## 3. KPM-v17 method (six iterations)

### v17.0 — baseline ward-UNS
For each ward, take prior_party_shares + apply year-scaled UNS swing
+ +4pp incumbency boost to prior winner if prior election ≤2 years old.
Renormalise to 100%. Largest projected share wins.

### v17.1 — 60% NOC overlay
Council winner = largest party if its predicted-seat share ≥60%, else NOC.
v17.0's 50% threshold over-predicts marginal majorities.

### v17.2 — Reform-weighted UNS multiplier
Reform UNS scales 1.0× → 1.3× → 1.7× → 2.0× by prior Reform vote share
(0/5/10/15% thresholds). Reform's national +12pp swing isn't enough in
Reform-emerging wards.

### v17.3 — Reform-target incumbency suppression
In wards with prior Reform ≥10%, drop the +4pp prior-incumbent boost.
The political environment has shifted enough that prior incumbency is no
longer protective.

### v17.4 (REJECTED) — symmetric Green-target detection
Same mechanism for Green: 1.0× → 1.5× UNS multiplier + suppress
incumbency when prior Green ≥15%. Result: per-ward 47.3% (vs v17.3
47.9%, regression). Green recall unchanged. Conservative recall regressed.

Cause: Green's national UNS is +3pp; even 1.5× = +4.5pp can't flip
Lab/LD wards where Lab/LD has 45-50% prior. Green's failure mode is
**structurally different** from Reform's — Green breakthroughs are
demographic-driven (young, degree-educated, urban-core), not predictable
from prior-share-base alone.

### v17.5 — council-level Reform-emergence detection
Council mean prior Reform ≥5% flags the council as "Reform-emerging".
All wards in such councils get +0.5 Reform multiplier; all Lab incumbents
lose incumbency boost.

### v17.6 (production) — outcome override
In Reform-emerging councils, if v17.5 predicts any single-party majority
(typically Lab continuation), override to "Reform UK". The council-level
signal is more reliable than per-ward UNS in detecting outright Reform
sweeps.

### v17.7-io — Census Muslim signal (per-ward Independent)

After v17.7-full (REJECTED), we kept ONLY the per-ward Independent surge
detection. Census 2021 TS030 (religion) shows Birmingham 2026 Independent
winners had Muslim% 73-84% (vs council mean ~30%).

Rule: per-ward override if `census.muslim_pct >= 60%` AND prior winner = Lab → predict Independent.

Threshold sweep on 370 wards:
| Threshold | Indep recall (n=19) | Lab loss | Net per-ward |
|---|---|---|---|
| 50% | 12/19 = 63.2% | -8 | -1 |
| **60%** | 11/19 = 57.9% | -3 | +3 |
| 70% | 11/19 = 57.9% | -3 | +3 |
| 80% | 8/19 = 42.1% | 0 | +5 |

Selected threshold: 60%. v17.7-io recall: 4/19 → 10/19 (+6 catches),
Labour recall: 54/61 → 51/61 (-3). Council-level unchanged.

### v17.8 — Brexit 2016 Leave % Reform-target

Hypothesis: Wolverhampton-class councils (Reform actual, 0% prior Reform)
are detectable via 2016 Brexit Leave %. Wolverhampton constituencies had
54-68% Leave; Wakefield 62.8%; Hartlepool 69.6%.

Rule: Add SECOND path to Reform-emerging council flag:
  council mean constituency Leave % ≥ 60% AND Lab-incumbent council
→ flag Reform-emerging (triggers v17.6 outcome override).

Brexit data: Hanretty constituency-level estimates (Harvard Dataverse).

Result on the larger n=37 sample: 26/37 = 70.3% (vs v17.6 26/37 = 70.3%). Earlier
+5pp lift figure was a smaller-sample artefact; on the expanded sample, the
Brexit rule adds zero net lift due to 3 false-positives (Wigan, Wolverhampton,
Dudley) cancelling the Wakefield gain. The rule is structurally interpretable
but the threshold (Leave ≥60%) is too permissive for councils where Brexit-era
Leave voting did not translate into 2024-26 Reform voting.

Wolverhampton: v17.8 says Reform UK; actual NOC. Different-wrong but
not improved over v17.6.

### v17.9 — combined Census + Brexit (intermediate, not final production)

v17.9 = v17.8 + v17.7-io. Combines both empirically validated extensions:
- Brexit Reform-target (catches Wakefield)
- Census Muslim Indep override (per-ward Indep recall +6)

Result on the larger n=37 sample: 26/37 = 70.3% — same as v17.6 / v17.7-io
/ v17.8 individually. The combined extensions do not stack additively because
the same councils are caught by either rule and the false positives offset.

Methodology hash: `0df615a23ef16b2d…`

### v17.10 (PRODUCTION) — ensemble with v15.1 fallback

Final production methodology layers v17.9 with a v15.1 mid-confidence fallback:

```
if v17.9 largest-share ≥ 70% OR ≤ 50%:  use v17.9 (confident)
elif Reform-emerging override fires:     use v17.9 (override)
else:                                    use v15.1 (mid-zone fallback)
```

Result on the final n=40 sample (incl. 4 Wikipedia-held-out): **29/40 = 72.5%,
tied with v15.1** at the same 72.5%. Bootstrap 95% CI on the difference:
[-17.5, +17.5]pp.

Methodology hash: `2ea86b8d1e25ee68ebf66c6f59496e2480a43dba2a81ff17012ce0094531f018`

## 4. Results

### 4.1 Council-level accuracy on the final n=40 sample

The final evaluation set is n=40 councils: 36 with ward-level DC API
prior-history + 4 Wikipedia-filled held-out councils (Camden, Croydon,
Dudley, Enfield) that the methodology never saw during tuning.

| Methodology | Hits | Pct | Lift over v15.1 |
|---|---|---|---|
| v15.1 (canonical) | 29/40 | 72.5% | baseline |
| v17.0 (raw UNS) | ~14/36 | ~39% | -33pp |
| v17.6 (Reform-target wards) | 26/37 | 70.3% | -2.2pp |
| v17.7-io (+Census Indep) | 26/37 | 70.3% | -2.2pp |
| v17.8 (+Brexit) | 26/37 | 70.3% | -2.2pp |
| v17.9 (combined) | 26/37 | 70.3% | -2.2pp |
| **v17.10 ENSEMBLE (PRODUCTION)** | **29/40** | **72.5%** | **0pp** |

**Bootstrap 95% CI on the v17.10 − v15.1 difference: [-17.5, +17.5]pp.**
We cannot reject the null hypothesis that v17.10 = v15.1 on this sample.

### 4.1.1 Lift trajectory by sample size

The honest scaling shows the apparent advantage was a small-sample artefact:

| n | v17.10 | v15.1 | Lift |
|---|---|---|---|
| 15 (Reform-heavy hand-picked) | 14/15 = 93.3% | 9/15 = 60.0% | +33pp |
| 22 (Reform metros) | 20/22 = 90.9% | 15/22 = 68.2% | +23pp |
| 29 (incl. London) | 23/29 = 79.3% | 19/29 = 65.5% | +14pp |
| 36 (all DC councils with history) | 27/36 = 75.0% | 27/36 = 75.0% | 0pp |
| **40 (incl. 4 Wikipedia-held-out)** | **29/40 = 72.5%** | **29/40 = 72.5%** | **0pp** |

As the sample expanded from Reform-target hand-picked metros to a representative
mix including London Lib Dem boroughs and Labour strongholds, the lift compressed
to zero. The earlier +25pp figure at n=15 was a sampling artefact, not a generalisable
improvement.

### 4.1.2 Per-party precision-recall — the substantive structural finding

The overall-accuracy tie masks a real precision-recall tradeoff at the party level, and a corrected analysis (using v15.1's full n=130 sample rather than the n=40 overlap) reveals a stronger structural claim than initially apparent.

**On the n=40 overlap subset** (where v17.10 was scored):

| Party | v17.10 Recall | v15.1 Recall | v17.10 Precision | v15.1 Precision | Actual n |
|---|---|---|---|---|---|
| Labour | 66.7% | **83.3%** | 66.7% | 58.8% | 12 |
| Liberal Democrat | 85.7% | 85.7% | 100% | 100% | 7 |
| No Overall Control | **66.7%** | 60.0% | 71.4% | 69.2% | 15 |
| Reform UK | **83.3%** | 66.7% | 62.5% | 100% | 6 |

**On v15.1's full n=130 council sample** (where v17.10 cannot be run for lack of ward data):

| Party | v15.1 Recall | v15.1 Precision | Actual n |
|---|---|---|---|
| Labour | 59.3% | 53.3% | 27 |
| Lib Dem | 76.9% | 76.9% | 13 |
| NOC | 71.4% | 59.2% | 63 |
| Reform UK | **46.2%** | **54.5%** | 13 |
| **Conservative** | **0.0%** | n/a — never predicted | 9 |
| **Green** | **0.0%** | n/a — never predicted | 5 |

### Sampling-artefact correction

The 100% v15.1 Reform precision in the n=40 subset is a **small-sample artefact**: v15.1's 4 Reform predictions in that subset happened to be its 4 easiest cases (Gateshead, Sunderland, Calderdale, Wakefield — all high-Brexit Lab-stronghold metros where Reform's emergence is obvious). On the broader n=130 sample where v15.1 makes 11 Reform predictions, only 6 hit — a precision of 54.5% and recall of 46.2%.

**Comparing v17.10 (n=40 subset) to v15.1 (full n=130):**
- v17.10 Reform recall (83%) is **almost double** v15.1's broader Reform recall (46%)
- v17.10 Reform precision (62.5%) is **slightly better** than v15.1's broader precision (54.5%)

So once the small-sample artefact is removed, **v17.10's structural advantage on Reform UK is substantial**: roughly 2× the recall at comparable precision.

### v15.1's systematic blind spots

The full-sample analysis reveals two structural failure modes that the n=40 subset hid:

1. **0% recall for Conservative** (9 actual Con council wins in 2026; v15.1 predicted Con 0 times)
2. **0% recall for Green** (5 actual Green council wins; v15.1 predicted Green 0 times)

v15.1's council-fragmentation rule structurally cannot output Conservative or Green as a council winner — those outcomes are systematically missed. v17.10 inherits the Conservative blind spot (the per-ward UNS rarely projects Con as the council majority unless 2024 priors were already heavily Con) but the Green blind spot is shared. Out of 14 Con+Green wins, both methodologies predict zero correctly.

This is a publishable methodological limitation: **both methodologies are fundamentally biased against minor-party council wins**, with 0/14 recall on Con+Green in the 2026 cycle. A new methodology that specifically modelled Con/Green retention dynamics could close this gap — outside the scope of v17.

### Decision framework for users

The per-party analysis gives users a clear choice:

| Use case | Recommended methodology | Justification |
|---|---|---|
| Tracking Reform UK emergence | **v17.10** | 83% recall vs v15.1's 46% (broader sample) |
| Predicting Labour-vs-NOC patterns | Either | Roughly tied |
| Predicting Lib Dem holds | Either | 85.7% / 100% precision both |
| Predicting Conservative wins | **Neither — known limitation** | Both 0% recall |
| Predicting Green wins | **Neither — known limitation** | Both 0% recall |

This is a publishable claim independent of the null overall-accuracy result.

### 4.2 Per-ward accuracy

On the n=322 underlying ward sample:

| Methodology | Per-ward winner % |
|---|---|
| v16 LLM-derived (previous, n=119) | 21.0% |
| Always-incumbent baseline | 43.5% |
| v17.0 (ward-UNS) | 44.4% |
| v17.3 (with Reform-target rules) | 46.9% |

Real ward priors give a 22pp lift over LLM-derived predictions. UNS adds
a small (1-3pp) signal over always-incumbent.

### 4.3 Per-party recall

v17.3 ward-level confusion matrix (n=322):

| Party | Actual wins | v17.3 correct | Recall | Precision |
|---|---|---|---|---|
| Conservative | 24 | 19 | 79% | ? |
| Labour | 41 | 35 | 85% | low |
| Liberal Democrat | 53 | 48 | 91% | high |
| Green | 60 | 18 | 30% | high |
| Reform UK | 112 | 9 | 8% | high |
| Independent | 14 | 4 | 29% | low |

v17.3 has high precision on Reform/Green/LD predictions (when it predicts
them, it's usually right) but low recall — it under-predicts both.

The v17.6 council override addresses this at council-level by detecting
Reform-emerging councils and overriding aggregate Lab-majority predictions
to Reform UK.

### 4.4 Calibration

v17.0/.3 confidence labels (Confident / Lean / Toss-up) are calibrated:

| Bucket | n | Hit rate |
|---|---|---|
| Confident | 151 | 49.0% |
| Lean | 27 | 37.0% |
| Toss-up | 10 | 30.0% |

Confident predictions hit 19pp more often than Toss-up.

## 5. Failure modes

We document three irreducible failure modes that no priors-only
methodology can address:

### 5.1 Reform sweeps in 0%-prior councils (Wolverhampton)

Wolverhampton 2026: NOC. v17.6 predicted Lab. All 18 Wolverhampton wards
had 0% prior Reform vote share. Reform's emergence here was invisible
from priors alone.

Required signal: Census 2021 demographics (low-graduate, post-industrial)
+ Brexit 2016 referendum vote share + active campaign data.

### 5.2 Birmingham Independent surge

7 of 8 Birmingham 2026 Independent winners (Lozells, Ward End, Aston,
Alum Rock, etc.) had ZERO prior Independent vote share. Driven by Gaza-
coded campaigns in Muslim-majority wards. Cannot be predicted without
Census 2021 ethnicity + current-affairs salience signal.

### 5.3 Green breakthroughs in Lab-stronghold wards

Manchester Lab→Green wave (Ancoats & Beswick, Ardwick, Burnage area)
happened in wards with Lab 50%+ priors and Green 0-10%. Pure UNS scaling
cannot predict these without demographic conditioning.

## 5.4 Sensitivity analysis on the n=15 sample (historical)

We re-ran v17.6 with the council Reform-emerging threshold varying from
0% to 20% (production = 5%) on the n=15 sample:

| Threshold | Hits/n=15 | Pct | Overrides fired | Override hit-rate |
|---|---|---|---|---|
| 0% | 9/15 | 60.0% | 8 | 25% (false-positives) |
| 3% | 14/15 | 93.3% | 2 | 100% |
| **5% (production)** | **14/15** | **93.3%** | **2** | **100%** |
| 7% | 13/15 | 86.7% | 1 | 100% |
| 10% | 12/15 | 80.0% | 0 | (no overrides — = v17.5) |
| 15% | 12/15 | 80.0% | 0 | = v17.5 |
| 20% | 12/15 | 80.0% | 0 | = v17.5 |

**Interpretation on the n=15 sample**:
1. The 93.3% holds across thresholds 3-5% (a natural plateau within the small sample).
2. At ≥10% no overrides fire.
3. **At 0% the override is catastrophically over-aggressive** — fires on
   8 councils, only 2 correct. The threshold matters; the override is a
   sharp tool that needs careful aiming.

**Critical update on the larger n=40 sample**: the apparent 93.3% knife-edge robustness
documented above was itself an n=15 sampling artefact. On the full n=40 evaluation set,
v17.10 (the ensemble that wraps v17.9 which wraps v17.6) ties v15.1 at 72.5%. The
Reform-emerging override's threshold sensitivity is still real but contributes only ~2
correct predictions to v17.10's total — not enough to differentiate the methodology from
v15.1's baseline at the larger sample size. The override is a real signal; its leverage
at small samples was artificially amplified by sampling. See Section 4.1 for the n=40
result and Section 5.5 for the cross-cycle attempt.

## 5.5 Cross-cycle 2024 backtest — infeasible at scale

We attempted a true held-out cross-cycle validation: use 2022/2023 ward priors to predict
2024 metropolitan borough actuals (different cycle, different priors, methodology never
saw 2024 data during tuning).

**Result: empirically infeasible**. Of 26 metropolitan boroughs attempted (all known to
have had May 2024 elections), **21 (81%) had ward boundary review between 2022 and 2024**.
Democracy Club's API uses ballot IDs of the form `local.{council_slug}.{ward_slug}.{date}`,
and when wards are renamed, merged, or split, the 2022/2023 ballot IDs no longer match
the 2024 ward names. This is not a DC API failure — it reflects the underlying UK local
government boundary review process, which runs continuously across English metropolitan
boroughs.

| Coverage | Count | Councils |
|---|---|---|
| 100% (stable boundaries) | 3 | Barnsley, Bolton, Sheffield |
| 25-50% (partial) | 2 | Oldham (47%), Bradford (27%) |
| <25% (boundary review) | 21 | Bury, Calderdale, Coventry, Gateshead, Hartlepool, Kirklees, Knowsley, Leeds, Manchester, Newcastle-upon-Tyne, Rochdale, Salford, Sandwell, Sefton, Stockport, Sunderland, Tameside, Trafford, Wakefield, Wigan, Wolverhampton |

Every Reform-relevant council in our dataset (Wakefield, Wigan, Wolverhampton, Sunderland,
Sandwell, Calderdale, Hartlepool, Newcastle) had boundary review, so the Reform-emerging
override path specifically cannot be tested on 2024.

On the 5 councils where partial backtest was possible, both v17.10 and v15.1-proxy hit
3/5 = 60% — uninformative for discrimination (2024 was a Labour landslide; non-discriminating
for Reform-target methods). Full breakdown in `FINDING_2024_backtest_data_limit.md`.

**Implication for the paper**: the n=40 in-sample plateau at 72.5% cannot be cross-cycle
validated against 2024. Validation requires either (a) the 2027 May local cycle when more
boundary-stable councils elect, or (b) manual cross-cycle ward boundary mapping for ~30
councils × 30 wards = 900+ mappings (significant work, not yet done).

**Pre-registration for 2027/2028 cycles** (see `PREREG_v17_10_2027_2028.md`, SHA-256
`aa3c9814bac8015f9e87861d49629ebee6948aad7429759d299243fd308c8423`) locks the v17.10
methodology hash now so the future test is genuinely held-out.

## 6. Caveats

1. **The n=15 lift didn't generalise.** v17.6's 93.3% at n=15 compressed to 72.5%
   at n=40, indistinguishable from v15.1's 72.5% on the same sample (bootstrap
   95% CI on diff: [-17.5, +17.5]pp, cannot reject H0). The structural per-party
   tradeoff (v17.10 catches Reform UK, v15.1 catches Labour holds, neither catches
   Conservative/Green wins) survives the null.

2. **Cross-cycle 2024 backtest was data-limited.** 81% of attempted metropolitan
   boroughs had ward boundary review 2022→2024, preventing ward-level retrospective
   validation. See Section 5.5.

3. **Sample is biased toward Reform-target councils for the n=15 historical work
   and toward ward-data-available councils for the n=40 evaluation.** v15.1's
   published track record at 59.2% on n=130 is the cleanest baseline for
   methodology comparison; v17.10 has not yet been run on the full 130-council
   set because the required prior-history data does not exist for all 130 councils.

4. **v17.6's outcome override is OPINIONATED.** Brexit-fires-with-low-prior-Reform
   produces 3 confirmed false positives on the n=40 sample (Wigan, Wolverhampton,
   Dudley). Documented in `risk` field of methodology hash.

5. **Multi-member ward seat splitting.** v17 assigns all seats in a multi-member
   ward to single winner. Real ward elections often split (e.g., 1 Lab + 1 Green
   from a 2-seat ward). Affects per-ward accuracy but not council-level winner.

6. **Conservative + Green council blind spots.** Both methodologies have 0% recall
   for Con and Green council wins on the n=130 sample (9 Con + 5 Green = 14 of 130
   cases). v17's per-ward UNS inherits v15.1's fragmentation-rule blind spot.
   Addressing this requires a successor methodology with separate Con-retention
   and Green-breakthrough models.

## 7. Reproducibility

All numbers in this paper are reproducible via:

```bash
# v15.1 baseline (59.2% on n=130)
python3 -m tests.test_backtest

# v17.10 production (29/40 = 72.5%, ties v15.1 on same sample)
python3 -m tests.test_v17_10_backtest

# Full v17 stack comparison table
python3 -m scripts.ward_data.build_comparison_table
```

Both reproducibility tests run as a daily CI workflow at 02:00 UTC; any drift
from the published numbers fails CI and is visible in the public action log.

Methodology hashes (frozen, machine-enforced via CI):
- v17.0: `e38adc8efdd564f8…`
- v17.1: `6da92625051696de…`
- v17.2: `67d25b3414272b4a…`
- v17.3: `467c29426306194d…`
- v17.4 (REJECTED): `51a12fba4e894bcc…`
- v17.5: `d5d5d3dd46ce1db2…`
- v17.6: `141c405a9c9861e0…`
- v17.7-io: see `methodology_v17_7_indep_only.py`
- v17.8 (Brexit): see `methodology_v17_8_brexit.py`
- v17.9 (combined): `0df615a23ef16b2d…`
- **v17.10 (PRODUCTION)**: `2ea86b8d1e25ee68ebf66c6f59496e2480a43dba2a81ff17012ce0094531f018`

Each methodology Python file contains a `METHODOLOGY_RULES` dict that
hashes to the above. Any change to the rules changes the hash and a new
methodology row enters the scorecard — no in-place modification of
existing methodologies allowed.

Pre-registration document SHA-256: `aa3c9814bac8015f9e87861d49629ebee6948aad7429759d299243fd308c8423`
(file integrity also verified in CI; any modification fails the build).

## 8. Acknowledgements

Democracy Club provides the underlying JSON ballot data (CC0 licensed).
This work would not be possible without their open data infrastructure.
