"""Diagnostic: was Independent strength visible in prior election for the
wards that elected Independents in 2026?

If YES → v17.1 Independent-detection rule is buildable from priors alone.
If NO  → Independent surge is unpredictable from priors (genuinely needs
         external signals like Census ethnicity or news). Document as a
         known unpredictable failure mode.

For each ward where actual_2026 winner = Independent:
  - Look up the prior election in *_history.json
  - Print: prior_party_shares including Independent share + winner
"""
from __future__ import annotations
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WARD_DIR = REPO / 'data' / 'ward_data'

def main():
    independent_wards_2026 = []
    for actual_path in WARD_DIR.glob('*_2026.json'):
        slug = actual_path.stem.replace('_2026', '')
        history_path = WARD_DIR / f'{slug}_history.json'
        if not history_path.exists():
            continue
        actual = json.loads(actual_path.read_text())
        history = json.loads(history_path.read_text())
        history_by_slug = {w['ward_slug']: w for w in history['wards']}

        for w in actual['wards']:
            if w.get('winning_party') != 'Independent':
                continue
            h = history_by_slug.get(w['ward_slug'])
            if not h:
                continue
            independent_wards_2026.append({
                'council': slug, 'ward': w['ward_name'],
                'prior_year': h['prior_year'],
                'prior_winner': h.get('prior_winning_party'),
                'prior_shares': h.get('prior_party_shares', {}),
                'prior_independent_share': h.get('prior_party_shares', {}).get('Independent', 0),
                'actual_winner': w['winning_party'],
                'actual_shares': w.get('party_shares', {}),
                'actual_independent_share': w.get('party_shares', {}).get('Independent', 0),
            })

    if not independent_wards_2026:
        print("No Independent winners in 2026 sample. Cannot diagnose.")
        return

    print(f"=== {len(independent_wards_2026)} wards with Independent winner in 2026 ===\n")
    print(f"{'Council':16s} {'Ward':28s} {'Prior yr':>8s} {'Prior winner':18s} {'Prior Ind%':>11s} {'Actual Ind%':>12s}")
    print('-' * 95)
    detectable = 0; undetectable = 0
    for w in independent_wards_2026:
        prior_ind = w['prior_independent_share']
        is_detectable = prior_ind >= 5.0
        if is_detectable:
            detectable += 1
        else:
            undetectable += 1
        flag = '✓ detectable' if is_detectable else '✗ surprise'
        print(f"  {w['council']:16s} {w['ward']:28s} {w['prior_year']:>8} {str(w['prior_winner']):18s} {prior_ind:>10.1f}% {w['actual_independent_share']:>11.1f}%  {flag}")

    print('-' * 95)
    print(f"\nSummary: {detectable} detectable from priors (Ind ≥5% before), "
          f"{undetectable} surprise (Ind <5% before, emerged in 2026 only)")
    print()
    if undetectable > detectable:
        print("CONCLUSION: Independent surge in 2026 is mostly NOT predictable from priors.")
        print("Needs external signal (Census 2021 ethnicity / 2024 GE Independent activity).")
        print("v17.1 from priors alone won't help materially.")
    else:
        print("CONCLUSION: Most Independent winners had prior Independent strength.")
        print("v17.1 Independent-detection rule is buildable from priors alone.")

if __name__ == '__main__':
    main()
