# Kronaxis by-election engine

Continuous prediction pipeline for UK council by-elections (~150 per year, every Thursday).

## Pieces

- `ingest_aldc.py` — pulls ALDC's by-election RSS feed, populates `data/byelection/calendar.json`
- `predict.py` — given (council, ward, date, last result, swing assumption), produces a v15.1 prediction with hash + appends to scorecard
- `score.py` — given (prediction id, actual winner), records outcome + computes hit/miss
- `weekly_run.sh` — cron-safe weekly orchestrator (ingest -> predict next 7 days -> refresh scorecard)

## Vote-share prior

UNS (Uniform National Swing) from 2024 GE to 2026 polling baseline:
- Lab -10pp · Con -8pp · Reform +12pp · LD +1pp · Green +3pp

Source: 2024 GE results vs Wikipedia "Opinion polling for the next UK GE" rolling average. Swings reviewed monthly.

## Source data

- ALDC RSS: `https://www.aldc.org/category/by-election-results/feed/` (12 most recent)
- Per-event detail: ALDC article page (TODO: parse vote shares from article tables in iter 2)
- Last-result shares: TODO - need to add a per-ward last-result lookup

## Cron

```
# /etc/crontab
0 9 * * 1 jason scripts/byelection/weekly_run.sh >> /var/log/kronaxis/byelection.log 2>&1
```

Outputs land on the public scorecard at https://kronaxis.co.uk/scorecard
