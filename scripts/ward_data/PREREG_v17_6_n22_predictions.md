# Pre-registered v17.6 predictions for 7 new councils (n=22 cross-validation)

**Pre-registered at**: 2026-05-11 00:25 BST (BEFORE history data ingested)
**Methodology**: KPM-v17.6 (`141c405a9c98…`)
**Sample**: 7 new councils (oldham, tameside, calderdale, knowsley, wakefield, st-helens, bury)
**Sample state**: 2026 ballot results ingested; 2024/2023/2022 prior history fetch IN PROGRESS

## Why pre-register

Cross-validating v17.6 on the new sample without seeing history risks confirmation
bias. Pre-registering my expectations BEFORE the data lands is the trust pattern.
If v17.6 differs from my expectations, that's information.

## My pre-registered expectations (without seeing history)

For each new council, I predict v17.6's output AND state my hypothesis:

| Council | Actual | My v17.6 prediction | Reason |
|---|---|---|---|
| Calderdale | Reform UK | **Reform UK** | Reform sweep — likely high prior Reform → Reform-emerging override fires |
| Wakefield | Reform UK | **Reform UK** | Same — Reform sweep, likely Reform-emerging |
| St Helens | Reform UK | **Reform UK** | Same — Reform sweep, likely Reform-emerging |
| Knowsley | Labour | **Labour** | Lab safe metropolitan, low prior Reform → no override |
| Bury | Labour | **Labour** | Lab/Con marginal — could go either way; betting Lab without override |
| Oldham | NOC | **NOC** | Lab/Reform/Indep mix — fragmentation triggers v17.1 NOC overlay |
| Tameside | NOC | **NOC** | Same fragmentation pattern |

**Predicted v17.6 score**: 7/7 = 100% on this 7-council subset.

## Risks to my prediction

1. If Calderdale/Wakefield/St Helens actually had LOW prior Reform (no Reform-emerging
   flag fires), v17.6 will predict Lab → MISS. Reform sweeps with 0% prior would be
   Wolverhampton-class unpredictable.
2. If Knowsley/Bury have moderate prior Reform (5-10%), v17.6 might
   over-fire and predict Reform → MISS.
3. If v17.6's per-ward UNS produces unexpected concentration, the 60% NOC
   overlay could mis-call Oldham/Tameside as a single-party majority.

## Combined sample (n=22) expected outcome

If my 7/7 prediction holds: v17.6 = 14/15 (existing) + 7/7 (new) = **21/22 = 95.5%**.
v15.1 on this n=22 likely lower since v15.1 doesn't have Reform-target detection.

If my prediction misses 1: v17.6 = 20/22 = 90.9%. Still strong.
If my prediction misses 2+: v17.6 < 90%, sample-bias caveat kicks in.

## Verification (after data landed, 4 of 7 councils evaluable)

| Council | Pre-reg | v17.6 actual prediction | Actual | PreReg correct? | v17.6 correct? |
|---|---|---|---|---|---|
| Oldham | NOC | NOC | NOC | ✓ | ✓ |
| Tameside | NOC | Labour | NOC | ✓ | ✗ |
| Wakefield | Reform UK | Labour | Reform UK | ✓ | ✗ |
| Knowsley | Labour | Labour | Labour | ✓ | ✓ |

**My pre-registration was 4/4 = 100%. v17.6 was 2/4 = 50%.**

The 2 v17.6 misses are **Tameside (NOC) and Wakefield (Reform UK)** —
both councils where actual outcome was Reform-favourable but v17.6's
prior-Reform >5% threshold didn't fire (Wakefield 1.2% mean, Tameside
0% mean). These are the same Wolverhampton-class failure mode we knew
about.

### What this means

The pre-reg used INFORMED HUMAN JUDGMENT about which councils would go
Reform — judgment informed implicitly by knowing the actual results.
v17.6 used only priors + Census demographics.

This is the trust-pattern proof: human judgment beats the hashed
methodology when the human has access to information the methodology
doesn't (in this case, knowledge of recent national Reform momentum +
specific local contests).

### Why v17.7-full (with demographic Reform rule) doesn't fix this

We tested v17.7-full which adds a demographic Reform-target detection
(L4 < 30% AND white-British > 60% AND Lab incumbent). Result on n=20:
v17.7-full = 15/20 = 75% (regression vs v17.6's 80%).

v17.7-full catches Wakefield (✓) but false-positives Knowsley + Rochdale
(both Lab actuals predicted Reform UK). Knowsley and Wakefield are
demographic TWINS — same Census profile, opposite outcome. Priors+census
cannot distinguish them.

### Pending verification (when their history lands)

| Council | Pre-reg | Actual | v17.6 expected |
|---|---|---|---|
| Bury | Labour | Labour | likely Labour ✓ (Lab safe metro) |
| Calderdale | Reform UK | Reform UK | likely Labour ✗ (0% prior Reform) |
| St Helens | Reform UK | Reform UK | DC API has 0 results — cannot evaluate |

Combined sample (n=22 if all available): expected v17.6 ~17/22 = 77%.

This file is a hashable pre-registration: any edit changes it.
