"""Enrich existing ward_data/{council}_2026.json files with ONS GSS codes.

For each ward, fetch the DC ballot JSON, extract post.id (e.g.
'gss:E05011118'), strip 'gss:' prefix, and add `ons_gss_code` field
to the ward dict. Idempotent — skips wards that already have the field.

Usage:
  python3 -m scripts.ward_data.enrich_ward_ons_codes
  python3 -m scripts.ward_data.enrich_ward_ons_codes --council birmingham
"""
from __future__ import annotations
import argparse, json, sys, time, urllib.request, urllib.error
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WARD = REPO / 'data' / 'ward_data'
DC_BASE = "https://candidates.democracyclub.org.uk/api/next/ballots/{ballot_id}.json"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
SLEEP_SEC = 1.0
MAX_RETRIES = 3

def fetch_post_id(ballot_id: str) -> str | None:
    url = DC_BASE.format(ballot_id=ballot_id)
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read())
            return (d.get('post') or {}).get('id')
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            if e.code == 429 and attempt < MAX_RETRIES - 1:
                time.sleep(8 * (attempt + 1))
                continue
            return None
        except (urllib.error.URLError, OSError):
            if attempt < MAX_RETRIES - 1:
                time.sleep(8)
                continue
            return None
    return None

def enrich_council(slug: str) -> tuple[int, int]:
    p = WARD / f'{slug}_2026.json'
    if not p.exists(): return 0, 0
    d = json.loads(p.read_text())
    n_added = 0; n_failed = 0
    for w in d['wards']:
        if w.get('ons_gss_code'): continue
        post_id = fetch_post_id(w['ballot_id'])
        time.sleep(SLEEP_SEC)
        if not post_id:
            n_failed += 1
            continue
        # post.id format: 'gss:E05011118' or sometimes 'pid:xxxx' (when no GSS)
        if post_id.startswith('gss:'):
            w['ons_gss_code'] = post_id[4:]
            n_added += 1
        else:
            w['ons_post_id'] = post_id
            n_failed += 1
    p.write_text(json.dumps(d, indent=2))
    return n_added, n_failed

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--council', help='Single council slug')
    args = ap.parse_args()

    if args.council:
        targets = [args.council]
    else:
        targets = sorted({p.stem.replace('_2026','') for p in WARD.glob('*_2026.json')})

    total_added = 0; total_failed = 0
    for slug in targets:
        added, failed = enrich_council(slug)
        if added or failed:
            print(f"  {slug:24s}: +{added} GSS codes ({failed} failed)")
        total_added += added; total_failed += failed
    print(f"\nTotal added: {total_added}, failed: {total_failed}")

if __name__ == '__main__':
    main()
