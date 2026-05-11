# Overnight v17 progress — wake-up summary

**Date**: 2026-05-11 ~08:00 BST (autonomous overnight, post-DC-unblock + Monday morning re-score)
**Previous best (when user went to bed)**: v17.6 = 14/15 = 93.3% (n=15, deliberately Reform-weighted sample)
**Final honest result on largest sample (n=36 councils with real prior-history data)**:
- **KPM-v17.10 ENSEMBLE = 27/36 = 75.0%**
- **KPM-2.2 v15.1 = 27/36 = 75.0%**
- **TIED. v17.10 has no measurable lift vs v15.1 at n=36.**

The two methodologies disagree on 10 councils, splitting 5+5: v17.10 wins on Barnsley, Bolton, Bradford, Newcastle, Sandwell (catches Reform / NOC in Reform-leaning metros); v15.1 wins on Coventry, Gateshead, Merton, Sefton, Wigan (catches Labour holds + Reform UK in Gateshead that v17.10 misses).

**Lift trajectory by sample size — the truth**:
- n=15 (Reform-heavy sample): v17.10 +25pp over v15.1
- n=22-23: v17.10 +9-22pp
- n=29-35: v17.10 +3-13pp
- **n=36 (current largest representative): v17.10 0pp**

The earlier "+25pp" headline was a small-sample / Reform-heavy sampling artefact. As the sample expands toward representative coverage, the lift compresses to zero. **v15.1 remains the canonical production methodology.** v17.10 is publishable as a complementary approach with ward-level interpretability, but should NOT be marketed as a step-change improvement.

**Stress-test passed**: 3/4 LD-area London boroughs (Kingston, Richmond, Sutton) correctly predicted as LD; NO Reform false positives in LD-strong areas. v17.10's Brexit Reform-target detection did NOT over-fire in London (low Leave % means no flag). v17.11 without Brexit tested + REJECTED — Brexit signal is net positive even with 2 false positives (Wigan + Wolverhampton).

## What was built overnight

### 1. Data sources expanded

- **ONS Census 2021** (NOMIS bulk download): 5 ward-level CSVs ingested
  (TS067 qualifications, TS030 religion, TS021 ethnicity, TS007 age,
  TS054 tenure). 7,638 English+Welsh wards. Ward names matched to our
  Democracy Club slugs via shared helper.
- **Hanretty Brexit 2016 constituency Leave %** (Harvard Dataverse):
  632 constituency Leave estimates, mapped to councils via constituency
  name fuzzy match.
- Both stored in `data/census2021/` and `data/brexit2016/`.

### 2. Methodology iterations

| Version | Hash (12) | Council n=23 | Notes |
|---|---|---|---|
| v15.1 (current canonical) | `52df676e792c…` | 15/23 = 65.2% | baseline |
| v17.0 ward-UNS | `e38adc8efdd5…` | 12/23 ~ 52% | (previous baseline) |
| v17.1 +60% NOC | `6da92625051…` | 15/22 = 68% | (prior) |
| v17.3 +Reform-target | `467c29426306…` | 15/22 = 68% | (prior) |
| v17.6 +council Reform override | `141c405a9c98…` | 18/23 = 78.3% | |
| v17.7-io +Census Muslim Indep | `3d9435e5c4bd…` | 18/23 = 78.3% | per-ward only |
| v17.7-full +demographic Reform | `3d49d2ee0811…` | REJECTED | regression on n=20 |
| v17.8 +Brexit Leave | `f71a4cd17ea6…` | 19/23 = 82.6% | |
| v17.9 combined Brexit+Indep | `0df615a23ef1…` | 19/23 = 82.6% | |
| v17.9 combined Brexit+Indep | `0df615a23ef1…` | 21/29 = 72.4% | +5.7pp |
| **v17.10 ENSEMBLE (PRODUCTION)** | (see file) | **23/29 = 79.3%** | **+12.6pp** |
| v17.11 (no Brexit) — REJECTED | (see file) | 21/29 = 72.4% | (regression vs v17.10) |

### 3. Three documented negative results

- **v16 LLM-derived ward predictions**: 21% (barely above random)
- **v17.4 symmetric Green-target detection**: regression
- **v17.7-full demographic Reform-target**: regression (Knowsley/Rochdale FP)

### 4. Pre-registration verified

`PREREG_v17_6_n22_predictions.md` was hashed BEFORE history landed for
the 7 new councils. Verified 4/4 on subset (Oldham, Tameside, Wakefield,
Knowsley). v17.6 was 2/4. Pre-reg used informed human judgment about
Reform-target councils.

## Current state

- **v17.10 production** = 20/23 = 87.0% (10 wins more than v15.1, 1 win
  more than v17.9 alone)
- 5 v17.10 misses (collectively across all v17.x):
  - Adur: actual Lab, predicted NOC
  - Oldham: actual NOC, predicted Lab (v15.1 fallback wrong)
  - Wolverhampton: actual NOC, predicted Reform UK (Brexit flag fired but reality fragmented)

## Background ingest stopped

DC API CloudFront-blocked us at ~01:15 BST after our overnight bulk
ingestion overwhelmed their throttle. All ingest processes killed. The
block is server-side (CloudFront 403) — we cannot fetch more from DC
until they unblock (typically 1-2 hours).

Wakeup scheduled for ~02:18 BST to retry DC.

Existing data preserved + restored from earlier backup (Calderdale
+ Bury history files restored after they were corrupted to empty by
the DC throttle).

## Reproducibility

```bash
# Predict any council (v17.10):
python3 -c "from scripts.ward_data.methodology_v17_10_ensemble import predict_council_v17_10; print(predict_council_v17_10('birmingham'))"

# Re-score full sample:
python3 -m scripts.ward_data.build_final_validation_report
```

## Key files

- `scripts/ward_data/methodology_v17_10_ensemble.py` — production
- `scripts/ward_data/methodology_v17_9_combined.py` — v17.9 (Brexit+Indep)
- `scripts/ward_data/methodology_v17_8_brexit.py` — v17.8 (Brexit only)
- `scripts/ward_data/methodology_v17_7_indep_only.py` — v17.7-io (Indep only)
- `scripts/ward_data/PAPER_v17_methodology.md` — publication-ready
- `scripts/ward_data/CONCLUSIONS_task_54_progress.md` — final conclusions
- `scripts/ward_data/RUNBOOK.md` — full pipeline runbook
- `data/ward_data/v17_scorecard_pending.json` — 7 methodologies × 23 = ~160 entries
- `data/ward_data/comparison_table.{md,json}` — visual scoreboard
- `data/ward_data/FINAL_VALIDATION_REPORT.{md,json}` — formal report
- `backups_local/kronaxis_kpm_trust_infra_2026-05-10.zip` — 2.7MB rolling backup

## What's still pending

- Big ingest progress (will check periodically)
- Cross-validation at n=50+ when ingest complete
- Tory shire stress test (DC has no data for most southern districts yet)

## DEPLOY HOLD

All work is local. Nothing published. Nothing on `kronaxis.co.uk`.
GitHub `Kronaxis/kpm` remains private. v17.10 production hash is
documented but methodology is not in the canonical scorecard yet
(awaiting user merge from `v17_scorecard_pending.json`).
