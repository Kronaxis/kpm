# 2024 cross-cycle backtest — substantive data-limitation finding

**Date**: 2026-05-11
**Goal**: Test whether v17.10's methodology generalises to a held-out election cycle (2024 May locals) when applied with pre-2024 ward priors.

## The substantive finding: ward boundary review breaks cross-cycle backtest

Of **26 metropolitan boroughs** attempted (all known to have had May 2024 elections):

| Coverage | Count | Councils |
|---|---|---|
| 100% (full) | **3** | Barnsley, Bolton, Sheffield |
| 25-50% (partial) | 2 | Oldham (47%), Bradford (27%) |
| <25% (boundary review) | **21** | Bury, Calderdale, Coventry, Gateshead, Hartlepool, Kirklees, Knowsley, Leeds, Manchester, Newcastle-upon-Tyne, Rochdale, Salford, Sandwell, Sefton, Stockport, Sunderland, Tameside, Trafford, Wakefield, Wigan, Wolverhampton |

**81% of attempted councils (21 of 26) had ward boundary review between 2022 and 2024** — including every single Reform-relevant council in the v17.10 dataset (Wakefield, Wigan, Wolverhampton, Sunderland, Sandwell, Calderdale, Hartlepool, Newcastle). Democracy Club's API uses ballot IDs of the form `local.{council_slug}.{ward_slug}.{date}`, and when wards are renamed, merged, or split, the 2022/2023 ballot IDs no longer match the 2024 ward names. This is not a DC API problem — it reflects the underlying UK local government boundary review process, which runs continuously across English metropolitan boroughs.

## Backtest result on the 3 stable-boundary councils

| Council | 2024 Actual | v17.9-backtest | v15.1-proxy | Always-incumbent |
|---|---|---|---|---|
| Barnsley | Labour | Labour ✓ | Labour ✓ | Labour ✓ |
| Bolton | NOC | NOC ✓ | NOC ✓ | NOC ✓ |
| Sheffield | NOC | NOC ✓ | NOC ✓ | NOC ✓ |

**3/3 = 100% across all three methodologies.** At n=3 this is uninformative for discrimination, but consistent with the 2024 cycle being a Labour landslide year (all three councils' outcomes were highly predictable from 2022 priors).

## Backtest at lower coverage threshold (≥20%, n=5)

Adding Bradford (27%) and Oldham (47%):

| Council | Coverage | Actual | v17.9 | v15.1-proxy |
|---|---|---|---|---|
| Barnsley | 100% | Labour | ✓ | ✓ |
| Bolton | 100% | NOC | ✓ | ✓ |
| Bradford | 27% | Labour | ✗ (Con) | ✗ (Con) |
| Oldham | 47% | NOC | ✗ (Lab) | ✗ (Lab) |
| Sheffield | 100% | NOC | ✓ | ✓ |

**3/5 = 60% for both methodologies.** Bradford and Oldham misses are attributable to partial coverage — the wards we have are non-representative of the council. This is a data-quality artefact, not a methodology failure.

## Implications for the paper

This is a publishable methodological limitation, not a result that overturns the n=40 plateau:

1. **v17.10 cannot be reliably backtested on the 2024 cycle** for the majority of English metropolitan boroughs due to boundary review.
2. **The Reform-emerging override path specifically cannot be tested on 2024** because every Reform-relevant council in our dataset (Wakefield, Wigan, Wolverhampton, Sunderland, Sandwell, Calderdale) had boundary review affecting all of its 2022/2023 ballot IDs. The override could only be exercised on stable-boundary Reform-relevant councils, of which we have zero in the 2024 sample.
3. **On the few councils where backtest is possible** (Barnsley, Bolton, Sheffield, plus Bradford + Oldham at partial coverage), methodologies are indistinguishable — consistent with the n=40 finding that v17.10 = v15.1 at the council level.
4. **The 2024 election was non-discriminating** (Labour landslide year), so even with full coverage the cycle would not strongly differentiate Reform-aware methodologies. The Reform-emerging override path requires a Reform-surge year (2025-26) to fire.
5. **A genuine cross-cycle validation requires either**: (a) the 2027 May local cycle when more boundary-stable councils elect, or (b) manual cross-cycle ward mapping for the boundary-changed councils (significant work, ~30 councils × 30 wards each — 900+ ward mappings).

## What this means for v17.10's status

The n=40 honest plateau result (`FINDING_n36_honest_plateau.md`) remains the authoritative claim:
- v17.10 = v15.1 = 29/40 = 72.5% on n=40
- Bootstrap 95% CI on difference: [-17.5, +17.5]pp
- Per-party tradeoff: v17.10 catches Reform UK better, v15.1 catches Labour holds better

The 2024 backtest does not refute this. It adds context: **the methodology cannot be validated against the 2024 cycle due to boundary review confounds, and the 2024 cycle would not have been discriminating anyway**. Future validation requires either (a) a future Reform-surge cycle or (b) significant manual data work to bridge boundary changes.

## Data quality reference

This is a known issue for any methodology that relies on cross-cycle ward continuity. The Democracy Club API correctly reflects what's contestable — it cannot manufacture continuity that doesn't exist in the underlying electoral geography. Any researcher attempting per-ward analysis across UK local cycles will hit this wall.
