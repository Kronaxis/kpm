"""Load Census 2021 ward-level demographics from the 5 NOMIS bulk CSVs.

Returns a dict keyed by ONS GSS code (E05XXXXXX) → demographic features.

Variables computed:
  - qual_l4_pct: % aged 16+ with NVQ4+ qualifications (degree-equivalent)
  - no_qual_pct: % with no qualifications
  - muslim_pct: % Muslim
  - christian_pct: % Christian
  - no_religion_pct: % no religion
  - age_under_35_pct: % aged under 35
  - age_65_plus_pct: % aged 65+
  - social_rented_pct: % in social rented housing
  - white_british_pct: % White British
  - asian_pct: % Asian (broad group)

Usage:
  python3 -m scripts.ward_data.census_loader  # dump all wards' demographics
  python3 -m scripts.ward_data.census_loader E05011118  # one ward
"""
from __future__ import annotations
import csv, json, sys
from pathlib import Path
from functools import lru_cache

REPO = Path(__file__).resolve().parents[2]
CENSUS = REPO / 'data' / 'census2021'

@lru_cache(maxsize=1)
def load_qualifications() -> dict[str, dict]:
    """TS067: Highest level of qualification by ward."""
    out = {}
    with open(CENSUS / 'census2021-ts067-ward.csv') as f:
        for row in csv.DictReader(f):
            code = row['geography code']
            total = int(row['Highest level of qualification: Total: All usual residents aged 16 years and over'])
            if total == 0: continue
            l4 = int(row['Highest level of qualification: Level 4 qualifications or above'])
            no_qual = int(row['Highest level of qualification: No qualifications'])
            out[code] = {
                'qual_l4_pct': round(100 * l4 / total, 2),
                'no_qual_pct': round(100 * no_qual / total, 2),
                'qual_total': total,
            }
    return out

@lru_cache(maxsize=1)
def load_religion() -> dict[str, dict]:
    """TS030: Religion by ward."""
    out = {}
    with open(CENSUS / 'census2021-ts030-ward.csv') as f:
        for row in csv.DictReader(f):
            code = row['geography code']
            # Find total + Muslim + Christian + no religion columns
            total_key = next((k for k in row if 'Total: All usual residents' in k), None)
            if not total_key: continue
            total = int(row[total_key])
            if total == 0: continue
            muslim = int(row.get('Religion: Muslim', 0))
            christian = int(row.get('Religion: Christian', 0))
            no_rel = int(row.get('Religion: No religion', 0))
            out[code] = {
                'muslim_pct': round(100 * muslim / total, 2),
                'christian_pct': round(100 * christian / total, 2),
                'no_religion_pct': round(100 * no_rel / total, 2),
            }
    return out

@lru_cache(maxsize=1)
def load_age() -> dict[str, dict]:
    """TS007: Age by single year. We aggregate to under-35 and 65+."""
    out = {}
    with open(CENSUS / 'census2021-ts007-ward.csv') as f:
        for row in csv.DictReader(f):
            code = row['geography code']
            total_key = next((k for k in row if 'Total: All usual residents' in k), None)
            if not total_key: continue
            total = int(row[total_key])
            if total == 0: continue
            # Sum ages 0-34 (under 35) and 65+
            under_35 = 0; age_65plus = 0
            for k, v in row.items():
                # Column format: 'Age: Aged X years'
                if not k.startswith('Age: Aged '): continue
                if 'Total' in k or 'under' in k.lower(): continue
                # Parse age from 'Age: Aged N years' or 'Age: Aged N year'
                try:
                    age_part = k.replace('Age: Aged ', '').replace(' years and over', '+').replace(' years', '').replace(' year', '').strip()
                    if age_part.startswith('under') or age_part.startswith('Under'):
                        # 'Aged under 1 year' counts as under 35
                        under_35 += int(v) if v else 0
                        continue
                    if age_part.endswith('+'):
                        age_n = int(age_part[:-1])
                        if age_n <= 34: under_35 += int(v) if v else 0
                        if age_n >= 65: age_65plus += int(v) if v else 0
                        continue
                    age_n = int(age_part)
                    if age_n <= 34: under_35 += int(v) if v else 0
                    if age_n >= 65: age_65plus += int(v) if v else 0
                except (ValueError, TypeError):
                    continue
            out[code] = {
                'age_under_35_pct': round(100 * under_35 / total, 2),
                'age_65_plus_pct': round(100 * age_65plus / total, 2),
            }
    return out

@lru_cache(maxsize=1)
def load_tenure() -> dict[str, dict]:
    """TS054: Tenure of household by ward."""
    out = {}
    with open(CENSUS / 'census2021-ts054-ward.csv') as f:
        for row in csv.DictReader(f):
            code = row['geography code']
            total_key = next((k for k in row if 'Total: All households' in k), None)
            if not total_key:
                total_key = next((k for k in row if 'Total' in k), None)
            if not total_key: continue
            try:
                total = int(row[total_key])
            except (ValueError, KeyError):
                continue
            if total == 0: continue
            social = 0
            for k, v in row.items():
                if 'Social rented' in k and 'Total' not in k:
                    try: social += int(v)
                    except (ValueError, TypeError): pass
            out[code] = {'social_rented_pct': round(100 * social / total, 2)}
    return out

@lru_cache(maxsize=1)
def load_ethnicity() -> dict[str, dict]:
    """TS021: Broad ethnic group by ward."""
    out = {}
    with open(CENSUS / 'census2021-ts021-ward.csv') as f:
        for row in csv.DictReader(f):
            code = row['geography code']
            total_key = next((k for k in row if 'Total: All usual residents' in k), None)
            if not total_key: continue
            total = int(row[total_key])
            if total == 0: continue
            white_british = 0; asian = 0
            for k, v in row.items():
                if 'White: English' in k or 'White: Welsh' in k or 'White: Scottish' in k or 'White: British' in k:
                    try: white_british += int(v)
                    except (ValueError, TypeError): pass
                if k.startswith('Ethnic group: Asian'):
                    if 'Asian, Asian British' not in k or k.endswith('British: Total'):
                        try: asian = max(asian, int(v))
                        except (ValueError, TypeError): pass
            out[code] = {
                'white_british_pct': round(100 * white_british / total, 2),
                'asian_pct': round(100 * asian / total, 2),
            }
    return out

def get_ward_demographics(ons_code: str) -> dict:
    """Combined demographics for a single ward by ONS code."""
    out = {'ons_gss_code': ons_code}
    for loader in [load_qualifications, load_religion, load_age, load_tenure, load_ethnicity]:
        d = loader().get(ons_code, {})
        out.update(d)
    return out

if __name__ == '__main__':
    if len(sys.argv) > 1:
        code = sys.argv[1]
        d = get_ward_demographics(code)
        print(json.dumps(d, indent=2))
    else:
        # Sample a few wards
        sample_codes = ['E05011118', 'E05011112', 'E05000650']  # Acocks Green, Aston, Astley Bridge
        for code in sample_codes:
            d = get_ward_demographics(code)
            print(json.dumps(d, indent=2))
            print()
