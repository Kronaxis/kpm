"""KPM v17 ward-aware (kpm-v17-ward-uns).

For each ward: take prior-election party shares + apply year-scaled UNS +
(optional) incumbency boost. Predict winner = largest projected share.

Aggregate per-council: count seats per party (each ward contributes
`winner_count` seats to its winning party for v17 v0 — multi-member
proportional allocation deferred to v18). NOC if no party clears majority
threshold.

This is the FIRST methodology to use REAL ward-level prior data instead
of LLM-derived speculation. The earlier v16 (`scripts/kpm3/v16_ward_attempt.py`)
used aggregated LLM ward predictions and scored 21.0% per-ward (barely above
random).

Empirical baseline target: must beat 21.0% per-ward winner accuracy on the
Birmingham + Sheffield + Manchester sample (n=119 wards) to be worth
aggregating.

Methodology:
  1. For each ward in `data/ward_data/{council}_2026.json`:
     a. Look up prior result in `data/ward_data/{council}_history.json`
     b. Apply year-scaled UNS (2024→2026, 2023→2026, 2022→2026)
     c. Optional: +6pp incumbency boost to prior winning party
     d. Predicted winner = largest projected share
  2. Aggregate per council: party with most ward wins controls the council
     (NOC if no majority)

Known v17 limitations (acknowledged in `notes`):
  - Single UNS per year — no regional or council-class adjustment
  - No multi-member ward seat splitting (Lab+Green wards still go all to one)
  - Independents handled as a single bucket — actual ward-level Independents
    cannot be predicted from UNS (no national-polling baseline for them)
  - No ward-demographic adjustment (Census 2021 deprivation, ethnicity, age)
"""
from __future__ import annotations
from dataclasses import dataclass, field
import hashlib, json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Year-scaled national vote-share swings (May polling vs same-year council
# election ish). Approximated from YouGov/Opinium aggregates.
UNS_BY_PRIOR_YEAR = {
    2024: {
        'Labour': -10.0, 'Conservative': -8.0, 'Reform UK': +12.0,
        'Liberal Democrat': +1.0, 'Green': +3.0, 'Independent': +1.0,
        'Workers Party of Britain': 0.0, 'TUSC': 0.0,
        'Plaid Cymru': +1.0, 'Scottish National Party': 0.0,
    },
    2023: {
        'Labour': -12.0, 'Conservative': -10.0, 'Reform UK': +14.0,
        'Liberal Democrat': +1.0, 'Green': +3.0, 'Independent': +1.0,
        'Workers Party of Britain': 0.0, 'TUSC': 0.0,
        'Plaid Cymru': +1.0, 'Scottish National Party': 0.0,
    },
    2022: {
        'Labour': -14.0, 'Conservative': -12.0, 'Reform UK': +17.0,
        'Liberal Democrat': +1.0, 'Green': +4.0, 'Independent': +1.0,
        'Workers Party of Britain': 0.0, 'TUSC': 0.0,
        'Plaid Cymru': +1.0, 'Scottish National Party': 0.0,
    },
}

# Ward-level personal-incumbency boost (sitting councillor stands again).
# We can't always tell from the data, so apply this only when prior year
# is recent (≤2 years old) AND only to top-two parties' shares.
PERSONAL_INCUMBENT_BOOST_PP = 4.0

@dataclass
class V17Prediction:
    ward_slug: str
    ward_name: str
    predicted_winner: str
    predicted_shares: dict
    prior_winner: str
    prior_year: int
    confidence: str
    methodology_name: str = 'KPM-v17-ward-uns'
    methodology_version: str = 'v1.0'
    notes: list = field(default_factory=list)

def project_ward_shares(prior_shares: dict, prior_year: int, prior_winner: str | None) -> dict:
    """Apply year-scaled UNS + incumbency boost (recent priors only). Renormalise to 100."""
    swing = UNS_BY_PRIOR_YEAR.get(prior_year, UNS_BY_PRIOR_YEAR[2024])
    out = {}
    for p, s in prior_shares.items():
        new_s = s + swing.get(p, 0.0)
        # Personal incumbency boost: only for recent priors AND only if prior winner
        if prior_winner and p == prior_winner and prior_year >= 2024:
            new_s += PERSONAL_INCUMBENT_BOOST_PP
        out[p] = max(0.0, new_s)
    total = sum(out.values()) or 1
    return {k: round(100*v/total, 2) for k, v in out.items()}

def predict_ward(ward_history: dict) -> V17Prediction:
    prior_shares = ward_history.get('prior_party_shares', {})
    prior_winner = ward_history.get('prior_winning_party')
    prior_year = ward_history.get('prior_year', 2024)

    if not prior_shares:
        return V17Prediction(
            ward_slug=ward_history.get('ward_slug', '?'),
            ward_name=ward_history.get('ward_name', '?'),
            predicted_winner='Unknown', predicted_shares={},
            prior_winner=prior_winner or 'Unknown',
            prior_year=prior_year, confidence='NoData',
            notes=['No prior shares available'],
        )

    projected = project_ward_shares(prior_shares, prior_year, prior_winner)
    sorted_p = sorted(projected.items(), key=lambda kv: -kv[1])
    top, top_share = sorted_p[0]
    runner = sorted_p[1][1] if len(sorted_p) > 1 else 0
    margin = top_share - runner
    confidence = 'Confident' if margin > 15 else ('Lean' if margin > 5 else 'Toss-up')
    notes = []
    if prior_year < 2024:
        notes.append(f'Prior result is {2026 - prior_year} years old; UNS scaling approximated')
    return V17Prediction(
        ward_slug=ward_history['ward_slug'],
        ward_name=ward_history['ward_name'],
        predicted_winner=top, predicted_shares=projected,
        prior_winner=prior_winner or 'Unknown',
        prior_year=prior_year, confidence=confidence, notes=notes,
    )

def predict_council(council_slug: str) -> dict:
    """Predict every ward in a council, aggregate to seat counts."""
    history_path = REPO / 'data' / 'ward_data' / f'{council_slug}_history.json'
    current_path = REPO / 'data' / 'ward_data' / f'{council_slug}_2026.json'
    if not history_path.exists():
        return {'error': f'No history file for {council_slug}'}

    history = json.loads(history_path.read_text())
    current = json.loads(current_path.read_text()) if current_path.exists() else None

    history_by_slug = {w['ward_slug']: w for w in history['wards']}
    seat_counts = {}
    ward_predictions = []

    # Iterate over current 2026 wards (the ones we want to predict)
    target_wards = current['wards'] if current else history['wards']
    for w_2026 in target_wards:
        slug = w_2026['ward_slug']
        h = history_by_slug.get(slug)
        if not h:
            continue
        pred = predict_ward(h)
        if pred.predicted_winner == 'Unknown':
            continue
        winner_count = w_2026.get('winner_count', 1) if current else h.get('prior_winner_count', 1)
        seat_counts[pred.predicted_winner] = seat_counts.get(pred.predicted_winner, 0) + winner_count
        ward_predictions.append({
            'ward_slug': slug, 'ward_name': pred.ward_name,
            'predicted_winner': pred.predicted_winner,
            'projected_shares': pred.predicted_shares,
            'prior_year': pred.prior_year, 'prior_winner': pred.prior_winner,
            'winner_count': winner_count,
        })

    total_seats = sum(seat_counts.values())
    majority_threshold = (total_seats // 2) + 1
    sorted_seats = sorted(seat_counts.items(), key=lambda kv: -kv[1])
    if not sorted_seats:
        return {'error': 'No predictions made'}
    largest_party, largest_seats = sorted_seats[0]
    council_winner = largest_party if largest_seats >= majority_threshold else 'No overall control'

    return {
        'council_slug': council_slug,
        'methodology': {'name': 'KPM-v17-ward-uns', 'version': 'v1.0', 'hash': methodology_hash()},
        'total_seats_predicted': total_seats,
        'majority_threshold': majority_threshold,
        'seat_counts': dict(sorted_seats),
        'predicted_council_winner': council_winner,
        'ward_predictions': ward_predictions,
    }

METHODOLOGY_RULES = {
    'schema_version': 'kpm-v17-ward-uns-v1',
    'name': 'kpm_v17_ward_uns',
    'description': (
        'Apply year-scaled UNS to per-ward prior election shares + 4pp '
        'incumbency boost on recent priors. Per-ward FPTP. Aggregate to '
        'council-level seat counts. NOC if no party clears majority.'
    ),
    'uns_by_prior_year': UNS_BY_PRIOR_YEAR,
    'personal_incumbent_boost_pp': PERSONAL_INCUMBENT_BOOST_PP,
    'data_source_actuals': 'Democracy Club JSON API (candidates.democracyclub.org.uk/api/next/ballots/)',
    'data_source_priors': 'Democracy Club JSON API, most-recent-prior-with-result',
    'electoral_system': 'FPTP per-ward, single round, multi-member ward = winner takes all (v17 v0 limitation)',
    'known_limitations': (
        'Single UNS per year (no regional/council-class). No multi-member '
        'ward seat splitting. Independents handled as single bucket (cannot '
        'predict from UNS). No ward-demographic adjustment (Census 2021).'
    ),
}

def methodology_hash():
    canonical = json.dumps(METHODOLOGY_RULES, sort_keys=True, indent=2)
    return hashlib.sha256(canonical.encode()).hexdigest()

if __name__ == '__main__':
    import sys
    print(f"KPM-v17-ward-uns hash: {methodology_hash()}")
    print()
    target = sys.argv[1] if len(sys.argv) > 1 else 'birmingham'
    print(f"=== Council prediction: {target} ===")
    pred = predict_council(target)
    if pred.get('error'):
        print(f"  ERROR: {pred['error']}")
    else:
        print(f"  Total seats: {pred['total_seats_predicted']}")
        print(f"  Predicted winner: {pred['predicted_council_winner']}")
        print(f"  Seat counts: {pred['seat_counts']}")
        print()
        print(f"  Sample ward predictions:")
        for w in pred['ward_predictions'][:5]:
            print(f"    {w['ward_name']:30s} → {w['predicted_winner']:25s} (prior {w['prior_year']} winner: {w['prior_winner']})")
