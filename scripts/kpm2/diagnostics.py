"""KPM-2.2 #G — per-region accuracy diagnostics.

Reads any phase5_run_<ts>.json and slices the per-council results by
region. Surfaces where KPM-2 actually fails so we can iterate on the
broken parts rather than guessed parts.

Also computes per-tier accuracy (Confident / Lean / Toss-up / NOC), per
predicted-winner accuracy (does KPM-2 over-predict Labour? Reform?
NOC?), and confusion matrix vs actual outcomes.

Usage:
  python3 -m scripts.kpm2.diagnostics --run data/kpm2_phase5_run_<ts>.json
  python3 -m scripts.kpm2.diagnostics --run <path> --by region
  python3 -m scripts.kpm2.diagnostics --run <path> --by tier
  python3 -m scripts.kpm2.diagnostics --run <path> --confusion
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from .turnout import get_turnout


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_run(path: Path) -> dict:
    return json.loads(path.read_text())


def by_region(run: dict) -> dict[str, dict]:
    """Group results by region (using turnout_estimates.region per council)."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for r in run.get("results", []):
        if "kpm2_hit" not in r:
            continue
        if r.get("actual", "").startswith("n/a"):
            continue
        t = get_turnout(r["council"])
        region = t.region if t else "unknown"
        grouped[region].append(r)

    out = {}
    for region, items in grouped.items():
        n = len(items)
        kpm2_hits = sum(1 for r in items if r["kpm2_hit"])
        kpm1_hits = sum(1 for r in items if r["kpm1_hit"])
        out[region] = {
            "n": n,
            "kpm1_hits": kpm1_hits,
            "kpm2_hits": kpm2_hits,
            "kpm1_pct": round(100.0 * kpm1_hits / n, 1) if n else 0.0,
            "kpm2_pct": round(100.0 * kpm2_hits / n, 1) if n else 0.0,
            "delta": kpm2_hits - kpm1_hits,
            "councils": [r["council"] for r in items],
        }
    return out


