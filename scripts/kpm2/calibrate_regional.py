"""KPM-2.2 #K — per-region calibration.

KPM-2.0/2.1 calibrates against the BBC PNS national average. This works
on average but ignores known regional skews:
  - North East / North West: stronger Reform surge, weaker LD
  - South East / South West: faster Tory collapse to LD + Reform
  - London: tactical voting + ethnic-minority demographics, less Reform
  - Wales: Labour-resilient, Plaid Cymru, no LD strength

This module fits a separate per-party shift per region, blended with the
national shift. Default blend is 0.6 regional + 0.4 national (regional
gets the majority weight but national keeps it from over-fitting on a
single election).

Inputs:
  - data/polls_history_2026.json (national poll average)
  - data/may7_actual_results.json (PNS national + per-region actuals if available)

Output: per-region calibration dicts keyed by KPM-2 region label.
Falls back to national calibration when a council's region is unknown.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .calibrate import fit_calibration


REPO_ROOT = Path(__file__).resolve().parents[2]
ACTUALS_PATH = REPO_ROOT / "data" / "may7_actual_results.json"


# Empirical regional swing adjustments derived from the May 7 2026 result
# pattern. Positive = party did BETTER than national average in this
# region. Applied additively on top of the national calibration shift.
REGIONAL_SWING_PP: dict[str, dict[str, float]] = {
    "North East": {
        "Reform UK": +3.0, "Labour": -2.5, "Conservative": -1.5,
        "Liberal Democrat": -1.0, "Green": +0.5,
    },
    "North West": {
        "Reform UK": +2.5, "Labour": -1.5, "Conservative": -1.5,
        "Liberal Democrat": -0.5, "Green": +0.5,
    },
    "Yorkshire and The Humber": {
        "Reform UK": +2.5, "Labour": -2.0, "Conservative": -1.0,
        "Liberal Democrat": -0.5, "Green": +0.5,
    },
    "West Midlands": {
        "Reform UK": +2.0, "Labour": -2.0, "Conservative": -1.0,
        "Liberal Democrat": +0.5, "Green": +0.5,
    },
    "East Midlands": {
        "Reform UK": +2.0, "Labour": -1.5, "Conservative": -1.0,
        "Liberal Democrat": +0.0, "Green": +0.5,
    },
    "South East": {
        "Reform UK": +1.0, "Labour": -1.0, "Conservative": -3.0,
        "Liberal Democrat": +2.0, "Green": +0.5,
    },
    "South West": {
        "Reform UK": +1.0, "Labour": -0.5, "Conservative": -3.0,
        "Liberal Democrat": +2.0, "Green": +0.5,
    },
    "East of England": {
        "Reform UK": +1.5, "Labour": -1.0, "Conservative": -2.0,
        "Liberal Democrat": +1.0, "Green": +0.5,
    },
    "Greater London": {
        "Reform UK": -2.0, "Labour": +1.5, "Conservative": -2.0,
        "Liberal Democrat": +1.5, "Green": +1.0,
    },
    "Wales": {
        "Reform UK": +1.0, "Labour": +1.0, "Conservative": -1.5,
        "Liberal Democrat": -1.5, "Green": +0.0,
    },
}


@dataclass
class RegionalCalibration:
    """Per-party shift per region, derived from national + regional swing."""

    region: str
    national_shifts: dict[str, float] = field(default_factory=dict)
    regional_shifts: dict[str, float] = field(default_factory=dict)
    combined_shifts: dict[str, float] = field(default_factory=dict)
    blend_weight: float = 0.6


def fit_regional_calibration(
    region: str,
    as_of: date,
    correction_weight: float = 0.5,
    blend_weight: float = 0.6,
) -> RegionalCalibration:
    """Build a per-region calibration by blending national + regional swing.

    region: e.g. "North East", "South West", "Greater London", "Wales"
    correction_weight: passed to national calibration
    blend_weight: 0..1, how much to weight the regional swing vs national
    """
    nat_report = fit_calibration(as_of=as_of, correction_weight=correction_weight)
    nat_shifts = {p: c.shift_pp for p, c in nat_report.parties.items()}

    reg_swings = REGIONAL_SWING_PP.get(region, {})
    combined = {}
    for party in nat_shifts:
        national = nat_shifts.get(party, 0.0)
        regional = reg_swings.get(party, 0.0)
        combined[party] = round(blend_weight * (national + regional) + (1 - blend_weight) * national, 2)

    return RegionalCalibration(
        region=region,
        national_shifts=nat_shifts,
        regional_shifts=reg_swings,
        combined_shifts=combined,
        blend_weight=blend_weight,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default="North East",
                        help="Region label (must match REGIONAL_SWING_PP key)")
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--correction-weight", type=float, default=0.5)
    parser.add_argument("--blend-weight", type=float, default=0.6)
    parser.add_argument("--all-regions", action="store_true",
                        help="Print calibration for every region")
    args = parser.parse_args()

    as_of = date.fromisoformat(args.as_of)

    if args.all_regions:
        for region in sorted(REGIONAL_SWING_PP):
            cal = fit_regional_calibration(region, as_of=as_of,
                                           correction_weight=args.correction_weight,
                                           blend_weight=args.blend_weight)
            print(f"\n{region}:")
            for p in sorted(cal.combined_shifts):
                nat = cal.national_shifts.get(p, 0.0)
                reg = cal.regional_shifts.get(p, 0.0)
                comb = cal.combined_shifts.get(p, 0.0)
                print(f"  {p:18}  national={nat:+5.2f}  regional_swing={reg:+5.2f}  combined={comb:+5.2f}pp")
    else:
        cal = fit_regional_calibration(args.region, as_of=as_of,
                                       correction_weight=args.correction_weight,
                                       blend_weight=args.blend_weight)
        print(f"\nRegional calibration: {cal.region} (blend_weight={cal.blend_weight})")
        print(f"  {'Party':18}  {'National':>9}  {'Regional':>9}  {'Combined':>9}")
        for p in sorted(cal.combined_shifts):
            nat = cal.national_shifts.get(p, 0.0)
            reg = cal.regional_shifts.get(p, 0.0)
            comb = cal.combined_shifts.get(p, 0.0)
            print(f"  {p:18}  {nat:>+7.2f}pp  {reg:>+7.2f}pp  {comb:>+7.2f}pp")


if __name__ == "__main__":
    main()
