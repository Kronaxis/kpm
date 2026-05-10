"""KPM-2 backtest harness against May 7 2026 actuals.

Loads:
  - KPM-1 predictions (from the rendered live-page JSON, which carries
    every field the pre-registered file did plus some renderer extras)
  - May 7 actual council winners (data/may7_actual_results.json)

Then scores:
  1. KPM-1 baseline (must reproduce the published 1/8 lean track + 27%
     combined accuracy for the harness to be trustworthy)
  2. KPM-2 with each cassette (conservative / balanced / aggressive)

Output: a tabular report comparing per-tier and combined accuracy.

Usage:
  python3 -m scripts.kpm2.backtest
  python3 -m scripts.kpm2.backtest --cassette balanced --verbose
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from .calibrate import fit_calibration
from .classify import CASSETTES, apply_fragmentation_override, reclassify_kpm1_record


REPO_ROOT = Path(__file__).resolve().parents[2]
KPM1_PREDICTIONS_PATH = REPO_ROOT / "website" / "kronaxis" / "data" / "election-results-2026.json"
ACTUAL_RESULTS_PATH = REPO_ROOT / "data" / "may7_actual_results.json"

KPM2_MILESTONE_TARGETS = {
    "pns_mae_max_pp": 2.5,             # Phase 2 target
    "lean_track_min_hits": 4,          # Phase 1 target (out of 8)
    "lean_track_total": 8,
    "cons_overprojection_max_pp": 2.0, # Phase 2 stretch goal
}


def load_kpm1_predictions() -> dict[str, dict]:
    """Return {council_name: prediction_record}.

    The live page JSON nests councils under `councils` as a list of dicts.
    Returns a name-keyed map for O(1) lookup against actuals.
    """
    with KPM1_PREDICTIONS_PATH.open() as f:
        data = json.load(f)
    councils = data.get("councils", [])
    return {c["name"]: c for c in councils if "name" in c}


def load_actuals() -> dict[str, str]:
    """Return {council_name: actual_winner}, only declared councils."""
    with ACTUAL_RESULTS_PATH.open() as f:
        data = json.load(f)
    return data.get("council_winners_actual", {})


def normalise_winner(name: str) -> str:
    """Canonicalise winner names so KPM-1 / actuals match string-wise."""
    n = (name or "").strip()
    aliases = {
        "NOC": "No overall control",
        "No Overall Control": "No overall control",
        "no overall control": "No overall control",
        "Lib Dem": "Liberal Democrat",
        "Liberal Democrats": "Liberal Democrat",
        "LibDem": "Liberal Democrat",
        "Reform": "Reform UK",
        "Conservatives": "Conservative",
        "Tories": "Conservative",
    }
    return aliases.get(n, n)


def score(
    kpm1: dict[str, dict],
    actuals: dict[str, str],
    cassette: str | None,
    apply_fragmentation: bool = False,
) -> dict:
    """Score either KPM-1 baseline (cassette=None) or KPM-2 with a cassette.

    apply_fragmentation: if True, apply the KPM-2.2 fragmentation override
    on top of whichever classifier ran. Validates the new rule.
    """
    by_tier: dict[str, dict[str, int]] = defaultdict(lambda: {"hits": 0, "total": 0})
    misses: list[dict] = []
    hits: list[dict] = []

    for council, actual_raw in actuals.items():
        if council not in kpm1:
            continue
        record = kpm1[council]
        actual = normalise_winner(actual_raw)

        if cassette is None:
            predicted = normalise_winner(record.get("predicted_winner", ""))
            confidence = record.get("confidence", "Toss-up")
            margin = record.get("margin_pp", 0.0)
            if apply_fragmentation:
                from .classify import Classification
                base = Classification(predicted, confidence, margin, False, "kpm1")
                overridden = apply_fragmentation_override(
                    record.get("vote_shares", {}), base,
                    region=record.get("region", ""),
                    council_type=record.get("council_type", ""),
                    incumbent=record.get("incumbent", ""),
                    council_name=council,
                )
                predicted = overridden.predicted_winner
                confidence = overridden.confidence
                margin = overridden.margin_pp
        else:
            cls = reclassify_kpm1_record(record, cassette=cassette)
            if apply_fragmentation:
                cls = apply_fragmentation_override(
                    record.get("vote_shares", {}), cls,
                    region=record.get("region", ""),
                    council_type=record.get("council_type", ""),
                    incumbent=record.get("incumbent", ""),
                    council_name=council,
                )
            predicted = cls.predicted_winner
            confidence = cls.confidence
            margin = cls.margin_pp

        hit = predicted == actual
        by_tier[confidence]["total"] += 1
        if hit:
            by_tier[confidence]["hits"] += 1
            hits.append({"council": council, "predicted": predicted, "actual": actual, "tier": confidence})
        else:
            misses.append({
                "council": council,
                "predicted": predicted,
                "actual": actual,
                "tier": confidence,
                "margin_pp": round(margin, 1),
            })

    total_hits = sum(t["hits"] for t in by_tier.values())
    total_n = sum(t["total"] for t in by_tier.values())

    return {
        "cassette": cassette or "kpm1_baseline",
        "by_tier": dict(by_tier),
        "combined": {
            "hits": total_hits,
            "total": total_n,
            "pct": round(100.0 * total_hits / total_n, 1) if total_n else 0.0,
        },
        "hits": hits,
        "misses": misses,
    }


def load_kpm1_national_share() -> dict[str, float]:
    """KPM-1's published national vote share output (per party, %)."""
    with KPM1_PREDICTIONS_PATH.open() as f:
        data = json.load(f)
    return data.get("national", {}).get("vote_share", {})


