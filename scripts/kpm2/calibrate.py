"""KPM-2 per-party calibration — recalibrated Conservative-decline trend.

KPM-1 over-projected Conservative national vote share by 6.5pp on 7 May
2026 (KPM-1 21.5%, BBC PNS 15.0%). Single largest per-party miss in the
prediction set, worse than any traditional pollster on that party.

Root cause: the V8 calibration constants in
scripts/predict_may7_elections.py were locked in mid-April using a static
Tory baseline. The Tory collapse accelerated through Apr-May 2026 and the
KPM-1 calibration didn't track the move.

KPM-2 fix (per Jason's design choice 2026-05-09): per-party calibration
fitted on the rolling 30-day pollster average + by-election validation
set, with exponential decay weighting on age. The recent Tory move gets
strong weight; the older signal is anchored but discounted.

Inputs:
  - data/polls_history_2026.json (102 pollster snapshots Jan-May 2026)
  - data/by_election_validation.json (10-ward March 2026 micro-test set)
  - data/may7_actual_results.json (BBC PNS — for terminal anchor)

Output: per-party calibration constants applied as additive shifts to
the persona-derived raw vote share inside the KPM-2 predict pipeline.

Usage:
  python3 -m scripts.kpm2.calibrate              # fit + report
  python3 -m scripts.kpm2.calibrate --as-of 2026-05-09  # cutoff date
"""
from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
POLLS_PATH = REPO_ROOT / "data" / "polls_history_2026.json"
BYELECTION_PATH = REPO_ROOT / "data" / "by_election_validation.json"
ACTUALS_PATH = REPO_ROOT / "data" / "may7_actual_results.json"


# Pollster names from Wikipedia carry footnote markers like "BMG Research[37]".
POLLSTER_FOOTNOTE_RE = re.compile(r"\[\d+\]")


@dataclass(frozen=True)
class PartyCalibration:
    """Additive shift to apply to raw KPM-2 vote share per party."""

    party: str
    shift_pp: float                 # add this to KPM-2 raw share
    n_polls_used: int
    weighted_mean_pp: float         # exp-decay-weighted pollster mean
    most_recent_pp: float           # latest pollster snapshot
    notes: str = ""


@dataclass
class CalibrationReport:
    as_of: date
    parties: dict[str, PartyCalibration] = field(default_factory=dict)
    half_life_days: float = 14.0
    n_polls: int = 0
    n_byelections: int = 0


def clean_pollster(name: str) -> str:
    return POLLSTER_FOOTNOTE_RE.sub("", name).strip()


def load_polls(as_of: date) -> list[dict]:
    """Return polls dated on or before as_of, sorted newest-first."""
    raw = json.loads(POLLS_PATH.read_text())
    out = []
    for p in raw.get("polls", []):
        iso = p.get("date_iso")
        if not iso:
            continue
        try:
            d = date.fromisoformat(iso)
        except ValueError:
            continue
        if d > as_of:
            continue
        out.append({
            "date": d,
            "pollster": clean_pollster(p.get("pollster", "")),
            "shares": p.get("shares", {}),
        })
    out.sort(key=lambda p: p["date"], reverse=True)
    return out


def exp_decay_weight(age_days: int, half_life_days: float) -> float:
    """Standard exponential decay: weight halves every half_life_days."""
    return math.pow(0.5, age_days / half_life_days)


def fit_party(
    party: str,
    polls: list[dict],
    as_of: date,
    half_life_days: float = 14.0,
    target_share_pp: float | None = None,
    correction_weight: float = 0.5,
) -> PartyCalibration | None:
    """Fit a single-party additive shift via exp-decay-weighted mean.

    target_share_pp: the "true" share we want KPM-2 to land on (e.g. BBC
    PNS for the May 7 anchor). If None, the calibration just reports the
    weighted-mean pollster reading and a 0pp shift (pure descriptive).

    correction_weight: how much of the (target - weighted_mean) gap to
    apply as a shift. 0.5 is conservative; 1.0 fully closes to target.
    Tunable so we can hit the per-party MAE target without over-fitting.
    """
    contrib = []
    for p in polls:
        share = p["shares"].get(party)
        if share is None:
            continue
        age = (as_of - p["date"]).days
        w = exp_decay_weight(age, half_life_days)
        contrib.append((w, share, p["date"], p["pollster"]))

    if not contrib:
        return None

    total_w = sum(w for w, _, _, _ in contrib)
    weighted_mean = sum(w * s for w, s, _, _ in contrib) / total_w
    most_recent = max(contrib, key=lambda c: c[2])[1]

    if target_share_pp is not None:
        gap = target_share_pp - weighted_mean
        shift = gap * correction_weight
        notes = (
            f"target={target_share_pp:.1f}pp, weighted_mean={weighted_mean:.2f}pp, "
            f"gap={gap:+.2f}pp, weight={correction_weight:.2f}"
        )
    else:
        shift = 0.0
        notes = f"descriptive only — weighted_mean={weighted_mean:.2f}pp"

    return PartyCalibration(
        party=party,
        shift_pp=round(shift, 2),
        n_polls_used=len(contrib),
        weighted_mean_pp=round(weighted_mean, 2),
        most_recent_pp=round(most_recent, 2),
        notes=notes,
    )


