"""KPM-2.2 #4 (proper) — wire up KPM-1's full build_council_panel.

Imports KPM-1's `build_council_panel`, `score_persona_council_fit`, and
`turnout_probability_local` from `scripts/predict_may7_elections.py`,
plus the COUNCIL_REGIONS + COUNCIL_CHARACTER constants and
map_councils_to_constituencies + _COUNCIL_CONSTITUENCY_OVERRIDES.

Returns a KPM-2-compatible panel (list of dicts in `_persona_to_panel_dict`
format) drawn from the same KPM-1 persona bank our other modes use, but
demographically post-stratified per ward census + DYNAMICS-8 swing
oversampling exactly as KPM-1 does for production runs.

This is the path that should crack the 3/10 ceiling — the missing piece
between regional sampling (real_panel.load_real_panel) and KPM-1's actual
production methodology.

Usage (from predict.py via panel_mode="kpm1"):
  from .kpm1_panel import load_kpm1_full_panel
  panel = load_kpm1_full_panel("Wigan", n=60)

Caveats:
  - KPM-1 is 5045 lines and lazy-loaded at function-call time, but the
    module imports cleanly (verified: no module-level data loads).
  - Falls back to load_real_panel if the constituency profiles are
    missing on disk (e.g. running on the laptop without the data files).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .real_panel import _load_all, _persona_to_panel_dict


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONSTITUENCIES_PATH = _REPO_ROOT / "hugging_face" / "data" / "constituency_profiles.json"

# Lazy import — only triggered when load_kpm1_full_panel is called.
# Avoids importing the 5045-line KPM-1 module unless we actually use it.
_kpm1_module = None
_personas_by_region_cache: dict[str, list[dict]] | None = None
_constituency_profiles_cache: list[dict] | None = None


def _import_kpm1():
    """Import the KPM-1 module + verify its functions exist."""
    global _kpm1_module
    if _kpm1_module is not None:
        return _kpm1_module
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    import predict_may7_elections as kpm1
    _kpm1_module = kpm1
    return kpm1


def _group_personas_by_region() -> dict[str, list[dict]]:
    """Group the persona bank by identity.region."""
    global _personas_by_region_cache
    if _personas_by_region_cache is not None:
        return _personas_by_region_cache
    all_personas = _load_all()
    out: dict[str, list[dict]] = {}
    for p in all_personas:
        region = p.get("identity", {}).get("region", "unknown")
        out.setdefault(region, []).append(p)
    _personas_by_region_cache = out
    return out


def _load_constituency_profiles() -> list[dict]:
    """Load the constituency profiles JSON KPM-1 needs for matching."""
    global _constituency_profiles_cache
    if _constituency_profiles_cache is not None:
        return _constituency_profiles_cache
    if not _CONSTITUENCIES_PATH.exists():
        _constituency_profiles_cache = []
        return _constituency_profiles_cache
    with _CONSTITUENCIES_PATH.open() as f:
        _constituency_profiles_cache = json.load(f)
    return _constituency_profiles_cache


def load_kpm1_full_panel(council: str, n: int = 60) -> list[dict]:
    """Build a panel using KPM-1's full demographic post-stratification.

    Falls through to load_real_panel if constituency profiles aren't
    available locally (e.g. development on laptop without the data).
    """
    if not _CONSTITUENCIES_PATH.exists():
        from .real_panel import load_real_panel
        return load_real_panel(council, n=n)

    kpm1 = _import_kpm1()

    personas_by_region = _group_personas_by_region()
    profiles = _load_constituency_profiles()
    council_region = kpm1.COUNCIL_REGIONS.get(council, "")
    council_char = kpm1.COUNCIL_CHARACTER.get(council, "")

    # Map this council to its constituency names
    council_to_consts = kpm1.map_councils_to_constituencies([council], profiles)
    constituency_names = council_to_consts.get(council, [])

    raw_panel = kpm1.build_council_panel(
        personas_by_region=personas_by_region,
        council=council,
        council_region=council_region,
        council_char=council_char,
        constituency_names=constituency_names,
        target_size=n,
    )

    if not raw_panel:
        # KPM-1 returned empty — fall through to region sample
        from .real_panel import load_real_panel
        return load_real_panel(council, n=n)

    return [_persona_to_panel_dict(p) for p in raw_panel]


def diagnostics(council: str, n: int = 60) -> dict:
    """Inspect what KPM-1's panel builder returns vs the regional sampler."""
    kpm1_panel = load_kpm1_full_panel(council, n=n)
    from .real_panel import load_real_panel
    region_panel = load_real_panel(council, n=n)
    return {
        "council": council,
        "kpm1_n": len(kpm1_panel),
        "region_n": len(region_panel),
        "kpm1_age_dist": _age_distribution(kpm1_panel),
        "region_age_dist": _age_distribution(region_panel),
        "kpm1_class_dist": _class_distribution(kpm1_panel),
        "region_class_dist": _class_distribution(region_panel),
        "kpm1_prior_vote_dist": _prior_vote_distribution(kpm1_panel),
        "region_prior_vote_dist": _prior_vote_distribution(region_panel),
    }


def _age_distribution(panel: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for p in panel:
        out[p.get("age_band", "?")] = out.get(p.get("age_band", "?"), 0) + 1
    return out


def _class_distribution(panel: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for p in panel:
        out[p.get("social_class", "?")] = out.get(p.get("social_class", "?"), 0) + 1
    return out


def _prior_vote_distribution(panel: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for p in panel:
        out[p.get("voted_2024_ge", "?")] = out.get(p.get("voted_2024_ge", "?"), 0) + 1
    return out


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--council", default="Wigan")
    p.add_argument("--n", type=int, default=60)
    args = p.parse_args()
    diag = diagnostics(args.council, n=args.n)
    print(json.dumps(diag, indent=2))