def load_pns() -> dict[str, float]:
    """BBC Projected National Share — KPM-2 calibration target."""
    with ACTUAL_RESULTS_PATH.open() as f:
        data = json.load(f)
    return data.get("national_vote_share", {})


def score_national_mae(
    kpm1_shares: dict[str, float],
    pns: dict[str, float],
    calibration: dict[str, float] | None = None,
) -> dict:
    """Score per-party MAE vs PNS, optionally applying KPM-2 calibration shifts.

    calibration: {party: shift_pp} — added to the KPM-1 raw share before
    measuring error against PNS. Pass None to score raw KPM-1.
    """
    parties = ["Reform UK", "Labour", "Conservative", "Liberal Democrat", "Green"]
    rows = []
    abs_errors = []
    for p in parties:
        if p not in pns or p not in kpm1_shares:
            continue
        raw = kpm1_shares[p]
        shift = (calibration or {}).get(p, 0.0)
        adjusted = raw + shift
        err = adjusted - pns[p]
        rows.append({
            "party": p,
            "kpm1_raw": round(raw, 2),
            "shift_applied": round(shift, 2),
            "kpm2_adjusted": round(adjusted, 2),
            "pns": round(pns[p], 2),
            "error_pp": round(err, 2),
        })
        abs_errors.append(abs(err))
    return {
        "rows": rows,
        "mae_pp": round(sum(abs_errors) / len(abs_errors), 2) if abs_errors else 0.0,
        "n_parties": len(rows),
    }


def format_national_report(scored: dict, label: str) -> str:
    lines = []
    lines.append(f"\n=== {label} ===")
    lines.append(f"  {'Party':18}  {'KPM-1':>7}  {'Shift':>7}  {'KPM-2':>7}  {'PNS':>6}  {'Error':>7}")
    lines.append(f"  {'-' * 18}  {'-' * 7}  {'-' * 7}  {'-' * 7}  {'-' * 6}  {'-' * 7}")
    for r in scored["rows"]:
        lines.append(
            f"  {r['party']:18}  {r['kpm1_raw']:>5.2f}pp  {r['shift_applied']:>+5.2f}pp  "
            f"{r['kpm2_adjusted']:>5.2f}pp  {r['pns']:>4.1f}pp  {r['error_pp']:>+5.2f}pp"
        )
    target = KPM2_MILESTONE_TARGETS["pns_mae_max_pp"]
    status = "PASS" if scored["mae_pp"] <= target else "FAIL"
    lines.append(f"  {'MAE':18}  {scored['mae_pp']:>5.2f}pp  (target ≤ {target}pp — {status})")
    return "\n".join(lines)


