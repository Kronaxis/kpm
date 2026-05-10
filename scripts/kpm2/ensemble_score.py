"""KPM-2.2 ensemble vote scorer.

Takes 3 phase5_run JSONs (one per cassette: conservative / balanced /
aggressive) and produces an ensemble verdict per council via majority
vote. Then scores the ensemble against actuals.

Usage:
  python3 -m scripts.kpm2.ensemble_score \\
      --conservative data/kpm2_ab_conservative_*.json \\
      --balanced data/kpm2_ab_balanced_*.json \\
      --aggressive data/kpm2_ab_aggressive_*.json
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TIEBREAK_ORDER = ["balanced", "aggressive", "conservative"]


def normalise(name: str) -> str:
    aliases = {
        "NOC": "No overall control",
        "Lib Dem": "Liberal Democrat",
        "Reform": "Reform UK",
    }
    return aliases.get((name or "").strip(), (name or "").strip())


def resolve_path(path_or_glob: str) -> Path:
    if "*" in path_or_glob:
        matches = sorted(glob.glob(path_or_glob))
        if not matches:
            raise FileNotFoundError(f"No files match {path_or_glob}")
        return Path(matches[-1])  # most recent
    return Path(path_or_glob)


def load_run(path: Path) -> dict[str, dict]:
    """{council_name: result_record} for one cassette run."""
    data = json.loads(path.read_text())
    out = {}
    for r in data.get("results", []):
        if "kpm2_predicted" not in r:
            continue
        out[r["council"]] = r
    return out


def ensemble_vote(per_cassette: dict[str, dict[str, dict]],
                  tiebreak_order: list[str] | None = None) -> dict:
    """For each council, vote across cassettes. tiebreak_order is the
    cassette ranking when votes split.
    """
    order = tiebreak_order or DEFAULT_TIEBREAK_ORDER
    cassettes = list(per_cassette.keys())
    all_councils = set()
    for runs in per_cassette.values():
        all_councils.update(runs.keys())

    ensemble: dict[str, dict] = {}
    for council in sorted(all_councils):
        votes_for: dict[str, list[str]] = {}  # winner -> list of cassette names
        actual = None
        kpm1_pred = None
        kpm1_hit = False
        for cas_name, runs in per_cassette.items():
            r = runs.get(council)
            if not r:
                continue
            pred = normalise(r["kpm2_predicted"])
            votes_for.setdefault(pred, []).append(cas_name)
            actual = normalise(r.get("actual", "")) if actual is None else actual
            if kpm1_pred is None:
                kpm1_pred = normalise(r.get("kpm1_predicted", ""))
                kpm1_hit = (kpm1_pred == actual)

        if not votes_for:
            continue

        # Majority + tiebreak
        sorted_votes = sorted(votes_for.items(), key=lambda kv: -len(kv[1]))
        top_count = len(sorted_votes[0][1])
        leaders = [w for w, lst in sorted_votes if len(lst) == top_count]
        tiebreak_used = len(leaders) > 1

        if tiebreak_used:
            chosen = None
            for cas_name in order:
                if cas_name not in cassettes:
                    continue
                cas_pred = normalise(per_cassette[cas_name].get(council, {}).get("kpm2_predicted", ""))
                if cas_pred in leaders:
                    chosen = cas_pred
                    break
            winner = chosen or leaders[0]
        else:
            winner = leaders[0]

        ensemble[council] = {
            "ensemble_predicted": winner,
            "ensemble_hit": (winner == actual) if actual else False,
            "kpm1_predicted": kpm1_pred,
            "kpm1_hit": kpm1_hit,
            "actual": actual,
            "cassette_votes": {cas: normalise(per_cassette[cas].get(council, {}).get("kpm2_predicted", "?")) for cas in cassettes},
            "n_voting_for_winner": top_count,
            "tiebreak_used": tiebreak_used,
        }
    return ensemble


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conservative", required=True)
    parser.add_argument("--balanced", required=True)
    parser.add_argument("--aggressive", required=True)
    parser.add_argument("--save", default=None)
    args = parser.parse_args()

    paths = {
        "conservative": resolve_path(args.conservative),
        "balanced": resolve_path(args.balanced),
        "aggressive": resolve_path(args.aggressive),
    }
    print(f"\nLoading runs:")
    for cas, p in paths.items():
        print(f"  {cas:14}  {p}")

    per_cassette = {cas: load_run(p) for cas, p in paths.items()}
    ensemble = ensemble_vote(per_cassette)

    # Filter out sanity-only entries
    scoreable = {c: e for c, e in ensemble.items() if e["actual"] and not e["actual"].startswith("n/a")}
    n = len(scoreable)
    kpm1_hits = sum(1 for e in scoreable.values() if e["kpm1_hit"])
    ensemble_hits = sum(1 for e in scoreable.values() if e["ensemble_hit"])

    # Per-cassette individual scores for comparison
    per_cas_hits: dict[str, int] = {}
    for cas, runs in per_cassette.items():
        per_cas_hits[cas] = sum(1 for r in runs.values()
                                 if "kpm2_hit" in r and r["kpm2_hit"]
                                 and not r.get("actual", "").startswith("n/a"))

    print(f"\n=== KPM-2.2 ensemble vote scoring ({n} councils) ===")
    print(f"  KPM-1 baseline:  {kpm1_hits}/{n}  ({100*kpm1_hits/n if n else 0:.1f}%)")
    for cas in ["conservative", "balanced", "aggressive"]:
        h = per_cas_hits.get(cas, 0)
        print(f"  KPM-2.2 {cas:14}  {h}/{n}  ({100*h/n if n else 0:.1f}%)")
    print(f"  KPM-2.2 ENSEMBLE     {ensemble_hits}/{n}  ({100*ensemble_hits/n if n else 0:.1f}%)")
    delta = ensemble_hits - kpm1_hits
    print(f"  Delta vs KPM-1:      {delta:+d} ({'IMPROVES' if delta>0 else 'NO LIFT' if delta==0 else 'REGRESSES'})")

    print(f"\n  Per-council ensemble verdict:")
    for council in sorted(scoreable):
        e = scoreable[council]
        marker = "✓" if e["ensemble_hit"] else "✗"
        tb = "  [tiebreak]" if e["tiebreak_used"] else ""
        print(f"    {marker}  {council:25}  ensemble={e['ensemble_predicted']:22}  actual={e['actual']:22}  ({e['n_voting_for_winner']}/3){tb}")

    if args.save:
        Path(args.save).write_text(json.dumps({
            "n": n,
            "kpm1_hits": kpm1_hits,
            "kpm22_per_cassette_hits": per_cas_hits,
            "kpm22_ensemble_hits": ensemble_hits,
            "delta_vs_kpm1": delta,
            "per_council": scoreable,
            "input_files": {cas: str(p) for cas, p in paths.items()},
        }, indent=2))
        print(f"\nWrote {args.save}")


if __name__ == "__main__":
    main()
