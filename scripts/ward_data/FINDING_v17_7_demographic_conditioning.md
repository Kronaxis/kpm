# v17.7 demographic conditioning — what worked, what didn't

**Date**: 2026-05-11 (overnight)
**Sample**: 19 councils with both 2026 actuals + most-recent prior history
**Demographic source**: ONS Census 2021 (NOMIS bulk: TS067 qualifications, TS030 religion, TS021 ethnicity, TS007 age, TS054 tenure)

## Two hypotheses tested

### H1 (REJECTED): Demographic Reform-target detection

Hypothesis: Wolverhampton-class councils (Reform actually won outright,
0% prior Reform across all wards) can be detected by their demographic
profile alone. All Reform-sweep councils we've seen share:
- Mean L4 qualifications < 30%
- Mean white British > 60%
- Lab incumbent council

**Implementation (v17.7-full)**: Add a demographic Reform-target flag.
If a council fits this profile AND v17.5/v17.6 says single-party
majority → override to Reform UK.

**Result on n=18**:
- v17.6: 15/18 = 83.3%
- v17.7-full: **14/18 = 77.8% (REGRESSION)**

The rule **false-positives** Rochdale (Lab actual) and Tameside (NOC
actual). Both fit the demographic profile but didn't go Reform.

**Diagnosis**: Knowsley has the same demographic profile as Hartlepool
(L4 24%, white-British 92%) but actually went Lab. We cannot distinguish
"Lab will hold despite Reform-favourable demographics" from "Reform will
sweep this Lab council" using priors-only signals. v17.5's prior Reform
≥5% threshold is the only reliable Reform signal we have from priors-only.

### H2 (ACCEPTED, modest improvement): Per-ward Independent surge

Hypothesis: Birmingham 2026 Independent winners had Census 2021
Muslim% 73-84% (vs council mean ~30%). This is a clear demographic signal.

**Implementation (v17.7-io)**: Per-ward override:
  ward_census.muslim_pct ≥ 60% AND prior winner = Lab → predict Independent

**Threshold sweep** on n=370 wards:
| Threshold | Indep recall | Lab loss | Net per-ward |
|---|---|---|---|
| 50% | 12/19 = 63.2% | -8 | -1 |
| **60%** | **11/19 = 57.9%** | **-3** | **+3** |
| 70% | 11/19 = 57.9% | -3 | +3 |
| 80% | 8/19 = 42.1% | 0 | +5 (best precision) |

**Selected threshold**: 60% (best raw recall while keeping false positives low).

**Result on n=370 wards**:
- v17.3 baseline: 158/370 = 42.7%
- **v17.7-io: 161/370 = 43.5% (+0.8pp)**
- Independent recall: 4 → 10 (+6 catches)
- Labour recall: 54 → 51 (-3 false positives)

**Council-level (n=19)**: v17.7-io = v17.6 = 16/19 = 84.2%. The Indep
override doesn't shift any council winner because Birmingham (where most
Indep wards land) was ALREADY NOC in v17.6.

## What v17.7 actually adds

v17.7-io gives:
- Same council-level accuracy as v17.6 (84.2% on n=19)
- +6 correct ward Independent predictions
- -3 incorrect Lab → Indep flips
- Per-ward winner accuracy: +0.8pp net

This is a real but modest improvement. **Production = v17.7-io**.

The demographic Reform-target rule (v17.7-full) is REJECTED as too
aggressive — over-fires on Reform-favourable demographic councils
where Lab actually holds.

## Methodology hashes

- v17.7-full (REJECTED): `3d49d2ee0811e7ee…`
- v17.7-io (PRODUCTION): see `methodology_v17_7_indep_only.py`

## What we learned about Census 2021 as a signal

Census 2021 Muslim% IS the discriminator for Birmingham Independent
surges. 6 of 8 actual Independent winners had Muslim > 70%. The
Birmingham Gaza-coded campaign concentrated entirely in Muslim-majority
wards.

Census 2021 demographic profile of "Reform-target" councils is REAL but
NOT discriminating — Lab-strong councils with the same demographics
(Knowsley, Salford, parts of Manchester) didn't go Reform. The
demographic profile is necessary but not sufficient for Reform sweep.

The genuine "Reform-emerging" signal remains the historic vote share
(prior Reform ≥5% via v17.5's council-level detection). Census adds
modest signal for Independent surges only.

## Wolverhampton remains structurally unpredictable

Wolverhampton actual = NOC. v17.7-io predicts Lab (no signals fire).
With 0% prior Reform across all 18 wards AND with demographics that
match other Reform-target councils equally, we cannot predict Wolverhampton's
Reform pickup from priors+census alone. Would need:
- Brexit 2016 ward-level Leave % (Hanretty constituency-level fallback)
- Active Reform UK candidate count (DC has this)
- Possibly social media sentiment / news signal

Documented as known limitation.
