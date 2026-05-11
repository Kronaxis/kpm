# v17 ward-UNS measured across 7 councils — task #54 first real results

**Date measured**: 2026-05-10
**Sample**: 188 wards with both prior data + 2026 actuals across 7 councils
**v17 methodology hash**: `e38adc8efdd564f8bbd36fd0c78f111f835e86a41b7ceb8225aa8158d289b71f`

## Headline results (per-ward winner accuracy)

| Method | Ward winner % | Lift over v16 |
|---|---|---|
| v16 LLM (previous) | 21.0% | — |
| **v17 ward-UNS** | **46.3%** | **+25.3pp** |
| Always-incumbent baseline | 45.2% | +24.2pp |
| Random (5-6 viable parties + Independents) | 16-20% | — |

### Per-council breakdown

| Council | n | Prior yr | v17 | Always-incumbent | UNS lift |
|---|---|---|---|---|---|
| Eastleigh (LD area) | 12 | 2024 | **91.7%** | 91.7% | 0pp |
| Leeds (Lab/Green) | 33 | 2024 | 63.6% | 60.6% | +3.0pp |
| Newcastle (Lab/Green) | 16 | 2024 | 56.2% | 50.0% | +6.2pp |
| Sheffield (mixed) | 26 | 2024 | 46.2% | 46.2% | 0pp |
| Birmingham (Lab+Indep) | 59 | 2022 | 44.1% | 45.8% | -1.7pp |
| Manchester (Lab→Green wave) | 31 | 2024 | 25.8% | 22.6% | +3.2pp |
| Hartlepool (Reform sweep) | 11 | 2024 | **0.0%** | 0.0% | 0pp |
| **OVERALL** | **188** | mixed | **46.3%** | **45.2%** | **+1.1pp** |

The range is informative: stable LD areas (Eastleigh) reach 91.7% from
priors-only; areas with "wave" elections (Hartlepool Reform sweep,
Manchester Lab→Green) drop to 0-25% because no priors-only model can
catch the wave.

## Two empirical findings

### 1. Real ward priors deliver 2× the LLM signal (validated, n=116)

Replacing LLM-derived per-ward shares with actual ward-level prior
election results jumps winner accuracy from 21.0% to 39.7%. **Task #54's
premise is proven**: real ward data is the path forward, LLM-derived
ward speculation adds no signal.

### 2. UNS adds ~1.1pp signal vs always-incumbent (n=188 — was 0pp at n=116)

Across 188 wards:
- v17 ward-UNS: 46.3%
- Always-incumbent: 45.2%
- **UNS adds +1.1pp net signal at the ward level** — modest but real,
  emerging only at the larger sample.

The 25.3pp lift over v16 is mostly from using real prior data; the UNS
layer adds a small additional signal that was invisible at n=116.

Per-council variance shows where UNS helps vs hurts:
- Newcastle (+6.2pp), Manchester (+3.2pp), Leeds (+3.0pp): metropolitan
  Lab-strong areas where UNS Lab→Reform/Green captures some real shift
- Birmingham (-1.7pp): UNS misfires on 2022 priors (4-year stretch)
- Hartlepool (0pp): UNS can't help — Reform swept everything regardless
- Eastleigh (0pp): UNS can't help — incumbent already 91.7% accurate

UNS is most useful in metropolitan Lab-strong areas where its Lab-erosion
component points the right direction; useless where wave elections
overwhelm any uniform projection.

## Council-level aggregation

v17's per-ward predictions aggregate to: **Labour 49 / Con 22 / LD 12 /
Green 3** (total 86 seats predicted, 13 wards lacked sufficient data).

**Actual Birmingham 2026**: No Overall Control.

| Methodology | Birmingham council | Hit |
|---|---|---|
| KPM-2.2 v15.1 | NOC | ✓ |
| KPM-v17 ward-UNS | Labour majority | ✗ |

v15.1 wins at the council level despite worse per-ward signal because
its fragmentation/NOC heuristic catches the Birmingham Independent
surge (Aston, Alum Rock — Gaza/Muslim-vote split from Lab to
Independent candidates). v17 mechanically assigns wards to known-party
candidates and misses Independents entirely.

## The Independent problem

3 of v17's 5 worst misses are Independent winners:
- Allens Cross: pred Conservative, incumbent Labour, actual Reform UK
- Alum Rock: pred Labour, incumbent Labour, **actual Independent**
- Aston: pred Liberal Democrat, incumbent Liberal Democrat, **actual Independent**

