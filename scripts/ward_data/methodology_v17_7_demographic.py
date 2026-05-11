"""KPM v17.7 = v17.6 + demographic signals from Census 2021.

Two new mechanisms:

1. **Demographic Reform-target detection** (council level)
   v17.6 fires Reform-emerging override only on councils with mean prior
   Reform ≥5%. Wolverhampton has 0% prior Reform across all wards so v17.6
   misses it. But Wolverhampton fits the post-industrial demographic
   profile (white British > 60%, L4 qualifications < 30%, no_qual > 25%).

   v17.7 adds a SECOND path to Reform-emerging classification:
     mean L4 qualifications < 30%  AND
     mean white British > 60%      AND
     prior winner = Lab (council)
   → flag council as "Reform-emerging via demographics"
   → trigger v17.6's outcome override

2. **Independent surge detection** (per-ward)
   Birmingham 2026: 6 of 8 Independent winners had ward Muslim% > 70%.
   The Gaza-coded campaign in Muslim-majority wards is now demographically
   detectable.

   v17.7 rule: per-ward predict Independent if
     ward Muslim% > 50%  AND
     prior winner is Labour
   This catches the Birmingham wards v17.6 misses.

This methodology is OPINIONATED but empirically grounded on n=15+ sample.
The demographic thresholds (L4<30%, white-British>60%, Muslim>50%) are
chosen as round numbers, not tuned. Cross-validation pending on bigger sample.
"""
from __future__ import annotations
import json, hashlib, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.ward_data.methodology_v17_6_council_override import predict_council_v17_6  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_5_council_reform import is_reform_emerging_council  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_3_reform_no_incumbency import predict_ward_v17_3  # type: ignore[import-not-found]

WARD = REPO / 'data' / 'ward_data'

# Per-council Reform-target via demographics
DEMOG_REFORM_L4_MAX = 30.0  # mean L4 qualifications < 30%
DEMOG_REFORM_WHITE_MIN = 60.0  # mean white British > 60%

# Per-ward Independent surge
INDEP_MUSLIM_MIN = 50.0  # ward Muslim% > 50%

def get_council_demographics(slug: str) -> dict:
    """Return mean demographics across a council's wards."""
    p = WARD / f'{slug}_2026.json'
    if not p.exists(): return {}
    d = json.loads(p.read_text())
    counts = {'qual_l4_pct': [], 'white_british_pct': [], 'muslim_pct': [], 'no_qual_pct': []}
    for w in d['wards']:
        c = w.get('census', {})
        if not c.get('matched'): continue
        for k in counts:
            v = c.get(k)
            if v is not None: counts[k].append(v)
    out = {}
    for k, vals in counts.items():
        if vals: out[f'mean_{k}'] = round(sum(vals)/len(vals), 2)
    return out

def is_demographically_reform_target(slug: str, history_wards: list) -> bool:
    """Check if council fits the Reform-target demographic profile.

    Three required conditions:
    - Mean L4 qualifications < 30%
    - Mean white British > 60%
    - Most prior winners are Labour (proxy for "Lab incumbent council")
    """
    demo = get_council_demographics(slug)
    if not demo.get('mean_qual_l4_pct') or not demo.get('mean_white_british_pct'):
        return False
    if demo['mean_qual_l4_pct'] >= DEMOG_REFORM_L4_MAX:
        return False
    if demo['mean_white_british_pct'] <= DEMOG_REFORM_WHITE_MIN:
        return False
    # Need majority Lab incumbents
    n_lab = sum(1 for w in history_wards if w.get('prior_winning_party') == 'Labour')
    if n_lab < 0.5 * len(history_wards):
        return False
    return True

def is_indep_surge_ward(history_ward: dict, current_census: dict) -> bool:
    """Check if a ward fits the Birmingham-style Independent surge profile."""
    if not current_census.get('matched'): return False
    muslim = current_census.get('muslim_pct', 0)
    if muslim < INDEP_MUSLIM_MIN: return False
    if history_ward.get('prior_winning_party') != 'Labour': return False
    return True

