"""Record an actual by-election outcome against a prior prediction in the scorecard.

Usage:
  python3 -m scripts.byelection.score \
    --prediction-id kpm22-v15-1-byel-2026-05-22-bradford-wibsey \
    --actual-winner "Reform UK" \
    --source-url https://www.bradford.gov.uk/...
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parents[2]

def norm_winner(w):
    s = (w or "").strip()
    return {"NOC":"No overall control","No Overall Control":"No overall control",
            "Lib Dem":"Liberal Democrat","Liberal Democrats":"Liberal Democrat",
            "Reform":"Reform UK","Conservatives":"Conservative",
            "Tories":"Conservative"}.get(s, s)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--prediction-id', required=True)
    ap.add_argument('--actual-winner', required=True)
    ap.add_argument('--source-url', required=True, help='Public source documenting the result')
    ap.add_argument('--note', default='', help='Optional: post-mortem note')
    args = ap.parse_args()

    sc_path = REPO / 'data' / 'scorecard' / 'kronaxis_scorecard.json'
    sc = json.loads(sc_path.read_text())
    found = None
    for p in sc['predictions']:
        if p['id'] == args.prediction_id:
            found = p
            break
    if not found:
        print(f"ERROR: prediction id {args.prediction_id} not in scorecard", file=sys.stderr)
        sys.exit(2)

    actual = norm_winner(args.actual_winner)
    found['actual_winner'] = actual
    found['actual_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
    found['actual_source'] = args.source_url
    found['hit'] = found['predicted_winner'] == actual
    if args.note:
        found['post_mortem_note'] = args.note

    sc['last_updated'] = found['actual_at']
    sc_path.write_text(json.dumps(sc, indent=2))
    badge = 'HIT' if found['hit'] else 'MISS'
    print(f"[{badge}] {found['subject']} - predicted {found['predicted_winner']}, actual {actual}")
    print(f"Updated: {sc_path}")
    print("Next: rerun scripts/scorecard/refresh.sh to recompute metrics + publish")

if __name__ == '__main__':
    main()
