#!/usr/bin/env bash
# Weekly by-election run.
# 1. Ingest fresh ALDC RSS items into calendar.json
# 2. Predict for entries with election_date in the next 7 days that have full data
# 3. Refresh scorecard
#
# Cron suggestion (Mondays 09:00):
#   0 9 * * 1 scripts/byelection/weekly_run.sh
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO"

CAL="data/byelection/calendar.json"
[[ -f "$CAL" ]] || { echo "no calendar at $CAL"; exit 1; }

echo "[byelection] Ingesting ALDC RSS..."
python3 scripts/byelection/ingest_aldc.py || echo "[byelection] ingest failed (network?), continuing"

TODAY=$(date -u +%Y-%m-%d)
NEXT_WEEK=$(date -u -d "+7 days" +%Y-%m-%d)
echo "[byelection] Scanning calendar for elections between $TODAY and $NEXT_WEEK"

python3 << PY
import json, subprocess
from pathlib import Path
from datetime import date
cal = json.loads(Path('data/byelection/calendar.json').read_text())
today = date.fromisoformat('$TODAY')
next_wk = date.fromisoformat('$NEXT_WEEK')
n_predicted = 0
for entry in cal.get('upcoming', []):
    edate = date.fromisoformat(entry['election_date'])
    if not (today <= edate <= next_wk): continue
    if entry.get('council') == 'TBD' or entry.get('status', '').startswith('placeholder'):
        print(f"  skip placeholder: {entry['id']}")
        continue
    if not entry.get('last_result_shares'):
        print(f"  skip no_shares: {entry['id']}")
        continue
    shares_str = ",".join(f"{k}={v}" for k, v in entry['last_result_shares'].items())
    cmd = [
        'python3', '-m', 'scripts.byelection.predict',
        '--council', entry['council'], '--ward', entry['ward'],
        '--election-date', entry['election_date'],
        '--incumbent', entry.get('incumbent_party', 'Independent'),
        '--region', entry.get('region', 'Unknown'),
        '--council-type', entry.get('council_type', ''),
        '--last-shares', shares_str,
    ]
    print(f"  predicting: {entry['council']} - {entry['ward']} on {entry['election_date']}")
    subprocess.run(cmd, check=True)
    n_predicted += 1
print(f"[byelection] Generated {n_predicted} predictions this week")
PY

echo "[byelection] Refreshing scorecard..."
scripts/scorecard/refresh.sh
