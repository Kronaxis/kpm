# v17 per-party failure modes — empirically diagnosed (n=188)

**Date measured**: 2026-05-10
**Sample**: 188 wards across Birmingham + Eastleigh + Hartlepool + Leeds + Manchester + Newcastle + Sheffield
**Method**: confusion matrix (actual ward winner × v17 predicted winner)

## Headline: v17 has 0% recall on 48 actual Reform UK ward wins

| Party | Actual wins | v17 predicted | Correct | Recall | Precision |
|---|---|---|---|---|---|
| **Reform UK** | **48** | **0** | **0** | **0.0%** | — |
| Independent | 10 | 5 | 2 | 20.0% | 40.0% |
| Green | **52** | 16 | 14 | **26.9%** | 87.5% |
| Labour | 28 | **104** | 25 | 89.3% | **24.0%** |
| Conservative | 16 | 22 | 14 | 87.5% | 63.6% |
| Liberal Democrat | 31 | 36 | 29 | 93.5% | 80.6% |
| **Total** | **185** | **183** | **84** | **45.4%** | **45.9%** |

(2 wards excluded: small-party tossups Workers Party / Garforth Indep / SDP)

## Three structural failure modes

### 1. Reform UK: zero recall on 48 actual wins (proven at scale)

v17 applied UNS_2024_TO_2026 (Reform +12pp) to wards where Reform was at
0% in 2024. Result: 12% projected — loses to incumbent Lab/LD at 30%+.
**v17 has no mechanism to predict Reform breakthroughs.**

Hartlepool is the most extreme case: Reform won every single ward in our
sample (11 wards). v17 predicted Reform 0 times. The Reform sweep was
unforeseeable from priors-only because Reform had no prior local
infrastructure to project from.

Reform's 2026 success was concentrated in post-industrial Northern wards
with no prior Reform candidate. UNS treats this uniformly across all
wards — it should NOT. v17.1 needs a "Reform-target detector" that
identifies these wards independently of prior Reform vote share.

### 2. Green: 76% miss rate on actual Green wins

v17 captured 9 of 38 Green ward wins (mostly in Sheffield where Green
already had prior strength). The 29 misses split:
- 26 wards: predicted Labour (Lab→Green flip in young metropolitan wards)
- 2 wards: predicted Liberal Democrat
- 1 ward: predicted Workers Party of Britain

Green's 2026 success in Manchester (Ancoats, Ardwick, Burnage area) and
Sheffield was concentrated in young, degree-educated wards. UNS Green +3pp
applied to a Green-baseline of 5% gives 8% projected — still loses to
Lab at 50%+.

### 3. Independent: 0% recall (Birmingham Gaza)

Already documented in `FINDING_v17_ward_uns.md`. Birmingham Independents
emerged from 0% prior share. Cannot be predicted from priors alone. 6 of
8 Independent wins predicted as Labour, 2 as Liberal Democrat.

## The Labour over-prediction problem

v17 predicted Labour in **71 of 116 wards** when Lab actually won only **18**.
Precision is 22.5%. Why: Lab was the prior winner in many wards
(Birmingham 2022, Manchester 2024). UNS Lab -10pp shaves Lab's projected
share but rarely enough to change the largest-share-wins outcome.

## What this means for v17.1

**Drop UNS as the primary projection layer.** Empirically it doesn't help.
Build instead:

1. **Reform-target detection**: identify wards by demographic profile
   (post-industrial Northern, low-graduate, high-Leave-vote-2016) — apply
   a Reform-emergence prior independent of prior Reform vote share.

2. **Green-target detection**: identify wards by demographic profile
   (urban-core, high-graduate, young-skewing) — apply a Green-emergence
   prior independent of prior Green vote share.

3. **Independent-detection**: requires Census 2021 ethnicity + active
   campaign signals (already documented as unpredictable from priors).

4. **Lab-incumbent erosion model**: Lab's prior share doesn't simply lose
   10pp to Reform/Green uniformly — the loss is concentrated in
   demographically-typed wards. Need conditional swing per ward type.

The v17 floor (39.7% with naive UNS) tells us how much can be done with
priors-only. v17.1 with demographic conditioning needs to beat 39.7% to
be worth the additional complexity.

## Reproducibility

```bash
python3 -m scripts.ward_data.per_party_recall_v17
```