def by_tier(run: dict) -> dict[str, dict]:
    """Group results by KPM-2 confidence tier."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for r in run.get("results", []):
        if "kpm2_hit" not in r:
            continue
        if r.get("actual", "").startswith("n/a"):
            continue
        tier = r.get("kpm2_confidence", "?")
        grouped[tier].append(r)

    out = {}
    for tier, items in grouped.items():
        n = len(items)
        hits = sum(1 for r in items if r["kpm2_hit"])
        out[tier] = {
            "n": n,
            "hits": hits,
            "pct": round(100.0 * hits / n, 1) if n else 0.0,
        }
    return out


def confusion_matrix(run: dict) -> dict:
    """KPM-2 predicted X / actual Y → counts. Identifies systematic biases."""
    matrix: dict[tuple[str, str], int] = Counter()
    pred_totals: Counter = Counter()
    actual_totals: Counter = Counter()

    for r in run.get("results", []):
        if "kpm2_hit" not in r:
            continue
        if r.get("actual", "").startswith("n/a"):
            continue
        pred = r["kpm2_predicted"]
        actual = r["actual"]
        matrix[(pred, actual)] += 1
        pred_totals[pred] += 1
        actual_totals[actual] += 1

    return {
        "matrix": {f"{p}->{a}": c for (p, a), c in matrix.items()},
        "pred_totals": dict(pred_totals),
        "actual_totals": dict(actual_totals),
    }


def per_party_bias(run: dict) -> dict[str, dict]:
    """For each party, how often did KPM-2 over- or under-predict it?"""
    pred_count: Counter = Counter()
    actual_count: Counter = Counter()
    for r in run.get("results", []):
        if "kpm2_hit" not in r:
            continue
        if r.get("actual", "").startswith("n/a"):
            continue
        pred_count[r["kpm2_predicted"]] += 1
        actual_count[r["actual"]] += 1

    parties = set(pred_count) | set(actual_count)
    out = {}
    for p in sorted(parties):
        pred = pred_count.get(p, 0)
        actual = actual_count.get(p, 0)
        out[p] = {
            "predicted_n": pred,
            "actual_n": actual,
            "bias": pred - actual,   # positive = over-predicted
            "bias_label": (
                "over-predicted" if pred > actual
                else "under-predicted" if pred < actual
                else "balanced"
            ),
        }
    return out


def fmt_region(rep: dict) -> str:
    lines = ["", "=== Per-region accuracy ==="]
    lines.append(f"  {'Region':22}  {'KPM-1':>10}  {'KPM-2':>10}  {'Delta':>5}  Councils")
    lines.append(f"  {'-'*22}  {'-'*10}  {'-'*10}  {'-'*5}  {'-'*30}")
    for region, r in sorted(rep.items(), key=lambda kv: -kv[1]["n"]):
        delta_marker = "↑" if r["delta"] > 0 else "↓" if r["delta"] < 0 else "→"
        lines.append(
            f"  {region:22}  {r['kpm1_hits']}/{r['n']:<2} ({r['kpm1_pct']:>4.1f}%)  "
            f"{r['kpm2_hits']}/{r['n']:<2} ({r['kpm2_pct']:>4.1f}%)  "
            f"{delta_marker}{abs(r['delta']):>3}  {', '.join(r['councils'][:3])}"
            + (f" +{len(r['councils'])-3}" if len(r['councils']) > 3 else "")
        )
    return "\n".join(lines)


def fmt_tier(rep: dict) -> str:
    lines = ["", "=== Per-tier accuracy (KPM-2) ==="]
    lines.append(f"  {'Tier':12}  {'Hits':>10}  {'Pct':>7}")
    lines.append(f"  {'-'*12}  {'-'*10}  {'-'*7}")
    for tier in ["Confident", "Lean", "Toss-up", "NOC"]:
        if tier not in rep:
            continue
        r = rep[tier]
        lines.append(f"  {tier:12}  {r['hits']}/{r['n']:<2}  {r['pct']:>5.1f}%")
    return "\n".join(lines)


def fmt_confusion(c: dict) -> str:
    lines = ["", "=== Confusion matrix (KPM-2 predicted -> actual) ==="]
    for pair, count in sorted(c["matrix"].items(), key=lambda kv: -kv[1]):
        pred, actual = pair.split("->")
        marker = "✓" if pred == actual else "✗"
        lines.append(f"  {marker}  {pred:25} -> {actual:25}  ({count})")
    return "\n".join(lines)


def fmt_bias(b: dict) -> str:
    lines = ["", "=== Per-party prediction bias ==="]
    lines.append(f"  {'Party':25}  {'Predicted':>10}  {'Actual':>10}  {'Bias':>10}")
    lines.append(f"  {'-'*25}  {'-'*10}  {'-'*10}  {'-'*10}")
    for party, r in sorted(b.items(), key=lambda kv: -abs(kv[1]["bias"])):
        sign = "+" if r["bias"] > 0 else ""
        lines.append(f"  {party:25}  {r['predicted_n']:>10}  {r['actual_n']:>10}  "
                     f"{sign}{r['bias']:>+5d} ({r['bias_label']})")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="phase5_run_<ts>.json path")
    parser.add_argument("--by", choices=["region", "tier", "all"], default="all")
    parser.add_argument("--confusion", action="store_true")
    parser.add_argument("--bias", action="store_true")
    args = parser.parse_args()

    run = load_run(Path(args.run))
    scoring = run.get("scoring", {})
    print(f"\nRun: {args.run}")
    print(f"  Cassette:    {run.get('cassette')}")
    print(f"  Panel size:  {run.get('panel_size')}")
    print(f"  LLM:         {run.get('llm_model')}")
    print(f"  Headline:    KPM-2 {scoring.get('kpm2_hits')}/{scoring.get('n')} "
          f"vs KPM-1 {scoring.get('kpm1_hits')}/{scoring.get('n')}")

    if args.by in ("region", "all"):
        print(fmt_region(by_region(run)))
    if args.by in ("tier", "all"):
        print(fmt_tier(by_tier(run)))
    if args.confusion or args.by == "all":
        print(fmt_confusion(confusion_matrix(run)))
    if args.bias or args.by == "all":
        print(fmt_bias(per_party_bias(run)))


if __name__ == "__main__":
    main()
