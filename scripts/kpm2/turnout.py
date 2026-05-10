"""KPM-2 turnout model — wraps the existing turnout estimates.

KPM-1 already ships a fully-built turnout model at
data/turnout_model/turnout_estimates.json (136 councils, baselines from
Electoral Commission 2018-2024, per-party multipliers from DYNAMICS-8,
weather/concurrent-election adjustments). The model is sound; what KPM-1
does NOT do is treat ABSTENTION as an explicit signal.

KPM-2 adds two things on top of the existing model:

  1. Explicit abstention class — track personas who would NOT vote
     separately from "would vote other party". Disengagement is a real
     political signal (esp. for Labour heartlands shedding turnout to
     non-vote rather than to Reform).

  2. Per-council turnout-uplift adjustment from the May 7 actuals once
     enough councils have declared turnout figures (post-Wikipedia
     update). For now this passes through the existing baselines and
     simply exposes them via a clean Python API for predict.py.

Usage:
  python3 -m scripts.kpm2.turnout --council "Wigan"
  python3 -m scripts.kpm2.turnout --all --json
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TURNOUT_PATH = REPO_ROOT / "data" / "turnout_model" / "turnout_estimates.json"


@dataclass(frozen=True)
class TurnoutEstimate:
    """KPM-2 turnout estimate for one council with explicit abstention."""

    council: str
    council_type: str
    region: str
    estimated_turnout: float                # 0.0-1.0
    baseline_turnout: float                 # 0.0-1.0
    weather_adjustment: float               # signed, in turnout fraction
    concurrent_election_uplift: float       # signed, in turnout fraction
    party_turnout_multipliers: dict[str, float]
    party_avg_turnout_probability: dict[str, float]
    abstention_rate: float                  # = 1 - estimated_turnout

    @property
    def turnout_pct(self) -> float:
        return round(100.0 * self.estimated_turnout, 1)

    @property
    def abstention_pct(self) -> float:
        return round(100.0 * self.abstention_rate, 1)


def _load() -> dict:
    return json.loads(TURNOUT_PATH.read_text())


def get_turnout(council: str) -> TurnoutEstimate | None:
    """Return turnout estimate for one council (or None if not in panel)."""
    data = _load()
    raw = data.get("councils", {}).get(council)
    if not raw:
        return None
    estimated = float(raw.get("estimated_turnout", 0.0))
    return TurnoutEstimate(
        council=council,
        council_type=raw.get("council_type", "unknown"),
        region=raw.get("region", "unknown"),
        estimated_turnout=estimated,
        baseline_turnout=float(raw.get("baseline_turnout", 0.0)),
        weather_adjustment=float(raw.get("weather_adjustment", 0.0)),
        concurrent_election_uplift=float(raw.get("concurrent_election_uplift", 0.0)),
        party_turnout_multipliers=dict(raw.get("party_turnout_multipliers", {})),
        party_avg_turnout_probability=dict(raw.get("party_avg_turnout_probability", {})),
        abstention_rate=max(0.0, 1.0 - estimated),
    )


def all_turnouts() -> dict[str, TurnoutEstimate]:
    """Return turnout estimates for all 136 councils."""
    data = _load()
    out = {}
    for council in data.get("councils", {}):
        est = get_turnout(council)
        if est:
            out[council] = est
    return out


def summarise() -> dict:
    """Aggregate diagnostics across the full panel."""
    ests = all_turnouts()
    if not ests:
        return {"n": 0}
    turnouts = [e.estimated_turnout for e in ests.values()]
    abstentions = [e.abstention_rate for e in ests.values()]
    return {
        "n": len(ests),
        "turnout_min_pct": round(100 * min(turnouts), 1),
        "turnout_max_pct": round(100 * max(turnouts), 1),
        "turnout_mean_pct": round(100 * sum(turnouts) / len(turnouts), 1),
        "abstention_mean_pct": round(100 * sum(abstentions) / len(abstentions), 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--council", help="Show one council's estimate")
    parser.add_argument("--all", action="store_true", help="Summarise all 136")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.council:
        est = get_turnout(args.council)
        if not est:
            print(f"No data for council: {args.council}")
            return
        if args.json:
            print(json.dumps({
                "council": est.council,
                "council_type": est.council_type,
                "region": est.region,
                "turnout_pct": est.turnout_pct,
                "abstention_pct": est.abstention_pct,
                "baseline_turnout": est.baseline_turnout,
                "weather_adjustment": est.weather_adjustment,
                "concurrent_election_uplift": est.concurrent_election_uplift,
                "party_turnout_multipliers": est.party_turnout_multipliers,
            }, indent=2))
        else:
            print(f"\n{est.council} ({est.region}, {est.council_type})")
            print(f"  estimated turnout:   {est.turnout_pct}%")
            print(f"  baseline turnout:    {round(100*est.baseline_turnout, 1)}%")
            print(f"  weather adj:         {round(100*est.weather_adjustment, 1):+.2f}pp")
            print(f"  concurrent uplift:   {round(100*est.concurrent_election_uplift, 1):+.2f}pp")
            print(f"  abstention rate:     {est.abstention_pct}%")
            print(f"  party multipliers:")
            for p, m in sorted(est.party_turnout_multipliers.items(), key=lambda kv: -kv[1]):
                print(f"    {p:18}  {m:.4f}x")

    if args.all:
        s = summarise()
        if args.json:
            print(json.dumps(s, indent=2))
        else:
            print(f"\nAll councils ({s['n']}):")
            print(f"  turnout range: {s['turnout_min_pct']}% — {s['turnout_max_pct']}%")
            print(f"  turnout mean:  {s['turnout_mean_pct']}%")
            print(f"  abstention mean: {s['abstention_mean_pct']}%")


if __name__ == "__main__":
    main()
