"""Enrich ward_data/{council}_2026.json files with Census 2021 demographics
via name-matching (no DC API calls).

For each ward:
  - Find Census row matching (ward_name, council_pretty) variants
  - Add `census` dict with key demographic features

Usage:
  python3 -m scripts.ward_data.enrich_with_census
  python3 -m scripts.ward_data.enrich_with_census --council birmingham
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.ward_data._slug_pretty import slug_to_pretty  # type: ignore[import-not-found]
from scripts.ward_data.match_ward_to_census import find_ons_code  # type: ignore[import-not-found]
from scripts.ward_data.census_loader import get_ward_demographics  # type: ignore[import-not-found]

WARD = REPO / 'data' / 'ward_data'

def enrich_council(slug: str) -> tuple[int, int]:
    p = WARD / f'{slug}_2026.json'
    if not p.exists(): return 0, 0
    council_pretty = slug_to_pretty(slug)
    d = json.loads(p.read_text())
    matched = 0; missed = 0
    for w in d['wards']:
        if w.get('census'): continue  # already enriched
        code = find_ons_code(w['ward_name'], council_pretty)
        if not code:
            missed += 1
            w['census'] = {'matched': False, 'note': 'no Census ward found by name'}
            continue
        demo = get_ward_demographics(code)
        w['census'] = {
            'matched': True,
            'ons_gss_code': code,
            'qual_l4_pct': demo.get('qual_l4_pct'),
            'no_qual_pct': demo.get('no_qual_pct'),
            'muslim_pct': demo.get('muslim_pct'),
            'no_religion_pct': demo.get('no_religion_pct'),
            'age_under_35_pct': demo.get('age_under_35_pct'),
            'age_65_plus_pct': demo.get('age_65_plus_pct'),
            'social_rented_pct': demo.get('social_rented_pct'),
            'white_british_pct': demo.get('white_british_pct'),
        }
        matched += 1
    p.write_text(json.dumps(d, indent=2))
    return matched, missed

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--council', help='Single council slug')
    args = ap.parse_args()

    if args.council:
        targets = [args.council]
    else:
        targets = sorted({p.stem.replace('_2026','') for p in WARD.glob('*_2026.json')})

    total_matched = 0; total_missed = 0
    for slug in targets:
        m, miss = enrich_council(slug)
        if m or miss:
            print(f"  {slug:24s} matched={m} missed={miss}")
        total_matched += m; total_missed += miss
    print(f"\nTotal: {total_matched} matched, {total_missed} missed")

if __name__ == '__main__':
    main()
