"""KPM-2.1 cassette ensemble.

Runs all 3 pre-registered cassettes (conservative / balanced / aggressive)
on the same KPM-1 record (or KPM-2 prediction) and combines their verdicts.

Two combination modes:
  - majority: simple plurality across the 3 cassette winners. Ties go to
    the cassette ranked-as-best in the pre-reg backtest (for the test set
    KPM-2.1 ships with: balanced > aggressive > conservative).
  - weighted: weight each cassette's win_probability by historical
    accuracy. Reduces to majority when accuracies are equal.

The ensemble verdict is itself an output the user can choose; the
individual cassette outputs remain the falsifiable anchors per the
pre-reg discipline.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .classify import Classification, classify
from .rules import CASSETTES as PRE_REG_CASSETTES


# Default tiebreak ranking — derived from the v4 backtest where balanced
# delivered the best overall combined accuracy.
DEFAULT_TIEBREAK_ORDER = ["balanced", "aggressive", "conservative"]


@dataclass(frozen=True)
class EnsembleVerdict:
    """Aggregated classification across pre-registered cassettes."""

    predicted_winner: str
    confidence: str                           # "Confident" | "Lean" | "Toss-up" | "NOC"
    n_voting: int                             # how many cassettes agreed
    cassette_votes: dict[str, str]            # {cassette_name: predicted_winner}
    tiebreak_used: bool


def majority_vote(per_cassette: dict[str, Classification],
                  tiebreak_order: list[str] | None = None) -> EnsembleVerdict:
    """Plurality across cassettes; ties broken by the configured order."""
    order = tiebreak_order or DEFAULT_TIEBREAK_ORDER
    votes = Counter(c.predicted_winner for c in per_cassette.values())
    if not votes:
        return EnsembleVerdict("Unknown", "Toss-up", 0, {}, False)

    top_count = votes.most_common(1)[0][1]
    leaders = [w for w, c in votes.most_common() if c == top_count]
    tiebreak_used = len(leaders) > 1

    if tiebreak_used:
        # Pick the leader from the highest-priority cassette in the order
        chosen = None
        for cas_name in order:
            if cas_name in per_cassette and per_cassette[cas_name].predicted_winner in leaders:
                chosen = per_cassette[cas_name].predicted_winner
                break
        if chosen is None:
            chosen = leaders[0]
        winner = chosen
    else:
        winner = leaders[0]

    # Confidence: take the highest-priority cassette's confidence whose
    # winner equals the ensemble verdict
    confidence = "Toss-up"
    for cas_name in order:
        if cas_name in per_cassette and per_cassette[cas_name].predicted_winner == winner:
            confidence = per_cassette[cas_name].confidence
            break

    return EnsembleVerdict(
        predicted_winner=winner,
        confidence=confidence,
        n_voting=top_count,
        cassette_votes={n: c.predicted_winner for n, c in per_cassette.items()},
        tiebreak_used=tiebreak_used,
    )


def classify_ensemble(
    vote_shares: dict[str, float],
    win_probability: dict[str, int | float],
    cassettes: list[str] | None = None,
    tiebreak_order: list[str] | None = None,
) -> EnsembleVerdict:
    """Run all (or specified) pre-registered cassettes and return the ensemble verdict."""
    casset_names = cassettes or list(PRE_REG_CASSETTES.keys())
    per_cassette: dict[str, Classification] = {}
    for name in casset_names:
        per_cassette[name] = classify(vote_shares, win_probability, cassette=name)
    return majority_vote(per_cassette, tiebreak_order=tiebreak_order)
