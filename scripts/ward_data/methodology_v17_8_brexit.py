"""KPM v17.8 = v17.6 + Brexit 2016 Leave % as additional Reform-target signal.

Hypothesis: Wolverhampton-class councils (Reform-favourable demographics +
0% prior Reform) might be detectable via 2016 Brexit Leave %. Wolverhampton
constituencies had 54-68% Leave; Wakefield 62.8%; Hartlepool 69.6%.

Rule: Add a SECOND path to the Reform-emerging council flag:
  council mean constituency Leave % >= 60% AND
  council had Lab-incumbent council
→ flag as Brexit-Reform-target

Then v17.6's outcome override fires on these too.

Brexit data: Hanretty constituency-level estimates, mapped to councils via
constituency-name fuzzy match. Coverage: most metropolitan councils, some
districts not in Hanretty's dataset.
"""
from __future__ import annotations
import csv, json, hashlib, sys
from pathlib import Path
from functools import lru_cache

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.ward_data.methodology_v17_5_council_reform import is_reform_emerging_council  # type: ignore[import-not-found]
from scripts.ward_data.methodology_v17_3_reform_no_incumbency import predict_ward_v17_3  # type: ignore[import-not-found]
from scripts.ward_data._slug_pretty import slug_to_pretty  # type: ignore[import-not-found]

WARD = REPO / 'data' / 'ward_data'
BREXIT_CSV = REPO / 'data' / 'brexit2016' / 'hanretty_wards.csv'

BREXIT_LEAVE_THRESHOLD = 0.60  # 60% mean constituency Leave

@lru_cache(maxsize=1)
def load_brexit_constituencies() -> list[dict]:
    rows = []
    with open(BREXIT_CSV) as f:
        for row in csv.DictReader(f):
            try:
                row['leave_pct'] = float(row['Figure to use'])
                rows.append(row)
            except (ValueError, KeyError):
                continue
    return rows

def council_leave_pct(council_pretty: str) -> float | None:
    rows = load_brexit_constituencies()
    matches = [r['leave_pct'] for r in rows if council_pretty.lower() in r['Constituency'].lower()]
    if not matches: return None
    return sum(matches) / len(matches)

def is_brexit_reform_target(council_slug: str, history_wards: list) -> bool:
    """Check if council fits Brexit-Reform-target profile."""
    pretty = slug_to_pretty(council_slug)
    leave = council_leave_pct(pretty)
    if leave is None: return False
    if leave < BREXIT_LEAVE_THRESHOLD: return False
    # Also require Lab-incumbent council (majority of prior winners are Lab)
    n_lab = sum(1 for w in history_wards if w.get('prior_winning_party') == 'Labour')
    return n_lab >= 0.5 * len(history_wards)

def predict_council_v17_8(council_slug: str) -> dict:
    history_path = WARD / f'{council_slug}_history.json'
    current_path = WARD / f'{council_slug}_2026.json'
    if not history_path.exists():
        return {'error': f'No history for {council_slug}'}
    history = json.loads(history_path.read_text())
    current = json.loads(current_path.read_text()) if current_path.exists() else None
    history_by_slug = {w['ward_slug']: w for w in history['wards']}
    seat_counts: dict = {}
    target = current['wards'] if current else history['wards']
    for w_2026 in target:
        h = history_by_slug.get(w_2026['ward_slug'])
        if not h: continue
        v3 = predict_ward_v17_3(h)
        if v3.predicted_winner == 'Unknown': continue
        winner_count = w_2026.get('winner_count', 1) if current else h.get('prior_winner_count', 1)
        seat_counts[v3.predicted_winner] = seat_counts.get(v3.predicted_winner, 0) + winner_count

    total_seats = sum(seat_counts.values())
    sorted_seats = sorted(seat_counts.items(), key=lambda kv: -kv[1])
    if not sorted_seats: return {'error': 'no predictions'}
    largest, largest_n = sorted_seats[0]
    share = largest_n / total_seats
    initial_winner = largest if share >= 0.60 else 'No overall control'

    # Reform-emerging detection: prior OR Brexit
    council_emerging_prior = is_reform_emerging_council(history['wards'])
    council_emerging_brexit = is_brexit_reform_target(council_slug, history['wards'])
    council_emerging = council_emerging_prior or council_emerging_brexit

    if council_emerging and initial_winner != 'No overall control':
        council_winner = 'Reform UK'
    else:
        council_winner = initial_winner

    return {
        'council_slug': council_slug,
        'methodology': {'name': 'KPM-v17.8', 'version': 'v1.8', 'hash': methodology_hash()},
        'predicted_council_winner': council_winner,
        'largest_party_share_pct': round(100 * share, 1),
        'council_emerging_via_prior_reform': council_emerging_prior,
        'council_emerging_via_brexit': council_emerging_brexit,
    }

METHODOLOGY_RULES = {
    'schema_version': 'kpm-v17.8-brexit-reform-target',
    'name': 'kpm_v17_8_brexit',
    'description': (
        'v17.6 base + Brexit 2016 constituency-level Leave % as additional '
        'Reform-target signal. If council mean Leave >= 60% AND Lab-incumbent '
        'council → flag Reform-emerging.'
    ),
    'brexit_leave_threshold': BREXIT_LEAVE_THRESHOLD,
    'brexit_data_source': 'Hanretty constituency-level Leave estimates (Harvard Dataverse)',
}

def methodology_hash():
    return hashlib.sha256(json.dumps(METHODOLOGY_RULES, sort_keys=True, indent=2, default=list).encode()).hexdigest()

if __name__ == '__main__':
    print(f"KPM-v17.8 hash: {methodology_hash()}\n")
    targets = sorted({p.stem.replace('_history','') for p in WARD.glob('*_history.json')})
    for slug in targets:
        pred = predict_council_v17_8(slug)
        if 'error' in pred: continue
        flags = []
        if pred['council_emerging_via_prior_reform']: flags.append('prior')
        if pred['council_emerging_via_brexit']: flags.append('brexit')
        flag_str = ' [' + ','.join(flags) + ']' if flags else ''
        print(f"  {slug:24s}: {pred['predicted_council_winner']:25s} (largest {pred['largest_party_share_pct']}%){flag_str}")