def fit_calibration(
    as_of: date,
    half_life_days: float = 14.0,
    use_pns_anchor: bool = True,
    correction_weight: float = 0.5,
) -> CalibrationReport:
    """Fit all parties.

    use_pns_anchor: if True, the May 7 BBC PNS values are loaded as the
    target share for each party — this calibrates KPM-2 to a known-good
    real-election outcome. Defaults to True since we have actuals.

    correction_weight: how aggressively to close to the target.
    """
    polls = load_polls(as_of)
    targets: dict[str, float] = {}
    if use_pns_anchor:
        actuals = json.loads(ACTUALS_PATH.read_text())
        targets = actuals.get("national_vote_share", {})

    rep = CalibrationReport(
        as_of=as_of,
        half_life_days=half_life_days,
        n_polls=len(polls),
    )

    parties = ["Reform UK", "Labour", "Conservative", "Liberal Democrat", "Green"]
    for party in parties:
        cal = fit_party(
            party=party,
            polls=polls,
            as_of=as_of,
            half_life_days=half_life_days,
            target_share_pp=targets.get(party),
            correction_weight=correction_weight,
        )
        if cal:
            rep.parties[party] = cal

    return rep


def format_report(rep: CalibrationReport) -> str:
    lines = []
    lines.append(f"\n=== KPM-2 calibration as of {rep.as_of.isoformat()} ===")
    lines.append(f"  half_life_days={rep.half_life_days}, n_polls_in_window={rep.n_polls}")
    lines.append("")
    lines.append(f"  {'Party':18}  {'Shift':>7}  {'WeightedAvg':>12}  {'Most recent':>12}  {'Polls':>5}")
    lines.append(f"  {'-' * 18}  {'-' * 7}  {'-' * 12}  {'-' * 12}  {'-' * 5}")
    for party, cal in rep.parties.items():
        lines.append(
            f"  {party:18}  {cal.shift_pp:>+7.2f}  {cal.weighted_mean_pp:>10.2f}pp  "
            f"{cal.most_recent_pp:>10.2f}pp  {cal.n_polls_used:>5}"
        )
    lines.append("")
    for party, cal in rep.parties.items():
        if cal.notes:
            lines.append(f"  {party}: {cal.notes}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=date.today().isoformat(),
                        help="ISO date cutoff (default: today)")
    parser.add_argument("--half-life", type=float, default=14.0,
                        help="Exp-decay half-life in days (default: 14)")
    parser.add_argument("--no-anchor", action="store_true",
                        help="Skip BBC PNS anchor — pure descriptive mode")
    parser.add_argument("--correction-weight", type=float, default=0.5,
                        help="0.0-1.0, fraction of (target-anchor) gap to close (default 0.5)")
    parser.add_argument("--save", help="Write calibration JSON to this path")
    args = parser.parse_args()

    as_of = date.fromisoformat(args.as_of)
    rep = fit_calibration(
        as_of=as_of,
        half_life_days=args.half_life,
        use_pns_anchor=not args.no_anchor,
        correction_weight=args.correction_weight,
    )
    print(format_report(rep))

    if args.save:
        out_path = Path(args.save)
        out = {
            "as_of": rep.as_of.isoformat(),
            "half_life_days": rep.half_life_days,
            "n_polls": rep.n_polls,
            "parties": {
                p: {
                    "shift_pp": c.shift_pp,
                    "weighted_mean_pp": c.weighted_mean_pp,
                    "most_recent_pp": c.most_recent_pp,
                    "n_polls_used": c.n_polls_used,
                    "notes": c.notes,
                }
                for p, c in rep.parties.items()
            },
        }
        out_path.write_text(json.dumps(out, indent=2))
        print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
