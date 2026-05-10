#!/usr/bin/env bash
# Full scorecard refresh: regenerate seed + metrics + copy to website data.
# Idempotent. Safe to run from cron.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO"

echo "[scorecard] Rebuilding seed..."
python3 scripts/scorecard/seed_may7.py

echo "[scorecard] Computing metrics..."
python3 scripts/scorecard/compute_metrics.py

echo "[scorecard] Publishing to website..."
cp data/scorecard/kronaxis_scorecard.json website/kronaxis/data/
cp data/scorecard/kronaxis_scorecard_metrics.json website/kronaxis/data/

echo "[scorecard] Done. Files at:"
ls -la data/scorecard/*.json website/kronaxis/data/kronaxis_scorecard*.json
