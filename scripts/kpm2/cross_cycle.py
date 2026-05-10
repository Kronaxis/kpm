"""KPM-2.2 #M — cross-cycle backtest scaffold.

Run KPM-2 on multiple historical electoral cycles and report unified
accuracy + Brier score. Currently scaffolded for May 7 2026 only;
extending to 2024 GE / 2024 locals / 2025 by-elections requires
fetching ground-truth result data we don't yet have on disk.

When extended, this module will:
  1. For each cycle, load the pre-published predictions + actual results
  2. Run the same KPM-2 cassette ablation
  3. Aggregate per-cycle and overall accuracy + Brier
  4. Output a single comparison table that can ship as a credibility
     primitive ("KPM-2 averages X% across N cycles")

For now it loads the May 7 backtest as a single cycle so the framework
is exercised end-to-end.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from .backtest import load_actuals, load_kpm1_predictions, score
from .classify import CASSETTES


REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class CycleResult:
    cycle: str
    n_councils: int
    kpm1_hits: int
    kpm2_hits: dict[str, int]    # cassette -> hits
    notes: str


def score_may7_2026() -> CycleResult:
    """Score KPM-1 + each KPM-2 cassette on May 7 2026 declared councils."""
    kpm1 = load_kpm1_predictions()
    actuals = load_actuals()
    baseline = score(kpm1, actuals, cassette=None)
    cassette_scores: dict[str, int] = {}
    for cas in CASSETTES:
        result = score(kpm1, actuals, cassette=cas)
        cassette_scores[cas] = result["combined"]["hits"]
    return CycleResult(
        cycle="may7_2026",
        n_councils=baseline["combined"]["total"],
        kpm1_hits=baseline["combined"]["hits"],
        kpm2_hits=cassette_scores,
        notes="51 declared councils; cassette ablation on KPM-1 bootstrap",
    )


def score_2024_ge() -> CycleResult | None:
    """Placeholder. Returns None until 2024 GE results data is on disk."""
    if not (REPO_ROOT / "data" / "uk_ge_2024_results.json").exists():
        return None
    # When data lands, implement: load_ge_predictions + score against actual seats
    return None


def score_2024_locals() -> CycleResult | None:
    """Placeholder for 2024 May local elections."""
    if not (REPO_ROOT / "data" / "uk_locals_2024_results.json").exists():
        return None
    return None


def score_2025_byelections() -> CycleResult | None:
    """Placeholder for 2025 by-election year."""
    if not (REPO_ROOT / "data" / "uk_byelections_2025_results.json").exists():
        return None
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", help="Write summary JSON to this path")
    args = parser.parse_args()

    cycles: list[CycleResult] = [score_may7_2026()]
    for fn in (score_2024_ge, score_2024_locals, score_2025_byelections):
        r = fn()
        if r:
            cycles.append(r)

    print("\n=== KPM-2 cross-cycle backtest ===")
    print(f"  {'Cycle':16}  {'N':>4}  {'KPM-1':>10}  ", end="")
    for cas in CASSETTES:
        print(f"{cas[:10]:>11}  ", end="")
    print()

    for c in cycles:
        print(f"  {c.cycle:16}  {c.n_councils:>4}  {c.kpm1_hits}/{c.n_councils:<3} "
              f"({100*c.kpm1_hits/c.n_councils:>4.1f}%)  ", end="")
        for cas in CASSETTES:
            h = c.kpm2_hits.get(cas, 0)
            print(f"{h}/{c.n_councils:<3} ({100*h/c.n_councils:>4.1f}%)  ", end="")
        print()

    available_cycles = len(cycles)
    expected_cycles = 4
    if available_cycles < expected_cycles:
        print(f"\n  ({available_cycles}/{expected_cycles} cycles scored — "
              f"add 2024 GE / 2024 locals / 2025 by-election data to extend)")

    if args.save:
        Path(args.save).write_text(json.dumps([
            {"cycle": c.cycle, "n_councils": c.n_councils,
             "kpm1_hits": c.kpm1_hits, "kpm2_hits": c.kpm2_hits, "notes": c.notes}
            for c in cycles
        ], indent=2))


if __name__ == "__main__":
    main()
