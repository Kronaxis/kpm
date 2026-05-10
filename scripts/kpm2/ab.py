"""KPM-2.2 #N — auto A/B framework.

Quick comparison driver for cassette × LLM × prompt × bootstrap configs.
Each grid cell runs phase5_run on the test set and emits a scored line.

Used to iterate fast without hand-launching phase5 for each config.

Example grid:
  python3 -m scripts.kpm2.ab \\
      --cassettes balanced,aggressive,conservative \\
      --bootstraps pool,bayesian,hierarchical \\
      --concurrency 8 \\
      --panel-size 30

Each row of the resulting table = one config + its KPM-2 score.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class GridResult:
    cassette: str
    bootstrap: str
    panel_size: int
    use_real_personas: bool
    kpm1_hits: int
    kpm2_hits: int
    n: int
    elapsed_s: float
    output_path: str


def run_one(cassette: str, bootstrap: str, panel_size: int,
            use_real_personas: bool, concurrency: int,
            adaptive_panel: bool, test_set: str,
            llm_url: str, llm_model: str) -> GridResult:
    """Run one phase5 invocation and parse the output."""
    args = [
        "python3", "-u", "-m", "scripts.kpm2.phase5_run",
        "--cassette", cassette,
        "--bootstrap", bootstrap,
        "--panel-size", str(panel_size),
        "--concurrency", str(concurrency),
        "--test-set", test_set,
        "--llm-url", llm_url,
        "--llm-model", llm_model,
    ]
    if use_real_personas:
        args.append("--use-real-personas")
    if adaptive_panel:
        args.append("--adaptive-panel")

    out_path = REPO_ROOT / "data" / f"kpm2_ab_{cassette}_{bootstrap}_p{panel_size}_{datetime.now(timezone.utc).strftime('%H%M%S')}.json"
    args += ["--save", str(out_path)]

    t0 = time.time()
    proc = subprocess.run(args, capture_output=True, text=True, cwd=REPO_ROOT)
    elapsed = time.time() - t0

    # Parse the result JSON for the score
    if out_path.exists():
        result = json.loads(out_path.read_text())
        scoring = result.get("scoring", {})
        return GridResult(
            cassette=cassette,
            bootstrap=bootstrap,
            panel_size=panel_size,
            use_real_personas=use_real_personas,
            kpm1_hits=scoring.get("kpm1_hits", 0),
            kpm2_hits=scoring.get("kpm2_hits", 0),
            n=scoring.get("n", 0),
            elapsed_s=elapsed,
            output_path=str(out_path),
        )

    print(f"WARNING: run failed — stderr: {proc.stderr[-300:]}")
    return GridResult(
        cassette=cassette,
        bootstrap=bootstrap,
        panel_size=panel_size,
        use_real_personas=use_real_personas,
        kpm1_hits=0,
        kpm2_hits=0,
        n=0,
        elapsed_s=elapsed,
        output_path="ERROR",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cassettes", default="balanced,aggressive,conservative",
                        help="Comma-separated cassette names")
    parser.add_argument("--bootstraps", default="pool,bayesian",
                        help="Comma-separated bootstrap methods")
    parser.add_argument("--panel-sizes", default="30,60",
                        help="Comma-separated panel sizes")
    parser.add_argument("--use-real-personas", action="store_true", default=True)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--adaptive-panel", action="store_true")
    parser.add_argument("--test-set", default="test_10")
    parser.add_argument("--llm-url", default="http://localhost:18000/v1/chat/completions")
    parser.add_argument("--llm-model", default="imprint-9b")
    parser.add_argument("--save-summary", default=None,
                        help="Write the grid summary JSON to this path")
    args = parser.parse_args()

    cassettes: list[str] = args.cassettes.split(",")
    bootstraps: list[str] = args.bootstraps.split(",")
    panel_sizes: list[int] = [int(p) for p in args.panel_sizes.split(",")]

    grid: list[tuple[str, str, int]] = [
        (c, b, p) for c in cassettes for b in bootstraps for p in panel_sizes
    ]
    print(f"\n=== KPM-2.2 A/B grid: {len(grid)} configs ===")
    for cell_c, cell_b, cell_p in grid:
        print(f"  cassette={cell_c:14}  bootstrap={cell_b:14}  panel={cell_p}")

    results: list[GridResult] = []
    for i, (cassette, bootstrap, panel_size) in enumerate(grid, 1):
        print(f"\n[{i}/{len(grid)}] {cassette} | {bootstrap} | panel={panel_size}", flush=True)
        r = run_one(
            cassette=cassette,
            bootstrap=bootstrap,
            panel_size=panel_size,
            use_real_personas=args.use_real_personas,
            concurrency=args.concurrency,
            adaptive_panel=args.adaptive_panel,
            test_set=args.test_set,
            llm_url=args.llm_url,
            llm_model=args.llm_model,
        )
        results.append(r)
        pct = 100 * r.kpm2_hits / r.n if r.n else 0.0
        print(f"  -> KPM-2 {r.kpm2_hits}/{r.n} ({pct:.1f}%)  vs KPM-1 {r.kpm1_hits}/{r.n}  "
              f"({r.elapsed_s:.0f}s)  saved {r.output_path}")

    # Sorted summary
    results.sort(key=lambda r: -r.kpm2_hits)
    print("\n=== Grid summary (sorted by KPM-2 hits) ===")
    print(f"  {'Rank':>4}  {'Cassette':14}  {'Bootstrap':14}  {'Panel':>5}  {'KPM-1':>7}  {'KPM-2':>7}  {'Elapsed':>8}")
    for i, r in enumerate(results, 1):
        pct = 100 * r.kpm2_hits / r.n if r.n else 0.0
        print(f"  {i:>4}  {r.cassette:14}  {r.bootstrap:14}  {r.panel_size:>5}  "
              f"{r.kpm1_hits}/{r.n:<2}    {r.kpm2_hits}/{r.n:<2} ({pct:>4.1f}%)  {r.elapsed_s:>6.0f}s")

    if args.save_summary:
        Path(args.save_summary).write_text(json.dumps([
            {"cassette": r.cassette, "bootstrap": r.bootstrap, "panel_size": r.panel_size,
             "use_real_personas": r.use_real_personas,
             "kpm1_hits": r.kpm1_hits, "kpm2_hits": r.kpm2_hits, "n": r.n,
             "elapsed_s": r.elapsed_s, "output_path": r.output_path}
            for r in results
        ], indent=2))
        print(f"\nWrote summary to {args.save_summary}")


if __name__ == "__main__":
    main()
