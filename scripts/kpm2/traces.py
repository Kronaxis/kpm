"""KPM-2.2 #O — per-persona public reasoning traces.

KPM-1 published 19,376 individual reasoning traces alongside its
predictions — that's the falsifiability instrument that distinguished
KPM-1 from all other UK pollsters who publish only point estimates.

KPM-2.2's two-stage prompt collects per-persona REASON + FAV scores +
CERTAIN + VOTE. This module aggregates those into a publishable trace
artefact: one JSON line per persona, with full prompt + response + the
council/cassette context.

Output schema (JSONL, one line per trace):
  {
    "persona_id": "KX-123456",
    "council": "Wigan",
    "cassette": "balanced",
    "llm_model": "imprint-9b",
    "as_of": "2026-05-09T...",
    "persona_summary": {age_band, social_class, voted_2024, ...},
    "stimulus_response": {voted, vote_party, favourability_max, certainty_1to5},
    "raw_response_excerpt": "<first 400 chars of LLM output incl. REASON>"
  }

Used to ship per-by-election trace bundles + the May 7 retrospective bundle.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def extract_traces_from_prediction(pred_path: Path, council: str | None = None) -> list[dict]:
    """Extract persona-level trace records from a saved PredictionRun JSON.

    PredictionRun does NOT currently store per-persona records — only
    aggregate counts. This module is a SCAFFOLD: it produces the schema
    + writer. Full per-persona trace capture requires a PredictionRun
    refactor to retain `responses: list[StimulusResponse]` (deferred —
    breaks back-compat with existing JSONs).

    For now we emit aggregate-level trace records (one per cassette run,
    not one per persona). Per-persona trace shipping is a follow-up.
    """
    pred = json.loads(pred_path.read_text())
    council = council or pred.get("council", "unknown")

    return [{
        "council": council,
        "cassette": pred.get("cassette"),
        "llm_model": pred.get("llm_client"),
        "as_of": pred.get("generated_at"),
        "panel_size": pred.get("panel_size"),
        "n_voted": pred.get("n_voted"),
        "n_abstained": pred.get("n_abstained"),
        "raw_vote_counts": pred.get("raw_vote_counts"),
        "calibrated_vote_shares": pred.get("calibrated_vote_shares"),
        "win_probability": pred.get("win_probability"),
        "posterior_classification": pred.get("posterior", {}).get("classification"),
        "posterior_noc_prob_pct": pred.get("posterior", {}).get("noc_prob_pct"),
        "trace_schema_version": "kpm2-trace-v1-aggregate",
    }]


def bundle_traces(input_paths: list[Path], output_path: Path) -> dict:
    """Write a JSONL bundle of trace records from many PredictionRuns."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    n_records = 0
    with output_path.open("w") as f:
        for path in input_paths:
            for trace in extract_traces_from_prediction(path):
                f.write(json.dumps(trace) + "\n")
                n_records += 1
    return {
        "output_path": str(output_path),
        "n_records": n_records,
        "n_inputs": len(input_paths),
        "bundled_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", nargs="+", required=True,
                        help="One or more PredictionRun JSON paths")
    parser.add_argument("--output", required=True, help="Output JSONL path")
    args = parser.parse_args()

    paths = [Path(p) for p in args.inputs]
    summary = bundle_traces(paths, Path(args.output))
    print(f"Wrote {summary['n_records']} traces from {summary['n_inputs']} runs to {summary['output_path']}")


if __name__ == "__main__":
    main()
