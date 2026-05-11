"""Match a (ward_name, council_pretty_name) pair to a Census 2021 ward record.

Strategy: try multiple normalised variants. Census ward names use multiple
disambiguation patterns (suffix in parens, council-prefix, etc.).

Returns the ONS GSS code (E05XXXXXX) if matched, None if not.
"""
from __future__ import annotations
import csv, json, sys
from pathlib import Path
from functools import lru_cache

REPO = Path(__file__).resolve().parents[2]
CENSUS = REPO / 'data' / 'census2021' / 'census2021-ts067-ward.csv'

@lru_cache(maxsize=1)
def load_census_index() -> dict[str, str]:
    """Map normalised ward name → ONS GSS code from Census."""
    out = {}
    with open(CENSUS) as f:
        for row in csv.DictReader(f):
            name = row['geography']
            code = row['geography code']
            out[name] = code  # exact match
            # Add normalised variants
            out[name.lower()] = code
    return out

def candidate_variants(ward_name: str, council_pretty: str) -> list[str]:
    """Generate candidate Census ward names for a (ward, council) pair."""
    base = ward_name.strip()
    council = council_pretty.strip()
    return [
        base,
        f"{base} ({council})",
        f"{council} {base}",
        f"{base} ({council.split()[0]})",  # short council
        f"{base} & {council}",
        base.replace(' & ', ' and '),
        base.replace(' and ', ' & '),
    ]

def find_ons_code(ward_name: str, council_pretty: str) -> str | None:
    idx = load_census_index()
    for variant in candidate_variants(ward_name, council_pretty):
        if variant in idx: return idx[variant]
        if variant.lower() in idx: return idx[variant.lower()]
    return None

def main():
    if len(sys.argv) < 3:
        print("usage: match_ward_to_census.py 'Ward Name' 'Council'")
        sys.exit(1)
    code = find_ons_code(sys.argv[1], sys.argv[2])
    print(code or 'NOT FOUND')

if __name__ == '__main__':
    main()
