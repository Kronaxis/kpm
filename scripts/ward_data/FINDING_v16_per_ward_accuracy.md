# v16 per-ward prediction accuracy — direct test

**Date measured**: 2026-05-10
**Sample**: 119 wards across Birmingham (62), Sheffield (26), Manchester (31)
**Source of actuals**: Democracy Club JSON API (`candidates.democracyclub.org.uk/api/next/ballots/{ballot_id}.json`)
**Source of predictions**: `data/ward_level_projections.json` (LLM-derived ward predictions used in the v16 NEGATIVE finding)

## Headline

| Metric | Value |
|---|---|
| Per-ward winner accuracy | **21.0%** (25/119) |
| Share MAE per party-ward | **10.3pp** |
| Random baseline (5-6 viable parties + Independents) | 16-20% |

**v16 per-ward predictions are barely above random.**

## Per-council breakdown

| Council | Matched | Winner % | Share MAE |
|---|---|---|---|
| Birmingham | 62/69 | 22.6% | 9.33pp |
| Sheffield | 26/28 | 19.2% | 13.79pp |
| Manchester | 31/32 | 19.4% | 7.79pp |
| **Overall** | **119/129** | **21.0%** | **10.3pp** |

## Failure modes (sample misses)

**Birmingham — over-predicts Reform UK; misses Independents entirely**
- Acocks Green: pred Reform UK, actual Liberal Democrat (model missed by 14.4pp margin call)
- Alum Rock: pred Reform UK, actual Independent
- Aston: pred Reform UK, actual Independent

**Manchester — over-predicts Labour; misses Green breakthroughs**
- Ancoats & Beswick: pred Labour, actual Green
- Ardwick: pred Labour, actual Green
- Baguley: pred Labour, actual Reform UK

**Sheffield — over-predicts Liberal Democrat; misses Green/Reform**
- Beighton: pred Liberal Democrat, actual Reform UK
- Broomhill & Sharrow Vale: pred Liberal Democrat, actual Green
- Burngreave: pred Liberal Democrat, actual Green

## Why v15.1 still achieves 59.2% council-level

v15.1 does NOT use the ward predictions. It uses council-level fragmentation
patterns + regional priors + national swing. The 59.2% reflects the model
correctly identifying which councils trend toward NOC vs which hold their
incumbent — without ever attempting per-ward simulation.

The v16 NEGATIVE finding (`scripts/kpm3/v16_ward_attempt.py`) showed that
aggregating these bad ward predictions to council-level CANNOT exceed v15.1.
This direct test reveals WHY: the ward layer is itself essentially random.

## Path forward (task #54 next steps)

To build a genuine v17 ward-aware methodology, we need:

1. **Actual ward swings**: same-ward results from a comparable prior election
   (2022 / 2024 → 2026). Apply UNS at the ward level, not council level.
   Source: Democracy Club `previous_elections` field on each ballot, OR
   council-published historical results.

2. **Per-ward demographics**: ONS Census 2021 ward profiles
   (deprivation, ethnicity, age, tenure, qualifications) to estimate the
   non-uniform component of swing.

3. **Independent-detection priors**: high-incumbency-of-independents wards
   (e.g., Birmingham Alum Rock / Aston) need a flag. UNS predicts party
   shares without realising independents will sweep.

4. **Multi-member ward seat allocation**: most wards elect 2-3; the v16
   model only predicts the single winning party. v17 must allocate seats
   per-party, recognising that a council can return Lab+Green or LD+Reform
   from a single ward.

This is the multi-week sprint. Tonight's contribution is the
**measurement framework** — `score_ward_predictions.py` will let us
test any v17 prototype against the same 119-ward baseline and confirm
whether it beats the random-equivalent 21% floor.

## Reproducibility

```bash
# Re-fetch actuals (idempotent, ~3 min):
python3 -m scripts.ward_data.ingest_dc_ward_results --council birmingham,sheffield,manchester

# Score:
python3 -m scripts.ward_data.score_ward_predictions
```

Methodology hash for any v17 attempt: must include the same per-ward
winner-hit% + share-MAE on this same Birmingham+Sheffield+Manchester
sample to be comparable.