def format_report(result: dict, verbose: bool = False) -> str:
    lines = []
    lines.append(f"\n=== {result['cassette']} ===")
    for tier in ["Confident", "Lean", "Toss-up", "NOC"]:
        if tier not in result["by_tier"]:
            continue
        t = result["by_tier"][tier]
        pct = round(100.0 * t["hits"] / t["total"], 1) if t["total"] else 0.0
        lines.append(f"  {tier:10}  {t['hits']:>2}/{t['total']:<2}  ({pct:>5.1f}%)")
    c = result["combined"]
    lines.append(f"  {'COMBINED':10}  {c['hits']:>2}/{c['total']:<2}  ({c['pct']:>5.1f}%)")

    if verbose and result["misses"]:
        lines.append("\n  Misses:")
        for m in result["misses"]:
            lines.append(
                f"    {m['council']:30}  predicted={m['predicted']:25}  "
                f"actual={m['actual']:25}  tier={m['tier']}  margin={m['margin_pp']:.1f}pp"
            )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cassette", choices=list(CASSETTES.keys()), help="Run only one cassette")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print misses")
    parser.add_argument("--national-only", action="store_true",
                        help="Skip per-council scoring, only run PNS MAE")
    parser.add_argument("--correction-weights", default="0.5,0.85,1.0",
                        help="Comma-separated correction weights to sweep (default 0.5,0.85,1.0)")
    parser.add_argument("--as-of", default="2026-05-06",
                        help="Calibration as-of date (default 2026-05-06)")
    args = parser.parse_args()

    if not args.national_only:
        kpm1 = load_kpm1_predictions()
        actuals = load_actuals()
        print(f"Loaded {len(kpm1)} KPM-1 predictions, {len(actuals)} declared councils.")

        baseline = score(kpm1, actuals, cassette=None)
        print(format_report(baseline, verbose=args.verbose))

        # KPM-2.2 fragmentation rule applied to KPM-1's published predictions
        with_frag = score(kpm1, actuals, cassette=None, apply_fragmentation=True)
        with_frag["cassette"] = "kpm1_baseline + fragmentation"
        print(format_report(with_frag, verbose=args.verbose))

        cassettes = [args.cassette] if args.cassette else list(CASSETTES.keys())
        for cas in cassettes:
            result = score(kpm1, actuals, cassette=cas)
            print(format_report(result, verbose=args.verbose))
            # Each cassette also gets a +fragmentation variant
            result_frag = score(kpm1, actuals, cassette=cas, apply_fragmentation=True)
            result_frag["cassette"] = f"{cas} + fragmentation"
            print(format_report(result_frag, verbose=args.verbose))

    # National PNS MAE scoring (Phase 2)
    print("\n" + "=" * 76)
    print("KPM-2 NATIONAL VOTE SHARE — Phase 2 calibration vs BBC PNS")
    print("=" * 76)

    kpm1_nat = load_kpm1_national_share()
    pns = load_pns()

    raw = score_national_mae(kpm1_nat, pns, calibration=None)
    print(format_national_report(raw, "KPM-1 baseline (no calibration)"))

    weights = [float(w) for w in args.correction_weights.split(",")]
    as_of = date.fromisoformat(args.as_of)
    for w in weights:
        cal_report = fit_calibration(as_of=as_of, correction_weight=w)
        cal_dict = {p: c.shift_pp for p, c in cal_report.parties.items()}
        scored = score_national_mae(kpm1_nat, pns, calibration=cal_dict)
        print(format_national_report(scored, f"KPM-2 calibration (weight={w})"))


if __name__ == "__main__":
    main()
