"""KPM-2 Phase 5 real-LLM validation runner.

Runs KPM-2 end-to-end with the real Imprint LLM (qwen-omni-7b on DL580)
against the 8 KPM-1 Lean-track councils + Caerphilly sanity.

KPM-1 went 1/8 = 12.5% on the lean track (only Havering hit). KPM-2
ablation (cassette only on KPM-1's bootstrap) hit 5/7 with the aggressive
cassette on this same set. This run validates the full LLM-driven pipeline.

HONEST CAVEAT: Synthetic panels (no DYNAMICS-8 personas on disk locally).
This validates pipeline integration, not full prediction accuracy. Real
production needs DYNAMICS-8 panels via KPM-1's build_council_panel.

Output: data/kpm2_phase5_run_<timestamp>.json with per-council
PredictionRun records + scoring summary.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .predict import predict_council, to_jsonable
from .llm import get_client


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_kpm1_lean_track() -> list[dict]:
    """The 8 KPM-1 Lean-track councils + their incumbents + actuals."""
    kpm1 = json.loads((REPO_ROOT / "website" / "kronaxis" / "data" / "election-results-2026.json").read_text())
    actuals = json.loads((REPO_ROOT / "data" / "may7_actual_results.json").read_text())["council_winners_actual"]
    out = []
    for c in kpm1["councils"]:
        if c.get("confidence") != "Lean":
            continue
        if c["name"] not in actuals:
            continue
        out.append({
            "name": c["name"],
            "incumbent": c.get("incumbent", "Labour"),
            "kpm1_predicted": c.get("predicted_winner", "?"),
            "actual": actuals[c["name"]],
        })
    return out


def load_test_set_10(extra_councils: list[str] | None = None) -> list[dict]:
    """The 8 lean-track councils + 2 extra (KPM-1 Toss-up misses with NOC actual).

    Pads to 10 councils to give a more diverse test surface for real-persona
    Phase 5 validation.
    """
    base = load_kpm1_lean_track()
    extras = extra_councils or ["Hartlepool", "Tamworth"]  # Both NOC actuals KPM-1 missed

    kpm1 = json.loads((REPO_ROOT / "website" / "kronaxis" / "data" / "election-results-2026.json").read_text())
    actuals = json.loads((REPO_ROOT / "data" / "may7_actual_results.json").read_text())["council_winners_actual"]
    council_records = {c["name"]: c for c in kpm1["councils"]}
    seen = {c["name"] for c in base}
    for name in extras:
        if name in seen or name not in council_records or name not in actuals:
            continue
        c = council_records[name]
        base.append({
            "name": name,
            "incumbent": c.get("incumbent", "Labour"),
            "kpm1_predicted": c.get("predicted_winner", "?"),
            "actual": actuals[name],
        })
    return base


def normalise(name: str) -> str:
    aliases = {
        "NOC": "No overall control",
        "No Overall Control": "No overall control",
        "Lib Dem": "Liberal Democrat",
        "Reform": "Reform UK",
        "Conservatives": "Conservative",
    }
    return aliases.get((name or "").strip(), (name or "").strip())


def run_council(council_meta: dict, cassette: str, panel_size: int, seed: int, client,
                use_real_personas: bool = False,
                bootstrap_method: str = "pool",
                adaptive_panel: bool = False,
                concurrency: int = 1,
                panel_mode: str = "region") -> dict:
    """Run KPM-2 on one council with the real LLM, return scored record."""
    ctx_override = {
        "council": council_meta["name"],
        "incumbent": council_meta["incumbent"],
        "election_date": "2026-05-07",
    }

    effective_panel_size = panel_size
    if adaptive_panel:
        from .turnout import get_turnout
        t = get_turnout(council_meta["name"])
        if t:
            effective_panel_size = {
                "metropolitan": 120, "london": 80, "unitary": 80,
                "county": 100, "district": 40,
            }.get(t.council_type, panel_size)

    t0 = time.time()
    run = predict_council(
        council=council_meta["name"],
        cassette=cassette,
        panel_size=effective_panel_size,
        llm_client=client,
        llm_client_name="imprint",
        seed=seed,
        council_ctx_override=ctx_override,
        use_real_personas=use_real_personas,
        bootstrap_method=bootstrap_method,
        concurrency=concurrency,
        panel_mode=panel_mode,
    )
    elapsed = time.time() - t0

    pred = normalise(run.posterior["classification"]["predicted_winner"])
    actual = normalise(council_meta["actual"])
    kpm1_pred = normalise(council_meta["kpm1_predicted"])

    return {
        "council": council_meta["name"],
        "incumbent": council_meta["incumbent"],
        "actual": actual,
        "kpm1_predicted": kpm1_pred,
        "kpm1_hit": kpm1_pred == actual,
        "kpm2_predicted": pred,
        "kpm2_confidence": run.posterior["classification"]["confidence"],
        "kpm2_margin_pp": run.posterior["classification"]["margin_pp"],
        "kpm2_noc_prob_pct": run.posterior["noc_prob_pct"],
        "kpm2_hit": pred == actual,
        "n_voted": run.n_voted,
        "n_abstained": run.n_abstained,
        "calibrated_shares": run.calibrated_vote_shares,
        "win_probability": run.win_probability,
        "elapsed_s": round(elapsed, 1),
        "full_run": to_jsonable(run),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cassette", default="aggressive",
                        help="Cassette to use (default: aggressive — best on lean track in ablation)")
    parser.add_argument("--panel-size", type=int, default=30,
                        help="Personas per council (default 30 — keeps runtime manageable)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--include-caerphilly", action="store_true", default=True)
    parser.add_argument("--llm-url", default="http://localhost:18000/v1/chat/completions",
                        help="vLLM endpoint (default imprint-9b at 18000)")
    parser.add_argument("--llm-model", default="imprint-9b",
                        help="vLLM served-model-name (default imprint-9b)")
    parser.add_argument("--save", default=None,
                        help="Output path (default: data/kpm2_phase5_run_<ts>.json)")
    parser.add_argument("--use-real-personas", action="store_true",
                        help="Use KPM-1 persona bank (constituency_personas_v2_enriched_2026.jsonl)")
    parser.add_argument("--bootstrap", choices=["pool", "bayesian", "hierarchical"], default="pool")
    parser.add_argument("--adaptive-panel", action="store_true")
    parser.add_argument("--concurrency", type=int, default=1,
                        help="Concurrent LLM calls per council (1=sequential, 8=matches vLLM)")
    parser.add_argument("--panel-mode", choices=["region", "stratified", "constituency", "kpm1"], default="region",
                        help="Sampling mode (kpm1 = full KPM-1 ward-census post-strat)")
    parser.add_argument("--test-set", choices=["lean_track_8", "test_10"], default="lean_track_8")
    args = parser.parse_args()

    client = get_client("imprint", url=args.llm_url, model=args.llm_model)

    if args.test_set == "test_10":
        lean_track = load_test_set_10()
        set_label = f"{len(lean_track)}-council test set (8 lean + 2 NOC actuals)"
    else:
        lean_track = load_kpm1_lean_track()
        set_label = f"{len(lean_track)} lean-track councils"

    print(f"\n=== KPM-2 Phase 5 real-LLM run ===")
    print(f"  LLM:          {args.llm_model} @ {args.llm_url}")
    print(f"  Cassette:     {args.cassette}")
    print(f"  Panel size:   {args.panel_size}{' (adaptive)' if args.adaptive_panel else ''}")
    print(f"  Personas:     {'REAL (KPM-1 bank)' if args.use_real_personas else 'synthetic'}")
    print(f"  Bootstrap:    {args.bootstrap}")
    print(f"  Concurrency:  {args.concurrency}")
    print(f"  Targets:      {set_label} + Caerphilly")
    print()

    results = []
    for i, meta in enumerate(lean_track, 1):
        print(f"[{i}/{len(lean_track)}] {meta['name']}...", flush=True, end="")
        try:
            res = run_council(meta, args.cassette, args.panel_size, args.seed, client,
                              use_real_personas=args.use_real_personas,
                              bootstrap_method=args.bootstrap,
                              adaptive_panel=args.adaptive_panel,
                              concurrency=args.concurrency,
                              panel_mode=args.panel_mode)
            mark = "✓" if res["kpm2_hit"] else "✗"
            print(f"  {res['kpm2_predicted']:25} ({res['kpm2_confidence']}) [{mark}]  "
                  f"actual={res['actual']:18}  ({res['elapsed_s']}s)")
            results.append(res)
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"council": meta["name"], "error": str(e)})

    # Caerphilly sanity (Welsh — not in May 7 set, no actual)
    if args.include_caerphilly:
        caerphilly_meta = {
            "name": "Caerphilly",
            "incumbent": "Labour",
            "kpm1_predicted": "n/a (not in KPM-1 set)",
            "actual": "n/a (sanity check only)",
        }
        print(f"[sanity] Caerphilly...", flush=True, end="")
        try:
            res = run_council(caerphilly_meta, args.cassette, args.panel_size, args.seed, client,
                              use_real_personas=args.use_real_personas)
            print(f"  {res['kpm2_predicted']:25} ({res['kpm2_confidence']})  "
                  f"P(NOC)={res['kpm2_noc_prob_pct']}%  ({res['elapsed_s']}s)")
            results.append(res)
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"council": "Caerphilly", "error": str(e)})

    # Score
    scored = [r for r in results if "kpm2_hit" in r and r["actual"] != "n/a (sanity check only)"]
    n = len(scored)
    kpm1_hits = sum(1 for r in scored if r["kpm1_hit"])
    kpm2_hits = sum(1 for r in scored if r["kpm2_hit"])

    print()
    print("=== Scoring (lean-track only, Caerphilly excluded) ===")
    print(f"  KPM-1 baseline:  {kpm1_hits}/{n}  ({100*kpm1_hits/n if n else 0:.1f}%)")
    print(f"  KPM-2 real-LLM:  {kpm2_hits}/{n}  ({100*kpm2_hits/n if n else 0:.1f}%)")
    delta = kpm2_hits - kpm1_hits
    print(f"  Delta:           {delta:+d} ({'IMPROVES' if delta > 0 else 'NO LIFT' if delta == 0 else 'REGRESSES'})")

    out_path = Path(args.save) if args.save else (
        REPO_ROOT / "data" / f"kpm2_phase5_run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    )
    out_path.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cassette": args.cassette,
        "panel_size": args.panel_size,
        "seed": args.seed,
        "llm_url": args.llm_url,
        "llm_model": args.llm_model,
        "scoring": {
            "kpm1_hits": kpm1_hits,
            "kpm2_hits": kpm2_hits,
            "n": n,
            "delta": delta,
        },
        "results": results,
    }, indent=2))
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
