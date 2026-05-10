"""KPM-2 real persona-bank loader.

Loads from the production KPM-1 persona bank
(`hugging_face/data/constituency_personas_v2_enriched_2026.jsonl`,
~65,000 personas with full DYNAMICS-8 + voting history + key issues).

For a target council:
  1. Resolve the council's region (from turnout_estimates.json)
  2. Filter the persona pool to that region
  3. Random-sample N personas (deterministic by seed)

Honest scope: this is regional sampling, not the full DYNAMICS-8
demographic-weighted panel that KPM-1's `build_council_panel` does.
KPM-1's builder applies post-stratification across age/class/etc.;
this loader just picks regional voters at random. Sufficient for the
Phase 5 pipeline-validation milestone; full demographic weighting is
a KPM-3 enhancement.

Usage:
  from .real_panel import load_real_panel
  panel = load_real_panel("Wigan", n=30, seed=42)
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from .turnout import get_turnout


# Two candidate paths — DL580 is primary, laptop fallback for offline tests
_PERSONA_PATHS = [
    Path("/home/jason/projects/kronaxis/hugging_face/data/constituency_personas_v2_enriched_2026.jsonl"),
    Path.home() / "projects" / "kronaxis" / "hugging_face" / "data" / "constituency_personas_v2_enriched_2026.jsonl",
]

_CACHE: list[dict] | None = None


def _resolve_path() -> Path | None:
    for p in _PERSONA_PATHS:
        if p.exists():
            return p
    return None


def _load_all() -> list[dict]:
    """Load and cache the full persona bank. ~110MB → ~1-2GB RAM."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    path = _resolve_path()
    if not path:
        raise FileNotFoundError(
            "Persona bank not found. Expected at "
            f"{_PERSONA_PATHS[0]} (DL580) or {_PERSONA_PATHS[1]} (laptop)"
        )
    out: list[dict] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    _CACHE = out
    return out


def _persona_to_panel_dict(p: dict) -> dict:
    """Convert a raw KPM-1 persona record to the dict shape KPM-2 expects.

    KPM-2 panel dicts carry the fields the LLM prompt builder uses:
      id, age_band, social_class (derived), homeowner, voted_2024_ge,
      main_issue_2026, political_engagement_1to5, region, plus a
      turnout_probability derived from engagement + age.
    """
    ident = p.get("identity", {})
    fin = p.get("financial", {})
    pol = p.get("political", {})

    age = int(ident.get("age", 40))
    if age < 25:
        age_band = "18-24"
    elif age < 45:
        age_band = "25-44"
    elif age < 65:
        age_band = "45-64"
    else:
        age_band = "65+"

    income = float(ident.get("annual_income", fin.get("annual_income", 30000)))
    if income < 22000:
        klass = "DE - semi/unskilled, retired"
    elif income < 35000:
        klass = "C2 - skilled manual"
    elif income < 55000:
        klass = "C1 - clerical"
    else:
        klass = "AB - professional/managerial"

    homeowner = ident.get("housing_status", fin.get("housing_status", "")).lower() in (
        "owned outright", "mortgage", "owner-occupier", "owner", "owner_occupied"
    )

    # Pull most recent vote if there's a voting_history
    voted_2024 = "Did not vote"
    for v in pol.get("voting_history", []) or []:
        if v.get("year") == 2024 and v.get("election", "").lower().startswith("general"):
            voted_2024 = v.get("party_voted", "Did not vote")
            break

    issues = pol.get("key_issues", []) or []
    main_issue = issues[0] if issues else "Cost of living"

    engagement = int(pol.get("engagement_level", 3))
    # Turnout: baseline 30% + age uplift + engagement uplift
    age_uplift = {"18-24": -0.05, "25-44": 0.00, "45-64": 0.10, "65+": 0.18}.get(age_band, 0.0)
    eng_uplift = (engagement - 3) * 0.05
    turnout_prob = max(0.05, min(0.95, 0.30 + age_uplift + eng_uplift))

    return {
        "id": p.get("persona_id", "unknown"),
        "constituency": ident.get("constituency", p.get("constituency_name", "")),
        "region": ident.get("region", "unknown"),
        "age_band": age_band,
        "social_class": klass,
        "homeowner": homeowner,
        "voted_2024_ge": voted_2024,
        "main_issue_2026": main_issue,
        "political_engagement_1to5": engagement,
        "party_affiliation": pol.get("party_affiliation", "Unknown"),
        "turnout_probability": round(turnout_prob, 4),
        "ethnicity": ident.get("ethnicity", ""),
        "occupation": ident.get("occupation", ""),
        "_dynamics_8": p.get("dynamics_8", {}),
    }


def load_real_panel(council: str, n: int = 30, seed: int = 42) -> list[dict]:
    """Sample `n` real KPM-1 personas matching the council's region.

    Falls back to nation-wide pool if the council's region is unknown
    or has too few personas.
    """
    all_personas = _load_all()
    turnout = get_turnout(council)
    target_region = turnout.region if turnout else None

    pool = [p for p in all_personas if p.get("identity", {}).get("region") == target_region] if target_region else []

    if len(pool) < n:
        fallback_n = n - len(pool)
        rng = random.Random(seed + 1)
        rest = [p for p in all_personas if p not in pool]
        if rest:
            pool = pool + rng.sample(rest, min(fallback_n, len(rest)))

    if not pool:
        raise RuntimeError(f"Persona pool empty for council={council}")

    rng = random.Random(seed)
    sampled = rng.sample(pool, min(n, len(pool)))
    return [_persona_to_panel_dict(p) for p in sampled]


