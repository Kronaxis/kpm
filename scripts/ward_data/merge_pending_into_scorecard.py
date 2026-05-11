"""Merge data/ward_data/v17_scorecard_pending.json entries into the canonical
data/scorecard/kronaxis_scorecard.json.

Idempotent: skips entries whose id already exists in the canonical scorecard.
Local-only — does NOT publish anywhere. DEPLOY HOLD respected.

After merge:
  - Canonical scorecard grows by N entries
  - last_updated timestamp refreshed
  - Run scripts/scorecard/compute_metrics.py to refresh metrics
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parents[2]
PENDING = REPO / 'data' / 'ward_data' / 'v17_scorecard_pending.json'
SCORECARD = REPO / 'data' / 'scorecard' / 'kronaxis_scorecard.json'

def main():
    sc = json.loads(SCORECARD.read_text())
    pending = json.loads(PENDING.read_text())

    existing_ids = {p['id'] for p in sc['predictions']}
    n_appended = 0; n_skipped = 0
    by_methodology = {}

    for entry in pending['predictions']:
        if entry['id'] in existing_ids:
            n_skipped += 1
            continue
        sc['predictions'].append(entry)
        existing_ids.add(entry['id'])
        n_appended += 1
        m = entry['methodology']['name']
        by_methodology.setdefault(m, 0)
        by_methodology[m] += 1

    sc['last_updated'] = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
    SCORECARD.write_text(json.dumps(sc, indent=2))

    print(f"Appended {n_appended} entries (skipped {n_skipped} already-present)")
    print(f"Canonical scorecard now has {len(sc['predictions'])} predictions")
    print(f"\nBy methodology:")
    for m, n in sorted(by_methodology.items()):
        print(f"  {m}: {n}")

if __name__ == '__main__':
    main()
