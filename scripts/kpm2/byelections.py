"""KPM-2.2 #L — continuous by-election prediction framework.

Predict every UK by-election in advance, score after, log Brier score.
Builds public falsifiability record over months/years.

Workflow per by-election:
  1. Add the seat to data/byelection_calendar.json with date + ward + council
  2. Run `python3 -m scripts.kpm2.byelections --predict <slug>` BEFORE polls open
  3. Hash the prediction (SHA-256) and commit to git as the pre-reg
  4. After result lands, run `--score <slug>` to record Brier + accuracy
  5. Aggregate Brier scores in data/kpm2_byelection_log.json

This is the single highest-leverage falsifiability instrument we own:
each by-election adds one row to the public scoring history. The Brier
score over N by-elections is the strongest single number we can quote
to journalists / academics.

Schema for byelection_calendar.json:
  {
    "byelections": [
      {
        "slug": "caerphilly-2026-10",
        "date": "2026-10-23",
        "ward": "Hengoed",
        "council": "Caerphilly",
        "type": "council",
        "incumbent_party": "Labour",
        "registered_at": "2026-05-09T...",
        "prediction_path": "data/byelection_predictions/...",
        "actual_winner": null,
        "scored_at": null,
        "brier_score": null,
        "hit": null
      }
    ]
  }
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CALENDAR_PATH = REPO_ROOT / "data" / "byelection_calendar.json"
LOG_PATH = REPO_ROOT / "data" / "kpm2_byelection_log.json"
PREDICTIONS_DIR = REPO_ROOT / "data" / "byelection_predictions"


def load_calendar() -> dict:
    if not CALENDAR_PATH.exists():
        return {"byelections": []}
    return json.loads(CALENDAR_PATH.read_text())


def save_calendar(c: dict) -> None:
    CALENDAR_PATH.parent.mkdir(parents=True, exist_ok=True)
    CALENDAR_PATH.write_text(json.dumps(c, indent=2))


def add_byelection(slug: str, date_iso: str, ward: str, council: str,
                   incumbent: str, type_: str = "council") -> dict:
    """Register a new upcoming by-election."""
    c = load_calendar()
    if any(b["slug"] == slug for b in c["byelections"]):
        raise ValueError(f"by-election {slug!r} already registered")
    record = {
        "slug": slug,
        "date": date_iso,
        "ward": ward,
        "council": council,
        "type": type_,
        "incumbent_party": incumbent,
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "prediction_path": None,
        "actual_winner": None,
        "scored_at": None,
        "brier_score": None,
        "hit": None,
    }
    c["byelections"].append(record)
    save_calendar(c)
    print(f"Registered by-election: {slug} ({council}, {date_iso})")
    return record


def predict_byelection(slug: str, cassette: str = "balanced", panel_size: int = 60,
                       use_real_personas: bool = True, bootstrap: str = "bayesian",
                       concurrency: int = 8, llm_url: str | None = None,
                       llm_model: str | None = None) -> dict:
    """Run KPM-2.2 prediction for one by-election; commit to disk + hash."""
    from .predict import predict_council, to_jsonable

    c = load_calendar()
    record = next((b for b in c["byelections"] if b["slug"] == slug), None)
    if not record:
        raise ValueError(f"by-election {slug!r} not registered. Use --add first.")

    # Build council context override using the by-election metadata
    ctx_override = {
        "council": record["council"],
        "incumbent": record["incumbent_party"],
        "election_date": record["date"],
    }

    # Pluggable LLM client
    from .llm import get_client
    client = None
    if llm_url:
        client = get_client("imprint", url=llm_url, model=llm_model or "imprint-9b")

    run = predict_council(
        council=record["council"],
        cassette=cassette,
        panel_size=panel_size,
        llm_client=client,
        llm_client_name="imprint" if client else "stub",
        seed=42,
        council_ctx_override=ctx_override,
        use_real_personas=use_real_personas,
        bootstrap_method=bootstrap,
        concurrency=concurrency,
    )

    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
    pred_path = PREDICTIONS_DIR / f"{slug}.json"
    payload = to_jsonable(run)
    pred_path.write_text(json.dumps(payload, indent=2))

    pred_hash = hashlib.sha256(pred_path.read_bytes()).hexdigest()
    record["prediction_path"] = str(pred_path.relative_to(REPO_ROOT))
    record["prediction_hash_sha256"] = pred_hash
    save_calendar(c)

    print(f"Predicted {slug}: {payload['posterior']['classification']['predicted_winner']} "
          f"({payload['posterior']['classification']['confidence']})")
    print(f"  Hash: {pred_hash}")
    return payload


def score_byelection(slug: str, actual_winner: str) -> dict:
    """Record the actual result + compute Brier score for the prediction."""
    c = load_calendar()
    record = next((b for b in c["byelections"] if b["slug"] == slug), None)
    if not record:
        raise ValueError(f"by-election {slug!r} not registered")
    if not record.get("prediction_path"):
        raise ValueError(f"no prediction on disk for {slug!r}")

    pred = json.loads((REPO_ROOT / record["prediction_path"]).read_text())
    win_prob = pred.get("win_probability", {})  # party -> %

    # Brier score: sum_i (p_i - y_i)^2 over parties, where y_i = 1 if actual, else 0
    parties = set(win_prob.keys()) | {actual_winner}
    brier = sum(
        ((win_prob.get(p, 0.0) / 100.0) - (1.0 if p == actual_winner else 0.0)) ** 2
        for p in parties
    )

    predicted_winner = pred.get("posterior", {}).get("classification", {}).get("predicted_winner", "")
    hit = (predicted_winner == actual_winner)

    record["actual_winner"] = actual_winner
    record["scored_at"] = datetime.now(timezone.utc).isoformat()
    record["brier_score"] = round(brier, 4)
    record["hit"] = hit
    save_calendar(c)

    # Append to running log
    log = []
    if LOG_PATH.exists():
        log = json.loads(LOG_PATH.read_text())
    log.append({
        "slug": slug,
        "date": record["date"],
        "council": record["council"],
        "predicted": predicted_winner,
        "actual": actual_winner,
        "hit": hit,
        "brier_score": round(brier, 4),
        "prediction_hash": record.get("prediction_hash_sha256", ""),
    })
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(json.dumps(log, indent=2))

    print(f"Scored {slug}: predicted={predicted_winner}, actual={actual_winner}, "
          f"hit={hit}, Brier={brier:.4f}")
    return record


def summary() -> dict:
    """Aggregate accuracy + mean Brier across all scored by-elections."""
    if not LOG_PATH.exists():
        return {"n": 0, "hits": 0, "accuracy_pct": 0.0, "mean_brier": 0.0}
    log = json.loads(LOG_PATH.read_text())
    n = len(log)
    if n == 0:
        return {"n": 0, "hits": 0, "accuracy_pct": 0.0, "mean_brier": 0.0}
    hits = sum(1 for r in log if r["hit"])
    mean_brier = sum(r["brier_score"] for r in log) / n
    return {
        "n": n,
        "hits": hits,
        "accuracy_pct": round(100.0 * hits / n, 1),
        "mean_brier": round(mean_brier, 4),
        "log_path": str(LOG_PATH.relative_to(REPO_ROOT)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    add_p = sub.add_parser("add", help="Register a new by-election")
    add_p.add_argument("--slug", required=True)
    add_p.add_argument("--date", required=True, help="ISO date")
    add_p.add_argument("--ward", required=True)
    add_p.add_argument("--council", required=True)
    add_p.add_argument("--incumbent", required=True)
    add_p.add_argument("--type", default="council")

    pred_p = sub.add_parser("predict", help="Run prediction for a registered by-election")
    pred_p.add_argument("--slug", required=True)
    pred_p.add_argument("--cassette", default="balanced")
    pred_p.add_argument("--panel-size", type=int, default=60)
    pred_p.add_argument("--bootstrap", default="bayesian")
    pred_p.add_argument("--concurrency", type=int, default=8)
    pred_p.add_argument("--use-real-personas", action="store_true", default=True)
    pred_p.add_argument("--llm-url", default="http://localhost:18000/v1/chat/completions")
    pred_p.add_argument("--llm-model", default="imprint-9b")

    score_p = sub.add_parser("score", help="Record actual result + compute Brier")
    score_p.add_argument("--slug", required=True)
    score_p.add_argument("--winner", required=True)

    sub.add_parser("summary", help="Print rolling Brier + accuracy log")

    args = parser.parse_args()

    if args.cmd == "add":
        add_byelection(args.slug, args.date, args.ward, args.council,
                       args.incumbent, type_=args.type)
    elif args.cmd == "predict":
        predict_byelection(
            args.slug, cassette=args.cassette, panel_size=args.panel_size,
            use_real_personas=args.use_real_personas, bootstrap=args.bootstrap,
            concurrency=args.concurrency, llm_url=args.llm_url, llm_model=args.llm_model,
        )
    elif args.cmd == "score":
        score_byelection(args.slug, args.winner)
    elif args.cmd == "summary":
        s = summary()
        print(f"\nKPM-2 by-election rolling record:")
        print(f"  N scored:      {s['n']}")
        print(f"  Hits:          {s['hits']}")
        print(f"  Accuracy:      {s['accuracy_pct']}%")
        print(f"  Mean Brier:    {s['mean_brier']}")


if __name__ == "__main__":
    main()
