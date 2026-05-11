# `scripts/ward_data/` — runbook

**What this is**: end-to-end pipeline for real ward-level UK election data
ingestion + per-ward + council-level prediction.

**Production methodology**: KPM-v17.6 (`141c405a9c98…`) — council-level
93.3% on n=15 vs v15.1's 60.0% on the same sample (+33pp lift).

## Quick reference

| File | Purpose | Hash |
|---|---|---|
| `methodology_v17_ward_uns.py` | v17.0 baseline ward-UNS | `e38adc8efdd5…` |
| `methodology_v17_1_council_overlay.py` | + 60% NOC overlay | `6da92625051…` |
| `methodology_v17_2_reform_weighted.py` | + Reform-weighted UNS | `67d25b34142…` |
| `methodology_v17_3_reform_no_incumbency.py` | + suppress Reform-target incumbency | `467c29426306…` |
| `methodology_v17_4_green_too.py` | symmetric Green-target — REJECTED | `51a12fba4e89…` |
| `methodology_v17_5_council_reform.py` | + council-level Reform-emergence detection | `d5d5d3dd46ce…` |
| `methodology_v17_6_council_override.py` | + outcome override (PRODUCTION) | `141c405a9c98…` |

## Quick operational use

```bash
# Predict any council (v17.10 production) with full explanation:
python3 -m scripts.ward_data.explain_v17_10 wakefield
python3 -m scripts.ward_data.explain_v17_10 birmingham
```

Outputs council-level signals (Reform-emerging via prior or Brexit), per-ward
predictions with which signals fired (Muslim override, Reform-target, incumbency),
and the final ensemble decision.

## End-to-end re-run (idempotent, ~10 min on existing 15 councils)

```bash
# 1. Score current sample (no fetching):
python3 -m scripts.ward_data.score_v17_vs_baselines      # per-ward
python3 -m scripts.ward_data.score_v17_council_level     # council-level
python3 -m scripts.ward_data.per_party_recall_v17        # confusion matrix
python3 -m scripts.ward_data.calibration_v17             # confidence buckets
python3 -m scripts.ward_data.diagnostic_independent_signal  # Independent surge
python3 -m scripts.ward_data.score_v17_2                 # v17.2
python3 scripts/ward_data/methodology_v17_3_reform_no_incumbency.py  # v17.3
python3 scripts/ward_data/methodology_v17_5_council_reform.py        # v17.5
python3 scripts/ward_data/methodology_v17_6_council_override.py      # v17.6

# 2. Build comparison artifacts:
python3 -m scripts.ward_data.build_comparison_table

# 3. Refresh pending scorecard entries (60 entries: v17.0/.1/.3/.6 × 15):
python3 -m scripts.ward_data.seed_v17_pending_scorecard
```

## Add a new council to the sample

```bash
# 1. Fetch current 2026 results (~30s for ~20 wards):
python3 -m scripts.ward_data.ingest_dc_ward_results --council {slug}

# 2. Fetch most-recent prior election (~90s for ~20 wards × 3 dates):
python3 -m scripts.ward_data.ingest_dc_ward_history --council {slug}

# 3. Re-build comparison table with new council included:
python3 -m scripts.ward_data.build_comparison_table
```

## Full 130-council overnight ingest

```bash
# Inventory what's done vs pending:
python3 -m scripts.ward_data.ingest_all_councils --dry-run

# Real run (~5 hours, batched, resume-friendly):
nohup python3 -u -m scripts.ward_data.ingest_all_councils \
    --current --history --batch 5 \
    > logs/ingest_all_$(date +%F).log 2>&1 &
```

## Reading the comparison table

`data/ward_data/comparison_table.md` is the human-readable scorecard.
`data/ward_data/comparison_table.json` is the machine-readable equivalent.

Council rows show all methodologies × actual + ✓/✗ markers. The `(RE)` tag
on v17.6 means "Reform-emerging council" (mean prior Reform ≥5%).

## v17.6 mechanism (production)

For each council:
1. **Per-ward UNS** with year-scaled swings (v17.0)
2. **Reform-weighted UNS multiplier** (1.0× / 1.3× / 1.7× / 2.0× by prior
   Reform share, v17.2)
3. **Reform-target incumbency suppression** (in wards with prior Reform
   ≥10%, drop the +4pp prior-incumbent boost, v17.3)
4. **60% NOC overlay** (largest party needs ≥60% of predicted seats to be
   called as majority, v17.1)
5. **Council-level Reform-emergence detection** (council mean prior
   Reform ≥5% → flag, v17.5)
6. **Outcome override** (in Reform-emerging council, if v17.5 predicts
   any single-party majority → override to Reform UK, v17.6)

## Failure modes (published with hash, not hidden)

| Mode | Where seen | Detectable from priors? |
|---|---|---|
| Reform sweep, 0% prior Reform across all wards | Wolverhampton | NO |
| Birmingham Independent Gaza wards | 7/8 had 0% prior Independent | NO |
| Manchester Lab → Green wave in 0%-Green wards | Most v17.x Green misses | NO (needs Census 2021) |
| Reform sweep with high Lab prior in mixed council | Sandwell, Barnsley | YES via v17.6 council override |
| LD strongholds where LD already winning | Eastleigh | YES, trivial (always-incumbent works) |

## Honest caveats (kept in every doc)

1. **n=15 doesn't generalise.** v15.1's 60% on this sample is NOT v15.1's
   real track record (59.2% on n=130). v17.6's 93.3% needs cross-validation
   on the full 130-council set before any production claim.
2. **Sample is biased toward Reform-target councils** (deliberately picked).
   Random 15 might show smaller v17.6 lift.
3. **v17.6's outcome override is OPINIONATED.** Could over-fire on
   councils with rising Reform that ultimately stays sub-threshold.
4. **Reform recall ward-level still 8% (9/112).** Council-level wins
   come from the override, not improved per-ward prediction.
5. **Multi-member wards: v17 assigns all seats to single winner.** Real
   multi-member elections often split (e.g., 1 Lab + 1 Green).

## When to use which methodology

- **v15.1**: still production for the kronaxis_scorecard.json. Use until
  v17.6 cross-validates on full 130.
- **v17.6**: use for ad-hoc analysis where ward data is available + the
  council looks Reform-emerging. Do NOT use blind without inspecting the
  Reform-emerging flag.
- **v17.3**: use when Reform-emerging override feels too aggressive
  (council-level outcome override is the most opinionated piece of v17.6).
- **always-incumbent**: a 41.7% per-ward floor that almost ties UNS-projected.
  Useful sanity check.
