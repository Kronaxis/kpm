"""KPM-2.2 #I — seat-count Monte Carlo for principled P(NOC).

KPM-2.0/2.1 synthesises P(NOC) from cassette gate thresholds — heuristic,
not principled. KPM-2.2 replaces this with a proper Monte Carlo:

  1. Draw N samples from the Dirichlet posterior over vote shares
     (same posterior used in bayesian_dirichlet_win_probability)
  2. For each sample, allocate council seats via cube-rule or
     proportional rule
  3. Count what fraction of samples produce ANY single party majority
  4. P(NOC) = 1 - max_party_majority_fraction

Two seat-allocation rules:
  - cube_rule: classical UK first-past-the-post heuristic. Seats ∝
    shares^3 normalised. Captures incumbency bias + over-representation
    of plurality winner.
  - proportional: pure share-weighted seat allocation. Useful for
    Welsh / STV councils.

Defaults: cube rule, 1000 Monte Carlo samples, council total seats from
KPM-1 record (or 50 if unknown).
"""
from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class NOCMonteCarloResult:
    """Output of seat-count Monte Carlo for one council."""

    p_noc_pct: float
    p_majority_per_party: dict[str, float]
    expected_largest_party: str
    expected_seats_per_party: dict[str, float]
    rule: str


def _cube_rule_seats(shares: dict[str, float], total_seats: int) -> dict[str, int]:
    """UK FPTP-ish allocation: seats ∝ share^3 normalised."""
    if not shares or total_seats <= 0:
        return {}
    cubed = {p: max(0.0, s) ** 3 for p, s in shares.items()}
    total = sum(cubed.values())
    if total <= 0:
        return {}
    raw_seats = {p: total_seats * (v / total) for p, v in cubed.items()}
    # Round to integers, conserve total
    int_seats = {p: int(s) for p, s in raw_seats.items()}
    remainder = total_seats - sum(int_seats.values())
    # Distribute remainder by largest fractional part
    fracs = sorted(((p, raw_seats[p] - int_seats[p]) for p in raw_seats),
                   key=lambda kv: -kv[1])
    for i in range(remainder):
        if i < len(fracs):
            int_seats[fracs[i][0]] += 1
    return int_seats


def _proportional_seats(shares: dict[str, float], total_seats: int) -> dict[str, int]:
    """Pure proportional allocation (D'Hondt approximation)."""
    if not shares or total_seats <= 0:
        return {}
    total = sum(max(0.0, s) for s in shares.values())
    if total <= 0:
        return {}
    raw = {p: total_seats * max(0.0, s) / total for p, s in shares.items()}
    int_seats = {p: int(v) for p, v in raw.items()}
    remainder = total_seats - sum(int_seats.values())
    fracs = sorted(((p, raw[p] - int_seats[p]) for p in raw), key=lambda kv: -kv[1])
    for i in range(remainder):
        if i < len(fracs):
            int_seats[fracs[i][0]] += 1
    return int_seats


def seat_count_monte_carlo(
    raw_counts: Counter,
    prior_shares: dict[str, float] | None = None,
    prior_strength: float = 30.0,
    total_seats: int = 50,
    n_iterations: int = 1000,
    rule: str = "cube",
    seed: int = 42,
) -> NOCMonteCarloResult:
    """Compute P(NOC) and per-party majority probabilities via Monte Carlo.

    raw_counts: party -> observed vote count from the LLM stimulus
    prior_shares: party -> prior fraction (e.g. calibrated pollster anchor)
    total_seats: council seat count (typical district 30-50, met borough 60-100)
    """
    parties = list(raw_counts.keys())
    if prior_shares:
        for p in prior_shares:
            if p not in parties:
                parties.append(p)

    if prior_shares is None:
        uniform = 1.0 / max(1, len(parties))
        prior_shares = {p: uniform for p in parties}

    alpha = []
    for p in parties:
        prior_count = prior_strength * float(prior_shares.get(p, 0.0))
        observed = float(raw_counts.get(p, 0))
        alpha.append(max(0.001, prior_count + observed))

    rng = random.Random(seed)
    majority_threshold = (total_seats // 2) + 1
    majority_count: Counter = Counter()
    largest_count: Counter = Counter()
    seat_total: dict[str, float] = {p: 0.0 for p in parties}
    noc_count = 0

    seat_fn = _cube_rule_seats if rule == "cube" else _proportional_seats

    for _ in range(n_iterations):
        gammas = [rng.gammavariate(a, 1.0) for a in alpha]
        gtotal = sum(gammas)
        if gtotal <= 0:
            continue
        sample_shares = {parties[i]: 100.0 * gammas[i] / gtotal for i in range(len(parties))}
        seats = seat_fn(sample_shares, total_seats)
        if not seats:
            continue

        # Track the largest party in this sample
        largest_party = max(seats, key=lambda p: seats[p])
        largest_count[largest_party] += 1
        for p, s in seats.items():
            seat_total[p] += s

        # Did any party get a majority?
        max_seats = seats[largest_party]
        if max_seats >= majority_threshold:
            majority_count[largest_party] += 1
        else:
            noc_count += 1

    p_noc = round(100.0 * noc_count / n_iterations, 1)
    p_majority = {p: round(100.0 * c / n_iterations, 1) for p, c in majority_count.items()}
    expected_largest = largest_count.most_common(1)[0][0] if largest_count else "Unknown"
    expected_seats = {p: round(t / n_iterations, 1) for p, t in seat_total.items()}

    return NOCMonteCarloResult(
        p_noc_pct=p_noc,
        p_majority_per_party=p_majority,
        expected_largest_party=expected_largest,
        expected_seats_per_party=expected_seats,
        rule=rule,
    )