def predict_council_v17_7(council_slug: str) -> dict:
    """v17.7: v17.6 base + demographic Reform-target + per-ward Indep surge."""
    history_path = WARD / f'{council_slug}_history.json'
    current_path = WARD / f'{council_slug}_2026.json'
    if not history_path.exists():
        return {'error': f'No history for {council_slug}'}
    history = json.loads(history_path.read_text())
    current = json.loads(current_path.read_text()) if current_path.exists() else None
    history_by_slug = {w['ward_slug']: w for w in history['wards']}
    current_by_slug = {w['ward_slug']: w for w in current['wards']} if current else {}

    # Per-ward predictions with Independent surge override
    seat_counts: dict = {}
    target = current['wards'] if current else history['wards']
    indep_wards = 0
    for w_2026 in target:
        h = history_by_slug.get(w_2026['ward_slug'])
        if not h: continue
        # v17.3 ward prediction
        v17_3_pred = predict_ward_v17_3(h)
        winner = v17_3_pred.predicted_winner
        if winner == 'Unknown': continue

        # v17.7 Independent surge override
        ward_census = current_by_slug.get(w_2026['ward_slug'], {}).get('census', {})
        if is_indep_surge_ward(h, ward_census):
            winner = 'Independent'
            indep_wards += 1

        winner_count = w_2026.get('winner_count', 1) if current else h.get('prior_winner_count', 1)
        seat_counts[winner] = seat_counts.get(winner, 0) + winner_count

    total_seats = sum(seat_counts.values())
    sorted_seats = sorted(seat_counts.items(), key=lambda kv: -kv[1])
    if not sorted_seats: return {'error': 'no predictions'}
    largest, largest_n = sorted_seats[0]
    share = largest_n / total_seats

    # v17.6 council-level Reform-emergence detection
    council_emerging_prior = is_reform_emerging_council(history['wards'])
    # v17.7 demographic Reform-target check
    council_emerging_demo = is_demographically_reform_target(council_slug, history['wards'])
    council_emerging = council_emerging_prior or council_emerging_demo

    # 60% NOC overlay
    initial_winner = largest if share >= 0.60 else 'No overall control'

    # v17.6 outcome override (preserved): in Reform-emerging council, single-party-majority → Reform UK
    if council_emerging and initial_winner != 'No overall control' and initial_winner != 'Independent':
        council_winner = 'Reform UK'
        override_applied = True
    else:
        council_winner = initial_winner
        override_applied = False

    return {
        'council_slug': council_slug,
        'methodology': {'name': 'KPM-v17.7', 'version': 'v1.7', 'hash': methodology_hash()},
        'total_seats_predicted': total_seats,
        'seat_counts': dict(sorted_seats),
        'predicted_council_winner': council_winner,
        'largest_party_share_pct': round(100 * share, 1),
        'council_emerging_via_prior_reform': council_emerging_prior,
        'council_emerging_via_demographics': council_emerging_demo,
        'council_override_applied': override_applied,
        'n_indep_surge_wards': indep_wards,
    }

METHODOLOGY_RULES = {
    'schema_version': 'kpm-v17.7-demographic-conditioning',
    'name': 'kpm_v17_7_census_demographics',
    'description': (
        'v17.6 + Census 2021 demographic conditioning: '
        '(1) per-council Reform-target detection via L4<30% + whiteBritish>60% '
        '+ Lab incumbent (catches Wolverhampton-class 0%-prior-Reform sweeps); '
        '(2) per-ward Independent surge detection via Muslim>50% + Lab incumbent '
        '(catches Birmingham Gaza wards).'
    ),
    'demog_reform_l4_max_pct': DEMOG_REFORM_L4_MAX,
    'demog_reform_white_british_min_pct': DEMOG_REFORM_WHITE_MIN,
    'indep_surge_muslim_min_pct': INDEP_MUSLIM_MIN,
    'data_source_demographics': 'ONS Census 2021 (NOMIS bulk: TS067 qualifications, TS030 religion, TS021 ethnicity)',
    'base_methodology': 'kpm-v17.6',
    'rationale': (
        'v17.6 misses Wolverhampton (0% prior Reform across all wards) and 6/8 '
        'Birmingham Independent winners (0% prior Independent). Both failure modes '
        'have CRYSTAL CLEAR demographic signals: Wolverhampton fits white-British+'
        'low-qual profile that ALL Reform-sweep councils share; Birmingham Indep '
        'wards have Muslim% 70-84%. Census 2021 ward data is publicly available '
        'and bulk-downloadable from NOMIS in 2 MB total.'
    ),
    'risk': (
        'Demographic thresholds are round numbers chosen post-hoc on n=15 '
        'sample. Could over-fire on Tory shires with low qual + high white-British '
        'where Lab is nowhere (no Lab to bleed to Reform). Mitigated by requiring '
        'majority Lab incumbents in council.'
    ),
}

def methodology_hash():
    canonical = json.dumps(METHODOLOGY_RULES, sort_keys=True, indent=2, default=list)
    return hashlib.sha256(canonical.encode()).hexdigest()

if __name__ == '__main__':
    print(f"KPM-v17.7 hash: {methodology_hash()}\n")
    target = sys.argv[1] if len(sys.argv) > 1 else None
    if target:
        targets = [target]
    else:
        targets = sorted({p.stem.replace('_history','') for p in WARD.glob('*_history.json')})
    for slug in targets:
        pred = predict_council_v17_7(slug)
        if pred.get('error'):
            print(f"[skip] {slug}: {pred['error']}")
            continue
        flags = []
        if pred['council_emerging_via_prior_reform']: flags.append('prior')
        if pred['council_emerging_via_demographics']: flags.append('demo')
        if pred['council_override_applied']: flags.append('OVERRIDE')
        if pred['n_indep_surge_wards']: flags.append(f"IndepWards={pred['n_indep_surge_wards']}")
        flag_str = ' [' + ','.join(flags) + ']' if flags else ''
        print(f"  {slug:24s}: {pred['predicted_council_winner']:25s} (largest {pred['largest_party_share_pct']}%){flag_str}")
