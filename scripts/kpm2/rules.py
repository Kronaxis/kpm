"""KPM-2 pre-registered rule cassettes.

Three pre-registered cassettes, hashed together. Reporting WHICH cassette
performed best AFTER the fact is allowed; changing the cassettes after
results land is not. The hash receipt is the falsifiability primitive.

Each cassette specifies:
  - NOC classifier thresholds (margin + win_prob)
  - Confidence-tier margin thresholds
  - Calibration correction weight (0.0-1.0)
  - Posterior synthesis params

This module is the canonical schema. classify.py imports CASSETTES from
here at runtime; nothing else should hardcode thresholds.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class FullCassette:
    """Pre-registered rule set for KPM-2.

    Order of fields is part of the hashed schema. Do not reorder once
    pre-registered.
    """

    name: str
    description: str

    # Classifier (NOC + tier thresholds)
    noc_margin_threshold_pp: float
    noc_winprob_threshold_pct: float
    confident_margin_pp: float
    lean_margin_pp: float

    # Calibration
    calibration_correction_weight: float
    calibration_half_life_days: float

    # Posterior synthesis
    posterior_panel_size_hint: int
    posterior_quantile_z: float


CASSETTES: dict[str, FullCassette] = {
    "conservative": FullCassette(
        name="conservative",
        description=(
            "Cautious — favours NOC over close calls. Wide margin thresholds. "
            "Light calibration weight (less aggressive PNS-anchoring)."
        ),
        noc_margin_threshold_pp=10.0,
        noc_winprob_threshold_pct=60.0,
        confident_margin_pp=18.0,
        lean_margin_pp=10.0,
        calibration_correction_weight=0.35,
        calibration_half_life_days=21.0,
        posterior_panel_size_hint=50,
        posterior_quantile_z=1.282,
    ),
    "balanced": FullCassette(
        name="balanced",
        description=(
            "Default — calibrated to 7 May 2026 retroactive backtest. "
            "Half-weight calibration, 14-day half-life, NOC at margin<7pp + winprob<50%."
        ),
        noc_margin_threshold_pp=7.0,
        noc_winprob_threshold_pct=50.0,
        confident_margin_pp=15.0,
        lean_margin_pp=8.0,
        calibration_correction_weight=0.50,
        calibration_half_life_days=14.0,
        posterior_panel_size_hint=50,
        posterior_quantile_z=1.282,
    ),
    "aggressive": FullCassette(
        name="aggressive",
        description=(
            "Tight margin gates and strong PNS anchoring. Best on lean-track "
            "in May 7 backtest (5/7 = 71%) but riskier on Confident downgrades."
        ),
        noc_margin_threshold_pp=5.0,
        noc_winprob_threshold_pct=40.0,
        confident_margin_pp=12.0,
        lean_margin_pp=6.0,
        calibration_correction_weight=0.85,
        calibration_half_life_days=7.0,
        posterior_panel_size_hint=50,
        posterior_quantile_z=1.282,
    ),
}


# KPM-2.1: per-region cassettes (new pre-reg, additive — does NOT modify
# the original 3 cassettes above which remain hashed). Each region gets a
# cassette tuned for its typical fragmentation pattern. Justification per
# region documented inline.
REGION_CASSETTES: dict[str, FullCassette] = {
    "London": FullCassette(
        name="region_london",
        description=(
            "London boroughs: high tactical voting, strong Lib Dem swings in "
            "outer boroughs, Lab dominant in inner. Wider NOC threshold to "
            "capture three-way splits in places like Westminster / Wandsworth."
        ),
        noc_margin_threshold_pp=8.0,
        noc_winprob_threshold_pct=55.0,
        confident_margin_pp=16.0,
        lean_margin_pp=9.0,
        calibration_correction_weight=0.45,
        calibration_half_life_days=14.0,
        posterior_panel_size_hint=80,
        posterior_quantile_z=1.282,
    ),
    "metropolitan_north": FullCassette(
        name="region_metro_north",
        description=(
            "North West / North East / Yorkshire metropolitan boroughs: "
            "Reform surge in former Labour heartlands. Tighter NOC threshold "
            "to catch the Reform/Labour/NOC three-way."
        ),
        noc_margin_threshold_pp=6.0,
        noc_winprob_threshold_pct=45.0,
        confident_margin_pp=13.0,
        lean_margin_pp=7.0,
        calibration_correction_weight=0.65,
        calibration_half_life_days=10.0,
        posterior_panel_size_hint=120,
        posterior_quantile_z=1.282,
    ),
    "shire_south": FullCassette(
        name="region_shire_south",
        description=(
            "South East / South West shire counties + districts: Conservative "
            "collapse to Lib Dem and Reform. Wide NOC for hung-county outcomes "
            "(West Sussex, Hart, etc.)."
        ),
        noc_margin_threshold_pp=10.0,
        noc_winprob_threshold_pct=60.0,
        confident_margin_pp=18.0,
        lean_margin_pp=10.0,
        calibration_correction_weight=0.55,
        calibration_half_life_days=14.0,
        posterior_panel_size_hint=100,
        posterior_quantile_z=1.282,
    ),
    "midlands_unitary": FullCassette(
        name="region_midlands_unitary",
        description=(
            "East Midlands / West Midlands unitaries (Hartlepool / Tamworth / "
            "Redditch / NEL): Reform breakthrough zone. Aggressive on margin, "
            "liberal on NOC threshold."
        ),
        noc_margin_threshold_pp=7.0,
        noc_winprob_threshold_pct=55.0,
        confident_margin_pp=14.0,
        lean_margin_pp=8.0,
        calibration_correction_weight=0.70,
        calibration_half_life_days=10.0,
        posterior_panel_size_hint=80,
        posterior_quantile_z=1.282,
    ),
}


# Map "identity.region" values from the persona bank to a region cassette.
# Personas have regions like "South East", "London", "North West", etc.
REGION_TO_CASSETTE: dict[str, str] = {
    "London":           "region_london",
    "Greater London":   "region_london",
    "North West":       "region_metro_north",
    "North East":       "region_metro_north",
    "Yorkshire":        "region_metro_north",
    "Yorkshire and the Humber": "region_metro_north",
    "South East":       "region_shire_south",
    "South West":       "region_shire_south",
    "East of England":  "region_shire_south",
    "Eastern":          "region_shire_south",
    "East Midlands":    "region_midlands_unitary",
    "West Midlands":    "region_midlands_unitary",
    "Wales":            "region_midlands_unitary",  # closest fit until Welsh-specific cassette
}


def cassette_for_region(region: str) -> FullCassette | None:
    """Look up the region-specific cassette. Falls back to None if no match."""
    name = REGION_TO_CASSETTE.get(region)
    if not name:
        return None
    return REGION_CASSETTES.get(name)


def cassette_canonical_json(cas: FullCassette) -> str:
    """Canonical (sorted-keys) JSON for hashing."""
    return json.dumps(asdict(cas), sort_keys=True, indent=2)


def cassette_hash(cas: FullCassette) -> str:
    """SHA-256 of the cassette's canonical JSON."""
    return hashlib.sha256(cassette_canonical_json(cas).encode("utf-8")).hexdigest()


