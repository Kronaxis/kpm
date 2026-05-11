"""Orchestrator: ingest current results + history for ALL councils in
data/council_wards_2026.json.

Skips councils already ingested. Runs in batches of 5 with sleep
between batches to avoid sustained API pressure on Democracy Club.

Estimated total time for full 130-council run:
  - Current results: ~130 × 25 wards × 1.5s ≈ 80 min
  - History: ~130 × 25 wards × 3 prior dates × 1.5s ≈ 4 hours
  - Total: ~5 hours sequential

Resume-friendly: re-running skips councils with existing files.

Usage:
  # Dry-run to see what would be fetched:
  python3 -m scripts.ward_data.ingest_all_councils --dry-run

  # Real run, current results only:
  python3 -m scripts.ward_data.ingest_all_councils --current

  # Real run, history only (assumes current already done):
  python3 -m scripts.ward_data.ingest_all_councils --history

  # Full run with batching (recommended for overnight):
  python3 -m scripts.ward_data.ingest_all_councils --current --history --batch 5

Recommended overnight schedule:
  nohup python3 -u -m scripts.ward_data.ingest_all_councils --current --history --batch 5 > logs/ingest_all_$(date +%F).log 2>&1 &
"""
from __future__ import annotations
import argparse, json, subprocess, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COUNCIL_LIST = REPO / 'data' / 'council_wards_2026.json'
WARD_DATA = REPO / 'data' / 'ward_data'

BATCH_SLEEP_SEC = 30  # sleep between batches to keep API happy

def get_council_status() -> dict:
    """Return per-council status: has current? has history?"""
    council_list = json.loads(COUNCIL_LIST.read_text())
    status = {}
    for slug in sorted(council_list.keys()):
        current_path = WARD_DATA / f'{slug}_2026.json'
        history_path = WARD_DATA / f'{slug}_history.json'
        status[slug] = {
            'has_current': current_path.exists(),
            'has_history': history_path.exists(),
            'n_ballots': len(council_list[slug]),
        }
    return status

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--current', action='store_true', help='Fetch current results')
    ap.add_argument('--history', action='store_true', help='Fetch ward history')
    ap.add_argument('--batch', type=int, default=5, help='Councils per batch')
    ap.add_argument('--limit', type=int, default=0, help='Cap total councils (debug)')
    args = ap.parse_args()

    if not args.current and not args.history and not args.dry_run:
        ap.error('Pass at least one of --current --history --dry-run')

    status = get_council_status()
    total_councils = len(status)
    have_current = sum(1 for v in status.values() if v['has_current'])
    have_history = sum(1 for v in status.values() if v['has_history'])

    print(f"Council inventory:")
    print(f"  Total councils in 2026 ballot list: {total_councils}")
    print(f"  Have current results: {have_current}")
    print(f"  Have history:         {have_history}")
    print()

    if args.current:
        need_current = [s for s, v in status.items() if not v['has_current']]
        if args.limit: need_current = need_current[:args.limit]
        print(f"=== CURRENT FETCH ===")
        print(f"  Pending: {len(need_current)} councils")
        if args.dry_run:
            for s in need_current[:20]: print(f"  would fetch: {s} ({status[s]['n_ballots']} ballots)")
            if len(need_current) > 20: print(f"  ... and {len(need_current)-20} more")
        else:
            for i in range(0, len(need_current), args.batch):
                batch = need_current[i:i+args.batch]
                print(f"\n  Batch {i//args.batch + 1}: {','.join(batch)}")
                cmd = ['python3', '-u', '-m', 'scripts.ward_data.ingest_dc_ward_results', '--council', ','.join(batch)]
                subprocess.run(cmd, cwd=REPO)
                if i + args.batch < len(need_current):
                    print(f"  Sleeping {BATCH_SLEEP_SEC}s between batches...")
                    time.sleep(BATCH_SLEEP_SEC)

    if args.history:
        # Re-poll status — current run may have created files
        status = get_council_status()
        need_history = [s for s, v in status.items() if v['has_current'] and not v['has_history']]
        if args.limit: need_history = need_history[:args.limit]
        print(f"\n=== HISTORY FETCH ===")
        print(f"  Pending: {len(need_history)} councils (have current but no history)")
        if args.dry_run:
            for s in need_history[:20]: print(f"  would fetch: {s}")
            if len(need_history) > 20: print(f"  ... and {len(need_history)-20} more")
        else:
            for i in range(0, len(need_history), args.batch):
                batch = need_history[i:i+args.batch]
                print(f"\n  Batch {i//args.batch + 1}: {','.join(batch)}")
                cmd = ['python3', '-u', '-m', 'scripts.ward_data.ingest_dc_ward_history', '--council', ','.join(batch)]
                subprocess.run(cmd, cwd=REPO)
                if i + args.batch < len(need_history):
                    print(f"  Sleeping {BATCH_SLEEP_SEC}s between batches...")
                    time.sleep(BATCH_SLEEP_SEC)

    print(f"\n=== FINAL STATUS ===")
    final = get_council_status()
    have_current = sum(1 for v in final.values() if v['has_current'])
    have_history = sum(1 for v in final.values() if v['has_history'])
    print(f"  Have current results: {have_current}/{total_councils}")
    print(f"  Have history:         {have_history}/{total_councils}")

if __name__ == '__main__':
    main()