# KPM-2.2 #4 — demographic post-stratified sampling.
# UK population reference (ONS 2021 census + electoral demographic skews)
UK_AGE_TARGETS = {"18-24": 0.10, "25-44": 0.33, "45-64": 0.33, "65+": 0.24}
UK_CLASS_TARGETS = {
    "AB - professional/managerial": 0.25,
    "C1 - clerical": 0.27,
    "C2 - skilled manual": 0.21,
    "DE - semi/unskilled, retired": 0.27,
}


def load_stratified_panel(council: str, n: int = 30, seed: int = 42) -> list[dict]:
    """KPM-2.2 #4: demographic post-stratified panel.

    Pulls from regional pool but enforces age × class quotas matching
    UK census-realistic distribution. Reduces panel-level demographic
    skew that the random regional sampler can produce on small N.
    """
    all_personas = _load_all()
    turnout = get_turnout(council)
    target_region = turnout.region if turnout else None
    pool = [p for p in all_personas if p.get("identity", {}).get("region") == target_region] if target_region else []
    if len(pool) < n * 2:
        # Need enough headroom; fall back to nationwide
        pool = all_personas

    # Bucket personas by (age_band, class_band)
    rng = random.Random(seed)
    buckets: dict[tuple[str, str], list[dict]] = {}
    for p in pool:
        d = _persona_to_panel_dict(p)
        key = (d["age_band"], d["social_class"])
        buckets.setdefault(key, []).append(p)

    # Compute per-bucket target counts via age × class joint distribution
    selected: list[dict] = []
    for age_band, age_w in UK_AGE_TARGETS.items():
        for klass, class_w in UK_CLASS_TARGETS.items():
            target_count = max(1, round(n * age_w * class_w))
            bucket_pool = buckets.get((age_band, klass), [])
            if not bucket_pool:
                continue
            picked = rng.sample(bucket_pool, min(target_count, len(bucket_pool)))
            selected.extend(picked)

    # Fill any short with random from remaining region pool
    while len(selected) < n and pool:
        candidate = rng.choice(pool)
        if candidate not in selected:
            selected.append(candidate)
        if len(selected) >= len(pool):
            break

    return [_persona_to_panel_dict(p) for p in selected[:n]]


# KPM-2.2 #7 — constituency-aware filtering.
# Council → list of Westminster constituency keywords used to filter
# personas. Most council names are also recognisable constituency
# substrings; for ones that aren't (Hartlepool, Tamworth, etc. — single-
# constituency boroughs already), the filter falls through to council name.
COUNCIL_CONSTITUENCY_OVERRIDES: dict[str, list[str]] = {
    "Wigan":            ["Wigan", "Makerfield", "Leigh"],
    "Sunderland":       ["Sunderland", "Houghton"],
    "Sandwell":         ["West Bromwich", "Smethwick", "Tipton", "Wednesbury"],
    "Wolverhampton":    ["Wolverhampton"],
    "Bradford":         ["Bradford", "Shipley", "Keighley"],
    "Birmingham":       ["Birmingham", "Edgbaston", "Erdington", "Hodge Hill", "Hall Green",
                         "Ladywood", "Northfield", "Perry Barr", "Selly Oak", "Yardley"],
    "Westminster":      ["Cities of London and Westminster", "Westminster"],
    "Havering":         ["Romford", "Hornchurch", "Dagenham"],
    "North East Lincolnshire": ["Cleethorpes", "Great Grimsby"],
    "West Sussex":      ["Arundel", "Bognor", "Chichester", "Crawley", "East Worthing",
                         "Horsham", "Mid Sussex", "Worthing"],
}


def load_constituency_panel(council: str, n: int = 30, seed: int = 42) -> list[dict]:
    """KPM-2.2 #7: filter personas by constituency name match.

    Uses COUNCIL_CONSTITUENCY_OVERRIDES (best-effort; falls back to the
    council name as a substring search). When neither produces enough
    personas, falls through to load_real_panel (region-only).
    """
    all_personas = _load_all()
    keys = COUNCIL_CONSTITUENCY_OVERRIDES.get(council, [council])
    keys_lower = [k.lower() for k in keys]

    pool = []
    for p in all_personas:
        cname = (p.get("constituency_name") or p.get("identity", {}).get("constituency", "") or "").lower()
        if any(k in cname for k in keys_lower):
            pool.append(p)

    if len(pool) < n:
        # Constituency match too narrow; fall through to region
        return load_real_panel(council, n=n, seed=seed)

    rng = random.Random(seed)
    sampled = rng.sample(pool, min(n, len(pool)))
    return [_persona_to_panel_dict(p) for p in sampled]


def load_panel(council: str, n: int = 30, seed: int = 42, mode: str = "region") -> list[dict]:
    """Unified loader. mode: 'region' | 'stratified' | 'constituency' | 'kpm1'.

    'kpm1' invokes KPM-1's full build_council_panel via kpm1_panel.py for
    proper demographic post-stratification + DYNAMICS-8 swing oversampling.
    """
    if mode == "kpm1":
        from .kpm1_panel import load_kpm1_full_panel
        return load_kpm1_full_panel(council, n=n)
    if mode == "stratified":
        return load_stratified_panel(council, n=n, seed=seed)
    if mode == "constituency":
        return load_constituency_panel(council, n=n, seed=seed)
    return load_real_panel(council, n=n, seed=seed)


def stats() -> dict:
    """Diagnostic — pool sizes per region."""
    all_personas = _load_all()
    by_region: dict[str, int] = {}
    for p in all_personas:
        r = p.get("identity", {}).get("region", "unknown")
        by_region[r] = by_region.get(r, 0) + 1
    return {
        "total": len(all_personas),
        "by_region": dict(sorted(by_region.items(), key=lambda kv: -kv[1])),
    }