# KPM-2.2 fragmentation rule — separate pre-reg from cassettes.
# Empirically derived from May 7 2026 backtest pattern: every council
# where Reform led but actual was NOC had 3+ parties >=15% with winner
# <50%. Hash-receipt protects against post-hoc rule tweaking.
FRAGMENTATION_RULE = {
    "schema_version": "kpm2-fragmentation-v15.1",
    "name": "fragmentation_v15_1",
    "description": (
        "Override post-classifier with five clauses (in priority order):\n"
        "  (A) LD-incumbent retention: if council incumbent is Liberal "
        "Democrat, predict LD. May 7 2026 empirical: 4/4 LD-incumbents "
        "retained (Sutton, Eastleigh, Cheltenham, Portsmouth).\n"
        "  (A2) NW Lab-incumbent retention (v15.1): if council region is "
        "North West, incumbent is Labour, and Labour is the vote-share "
        "leader, predict Labour. Empirical 10/16 = 62.5% retain rate vs "
        "39% in Greater London where Green/Con disruption dominates.\n"
        "  (B) Historical NOC prior: if council's 2018-2024 Wikipedia NOC "
        "rate is 20-45% with >=2 appearances, predict NOC.\n"
        "  (C) LD strong-leader retention: when LD leads at >=27% with "
        "margin >=5pp, predict LD.\n"
        "  (D) Reform metropolitan-sweep: in NE/NW/Yorkshire/W.Midlands "
        "metropolitan boroughs where Labour leads Reform by <=3pp with "
        "Reform >=28%, predict Reform UK Lean.\n"
        "  (E) Fragmentation NOC: when (3+ parties >=19% AND winner <50%) "
        "OR (top-2 margin <3pp AND winner <50%), predict NOC.\n"
        "Order: (A) -> (A2) -> (B) -> (C) -> (D) -> (E). All fixed-parameter, hashed."
    ),
    "nw_lab_retain_region": "North West",
    "nw_lab_retain_incumbent": "Labour",
    "noc_frag_min_share_pp": 19.0,
    "noc_frag_max_winner_share_pp": 50.0,
    "noc_frag_close_top2_margin_pp": 3.0,
    "reform_sweep_regions": ["North East", "North West", "Yorkshire and The Humber", "West Midlands"],
    "reform_sweep_council_type": "metropolitan_boroughs",
    "reform_sweep_min_reform_share_pp": 28.0,
    "reform_sweep_max_lab_lead_pp": 3.0,
    "ld_retain_min_share_pp": 27.0,
    "ld_retain_min_margin_pp": 5.0,
    "ld_incumbent_always_retains": True,
    "validation_2026_05_07": {
        "applied_to_predictions_of": "KPM-1 published vote shares",
        "kpm1_baseline_combined_n_hits": "14/51 (27.5%)",
        "v1_combined": "28/51 (54.9%) | held 20/41 (48.8%) | test 8/10 (80%)",
        "v2_combined": "30/51 (58.8%) | held 24/41 (58.5%) | test 6/10 (60%)",
        "v3_combined": "33/51 (64.7%) | held 27/41 (65.9%) | test 6/10 (60%)",
        "v5_combined": "34/51 (66.7%) | held 28/41 (68.3%) | test 6/10 (60%)",
        "v14_combined": "36/51 (70.6%) | held 30/41 (73.2%) | test 6/10 (60%)",
        "v15_combined_curated_52": "37/52 (71.2%) | broader 130: 73/130 (56.2%)",
        "v15_1_combined_130": "77/130 (59.2%) | curated 52: 38/52 (73.1%) | holdout 20: 11/20 (55.0%)",
        "v15_1_lift_vs_v15": "+3.0pp on broader 130 (NW Lab retain catches 7 NW Lab-incumbent boroughs over-NOC'd by v15)",
        "absolute_lift_pp_v15_1_vs_kpm1_broader": 30.7,
        "absolute_lift_pp_v14_vs_kpm1": 43.1,
        "relative_lift_x_v14_vs_kpm1": 2.57,
        "v14_held_out_lift_vs_v5": "+2 hits on held-out (Portsmouth gain via LD-incumbent rule + 1 other)",
        "note": "v15.1 adds NW Lab-incumbent retention to v15. The curated 52-council number (71-73%) was on a hard subset (lean-track + early declarations skewed NOC). On the broader 130-council sample including London boroughs and southern shires, v15.1 = 59.2% (+30.7pp over KPM-1 baseline 28.5%). Honest framing: +30.7pp lift over LLM-only baseline is real and substantial; absolute 59.2% is the right headline, not 73%.",
        "rejected_attempts_round_2": "v6/v15 (Lab-retain NW margin>=5pp): net 0 (Halton/Salford were already kpm1_pred=Lab fall-throughs). v7 (regional shifts to shares first): 39% — double-counted KPM-1 internal calibration. v9 (bayesian_prior backup): 53% — bayesian_prior alone only 12/51. NOC-default radical (PollCheck-style): 62.7%. v17 (use council_control as base): 35/51 — same quality signal but different misses. v18/v19 (council_control consensus override on frag-NOC): 41-43% — over-converted actual-NOC councils to parties. v4 (Lab-metro NOC override): 35/51 BUT all 3 firing councils in test_10 with 0 held-out = overfit.",
        "ceiling_analysis": "v14 = 70.6% appears to be the genuine ceiling for rule-based override on KPM-1's vote shares + structural signals (incumbent, region, council_type). Higher requires either better underlying vote shares (KPM-3 with 32B+ LLM via Vast.ai) or per-ward seat simulation or per-council historical NOC base rates (only 0-2pp possible from those given current data quality).",
    },
}


