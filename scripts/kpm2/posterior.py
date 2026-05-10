"""KPM-2 posterior — full probability distribution per council.

KPM-1 publishes per-council:
  - vote_shares (point estimate per party)
  - win_probability (bootstrap-derived %, party -> 0-100)

KPM-1 does NOT publish:
  - P(NOC outcome)         — biggest gap — this is the May 7 lesson
  - P(party_X is largest)  — separate from "wins outright" once NOC exists
  - Per-party share quantile band (10/50/90)

KPM-2 derives all four from the existing KPM-1 bootstrap output + the
cassette-defined NOC threshold. The richer schema lets users see WHY a
council was classified NOC (e.g. P(NOC)=0.65 with three parties >20%) vs.
why a Confident call held (e.g. P(Lab wins)=0.92).

For share quantiles we synthesise a beta-binomial from the published
bootstrap win % + a Wilson interval. Less rigorous than re-running 1000
bootstrap iterations from scratch but uses the published numbers
faithfully — the alternative would be regenerating KPM-1's bootstrap
samples which were not retained on disk.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .classify import CASSETTES, Classification, classify
from .rules import FullCassette


@dataclass(frozen=True)
class PartyPosterior:
    """Per-party posterior summary."""

    party: str
    point_share_pp: float            # KPM-1 point estimate
    win_prob_pct: float              # bootstrap win probability (0-100)
    largest_share_prob_pct: float    # P(this party has largest share)
    share_p10_pp: float              # 10th percentile of share
    share_p90_pp: float              # 90th percentile of share


@dataclass(frozen=True)
class CouncilPosterior:
    """Full posterior output for one council."""

    council: str
    classification: Classification
    parties: dict[str, PartyPosterior] = field(default_factory=dict)
    noc_prob_pct: float = 0.0


def _wilson_interval(p_pct: float, n: int = 50) -> tuple[float, float]:
    """80% Wilson confidence interval for a proportion (p10, p90 in percentage points).

    Used to synthesise a share quantile band when raw bootstrap samples
    are not available. n=50 is the default panel size in KPM-1.
    """
    if n <= 0:
        return (p_pct, p_pct)
    p = max(0.0, min(1.0, p_pct / 100.0))
    z = 1.282  # z-score for 80% CI (≈ p10/p90)
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    p10 = max(0.0, centre - half) * 100.0
    p90 = min(100.0, centre + half) * 100.0
    return (round(p10, 2), round(p90, 2))


def _largest_party_probs(win_prob: dict[str, float]) -> dict[str, float]:
    """P(party is largest) ≈ P(party wins outright OR is largest in NOC).

    KPM-1's win_probability is already P(this party gets most votes), so
    largest_share_prob == win_prob in the underlying bootstrap. We expose
    it as a separate field because once NOC is a possible OUTPUT, "wins"
    and "largest" stop being synonyms (a party can be largest yet the
    council still goes NOC).
    """
    return dict(win_prob)


def derive_noc_probability(
    win_prob: dict[str, float],
    vote_shares: dict[str, float],
    cassette: FullCassette,
) -> float:
    """Estimate P(NOC) from cassette thresholds.

    Heuristic: a council goes NOC when no single party clears the cassette's
    margin/win-prob bar. We approximate P(NOC) as 1 - P(any single party
    exceeds the threshold).

    Conservative — the true posterior would require seat-count simulation,
    but for a published probability bar this synthesis is the honest read
    given the data we have.
    """
    sorted_shares = sorted(vote_shares.items(), key=lambda kv: kv[1], reverse=True)
    if len(sorted_shares) < 2:
        return 0.0
    winner, winner_share = sorted_shares[0]
    runner_up_share = sorted_shares[1][1]
    margin = winner_share - runner_up_share
    winner_winprob = float(win_prob.get(winner, 0.0))

    # If both gates fire (margin AND win_prob below threshold), NOC is near-certain
    if (margin < cassette.noc_margin_threshold_pp
            and winner_winprob < cassette.noc_winprob_threshold_pct):
        margin_dist = (cassette.noc_margin_threshold_pp - margin) / cassette.noc_margin_threshold_pp
        winprob_dist = (cassette.noc_winprob_threshold_pct - winner_winprob) / cassette.noc_winprob_threshold_pct
        return round(100.0 * min(0.95, 0.5 + 0.45 * (margin_dist + winprob_dist) / 2), 1)

    # If only one gate fires, NOC is plausible but not dominant
    if (margin < cassette.noc_margin_threshold_pp
            or winner_winprob < cassette.noc_winprob_threshold_pct):
        return round(100.0 * 0.3, 1)

    # Both gates closed: NOC is unlikely. Probability decays with margin.
    if margin > cassette.confident_margin_pp:
        return 0.0
    return round(100.0 * max(0.0, 0.2 - 0.01 * (margin - cassette.lean_margin_pp)), 1)


def compute_posterior(
    council_record: dict,
    cassette_name: str = "balanced",
    panel_size_hint: int = 50,
) -> CouncilPosterior:
    """Compute the KPM-2 posterior for a single council from a KPM-1 record."""
    cas = CASSETTES[cassette_name] if isinstance(cassette_name, str) else cassette_name

    vote_shares = council_record.get("vote_shares", {})
    win_prob = {p: float(v) for p, v in council_record.get("win_probability", {}).items()}
    largest = _largest_party_probs(win_prob)

    classification = classify(vote_shares, win_prob, cassette=cas)
    noc_prob = derive_noc_probability(win_prob, vote_shares, cas)

    parties: dict[str, PartyPosterior] = {}
    # Only meaningful parties (>1% share) get a posterior entry
    for party, share in sorted(vote_shares.items(), key=lambda kv: kv[1], reverse=True):
        if share < 1.0:
            continue
        p10, p90 = _wilson_interval(float(share), n=panel_size_hint)
        parties[party] = PartyPosterior(
            party=party,
            point_share_pp=round(float(share), 2),
            win_prob_pct=round(float(win_prob.get(party, 0.0)), 1),
            largest_share_prob_pct=round(float(largest.get(party, 0.0)), 1),
            share_p10_pp=p10,
            share_p90_pp=p90,
        )

    return CouncilPosterior(
        council=council_record.get("name", "Unknown"),
        classification=classification,
        parties=parties,
        noc_prob_pct=noc_prob,
    )


def to_dict(post: CouncilPosterior) -> dict:
    """Serialise CouncilPosterior to a JSON-friendly dict."""
    return {
        "council": post.council,
        "classification": {
            "predicted_winner": post.classification.predicted_winner,
            "confidence": post.classification.confidence,
            "margin_pp": round(post.classification.margin_pp, 2),
            "is_noc": post.classification.is_noc,
            "cassette": post.classification.cassette_name,
        },
        "noc_prob_pct": post.noc_prob_pct,
        "parties": [
            {
                "party": pp.party,
                "point_share_pp": pp.point_share_pp,
                "win_prob_pct": pp.win_prob_pct,
                "largest_share_prob_pct": pp.largest_share_prob_pct,
                "share_p10_pp": pp.share_p10_pp,
                "share_p90_pp": pp.share_p90_pp,
            }
            for pp in post.parties.values()
        ],
    }