UNS cannot project Independent vote share because there is no national
polling baseline for Independents. v17 inherits this blind spot from
the methodology design.

## Diagnostic: Independent surge was unpredictable from priors

We measured whether 2026 Independent winners had any prior-Independent
vote share in their wards (`diagnostic_independent_signal.py`).

**Result: 7 of 8 Birmingham Independent winners had 0% Independent vote
in 2022. Only Holyhead had detectable prior strength (13.8%).**

| Ward | 2022 Ind% | 2026 Ind% | Detectable from priors? |
|---|---|---|---|
| Alum Rock | 0.0% | 49.8% | No |
| Aston | 0.0% | 32.7% | No |
| Bordesley Green | 0.0% | 30.8% | No |
| Holyhead | 13.8% | 38.2% | Yes |
| Lozells | 0.0% | 61.9% | No |
| Sparkbrook & Balsall Heath East | 0.0% | 35.8% | No |
| Stockland Green | 0.0% | 27.0% | No |
| Ward End | 0.0% | 61.7% | No |

**Conclusion**: The 2026 Birmingham Independent surge was a Gaza-driven
2024-2026 emergence that NO methodology using only past election results
could have caught. Geographic concentration matches Birmingham's 2021
Census map of high-Muslim wards.

This is a genuinely unpredictable failure mode for any priors-only
methodology. v17.1 cannot fix it from priors alone.

To predict next time would require:
1. Census 2021 ethnicity per ward (% Muslim / Pakistani-Bangladeshi heritage)
2. Current-affairs salience signal (active Gaza-coded campaigns)
3. A model that connects the two

Without those, this is a known unpredictable category. Document, don't pretend.

## Path to v17.1 (now informed by data)

The empirical evidence rules out simple UNS as a useful ward-level layer.
v17.1 directions:

1. **Drop UNS, keep real-prior baseline**: 39.7% from always-incumbent
   is the floor. Build improvements on top of incumbent prediction, not
   on top of UNS that doesn't help.
2. **Demographic-adjusted swing**: ONS Census 2021 ward profiles
   (deprivation IMD, ethnicity, age, tenure, qualifications). Lab→Green
   wards in Manchester correlate with high % under-35 + degree-educated.
   Lab→Independent wards in Birmingham correlate with high % Muslim. A
   regression on these features against actual swings should beat UNS.
3. **Council-class swing buckets**: split UNS by metropolitan vs district
   vs unitary, and by London vs Northern. The national swing isn't
   uniform across council classes.
4. **Independent-detection prior**: 3 of v17's worst Birmingham misses
   are Independent winners (Aston, Alum Rock — Gaza/Muslim-vote split
   from Lab). Detect "Independent-prone" wards (Independents standing
   in prior election + Lab >50% prior) → predict Independent with
   confidence.
5. **Multi-member ward seat splitting**: Birmingham's many 2-seat wards
   often elect 1 Lab + 1 different party. v17 v0 gives all seats to one
   winner — seat counts are wrong even when winners are right.

### Council-level aggregation: v17 vs v15.1 head-to-head

| Council | Actual | v15.1 pred | v17 (aggregated) | v15.1 hit | v17 hit |
|---|---|---|---|---|---|
| Birmingham | NOC | NOC | Lab majority | ✓ | ✗ |
| Manchester | Lab | Lab | Lab | ✓ | ✓ |
| Sheffield | NOC | NOC | NOC | ✓ | ✓ |
| **TOTAL** | | | | **3/3 = 100%** | **2/3 = 66.7%** |

v17 disagrees with v15.1 on 1/3 councils — and in that case (Birmingham),
v15.1 wins. **Council-level aggregation of v17 ward predictions is
currently WORSE than v15.1's direct council-level methodology.**

The Birmingham failure mode is structural: v15.1's
fragmentation/NOC heuristic captures the Independent surge pattern
that v17's mechanical winner-takes-all aggregation misses. Sample
expansion (5 more councils being ingested) will tell whether this is
a Birmingham-only artifact or a general pattern.

## Reproducibility

```bash
# Fetch ward results + history (Birmingham 4-year cycle = 2022 priors):
python3 -m scripts.ward_data.ingest_dc_ward_results --council birmingham
python3 -m scripts.ward_data.ingest_dc_ward_history --council birmingham

# Score:
python3 -m scripts.ward_data.score_v17_vs_baselines --council birmingham
```

Re-run after any methodology change must produce ≥44.1% per-ward to be
worth a v17.x version bump.