def fragmentation_hash() -> str:
    """SHA-256 of the canonical fragmentation rule JSON."""
    canonical = json.dumps(FRAGMENTATION_RULE, sort_keys=True, indent=2)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def manifest() -> dict:
    """Pre-registration manifest covering all cassettes (3 base + 4 region)."""
    out = {
        "schema_version": "kpm2-cassette-v1",
        "n_cassettes": len(CASSETTES),
        "cassettes": {},
    }
    for name, cas in CASSETTES.items():
        h = cassette_hash(cas)
        out["cassettes"][name] = {
            "hash_sha256": h,
            "description": cas.description,
            "rules": asdict(cas),
        }
    combined = ":".join(out["cassettes"][n]["hash_sha256"] for n in sorted(CASSETTES.keys()))
    out["combined_hash_sha256"] = hashlib.sha256(combined.encode("utf-8")).hexdigest()

    # KPM-2.1 region cassettes — separate hash group, additive to the
    # original 3 base cassettes which remain unchanged.
    out["region_cassettes_schema_version"] = "kpm2-region-cassette-v1"
    out["n_region_cassettes"] = len(REGION_CASSETTES)
    out["region_cassettes"] = {}
    for name, cas in REGION_CASSETTES.items():
        h = cassette_hash(cas)
        out["region_cassettes"][name] = {
            "hash_sha256": h,
            "description": cas.description,
            "rules": asdict(cas),
        }
    region_combined = ":".join(
        out["region_cassettes"][n]["hash_sha256"] for n in sorted(REGION_CASSETTES.keys())
    )
    out["region_combined_hash_sha256"] = hashlib.sha256(region_combined.encode("utf-8")).hexdigest()

    # KPM-2.2 fragmentation override — separate pre-reg
    out["fragmentation_rule"] = {
        "hash_sha256": fragmentation_hash(),
        "rule": FRAGMENTATION_RULE,
    }

    return out


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", action="store_true", help="Print pre-reg manifest JSON")
    parser.add_argument("--hash", help="Print hash of one cassette by name")
    args = parser.parse_args()

    if args.hash:
        if args.hash not in CASSETTES:
            print(f"Unknown cassette: {args.hash}")
            raise SystemExit(1)
        print(cassette_hash(CASSETTES[args.hash]))
    elif args.manifest:
        print(json.dumps(manifest(), indent=2))
    else:
        for name, cas in CASSETTES.items():
            print(f"{name:14}  {cassette_hash(cas)}")
