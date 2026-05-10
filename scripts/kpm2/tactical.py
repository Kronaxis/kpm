"""KPM-2.2 #H — explicit tactical voting layer.

KPM-1 had `apply_tactical_voting` and `apply_stop_reform_tactical` baked
into its post-processing pipeline. KPM-2 dropped these in favour of
reading the persona's true preference directly. But the May 7 backtest
shows tactical voting genuinely shifts share in some councils (LD
"hold-the-Tory-out" votes especially in shire counties).

This module re-introduces tactical adjustment as an OPTIONAL post-
processing step KPM-2.2 can apply. Two modes:

  - stop_reform: lift LD/Lab/Green by transferring 30% of the smaller
    of those two parties' votes when they're competing for the runner-up
    spot against Reform. Captures progressive tactical voting in shire
    counties where Reform breaks through.

  - lib_lab: in seats where Lab and LD are competing for runner-up
    against the Tories, transfer 25% of the smaller to the larger.
    Captures the historical "Lib-Lab" anti-Tory tactical pact.

Honest scope: tactical voting is highly contextual. KPM-1's heuristic
caught some cases but missed others. KPM-2.2's version is opt-in and
applied post-bootstrap (so the bootstrap CIs already reflect persona
preferences; tactical is a deterministic last-mile tweak).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TacticalAdjustment:
    """Record of what tactical layer did to a council's vote shares."""

    mode: str
    transfer_from: str
    transfer_to: str
    transfer_pp: float
    rationale: str


def stop_reform_tactical(
    vote_shares: dict[str, float],
    transfer_pct: float = 0.30,
    min_reform_share: float = 22.0,
) -> tuple[dict[str, float], TacticalAdjustment | None]:
    """Anti-Reform tactical: in seats where Reform leads, progressives
    consolidate behind whichever of LD/Lab/Green has the strongest base.

    Trigger: Reform > min_reform_share AND there are at least two
    progressive parties splitting >5% each.
    Action: transfer transfer_pct of the SMALLER progressive's votes to
    the LARGER progressive.
    """
    reform = vote_shares.get("Reform UK", 0.0)
    lab = vote_shares.get("Labour", 0.0)
    ld = vote_shares.get("Liberal Democrat", 0.0)
    green = vote_shares.get("Green", 0.0)

    if reform < min_reform_share:
        return vote_shares, None

    progressives = [(p, s) for p, s in [("Labour", lab), ("Liberal Democrat", ld), ("Green", green)] if s > 5.0]
    if len(progressives) < 2:
        return vote_shares, None

    # Sort by share descending; transfer from the smallest to the largest progressive
    progressives.sort(key=lambda kv: -kv[1])
    largest_party, largest_share = progressives[0]
    smallest_party, smallest_share = progressives[-1]
    transfer = round(smallest_share * transfer_pct, 2)

    new_shares = dict(vote_shares)
    new_shares[smallest_party] = max(0.0, smallest_share - transfer)
    new_shares[largest_party] = largest_share + transfer

    return new_shares, TacticalAdjustment(
        mode="stop_reform",
        transfer_from=smallest_party,
        transfer_to=largest_party,
        transfer_pp=transfer,
        rationale=(
            f"Reform at {reform:.1f}% triggered anti-Reform tactical; "
            f"{transfer_pct*100:.0f}% of {smallest_party}'s {smallest_share:.1f}% "
            f"transferred to {largest_party}"
        ),
    )


def lib_lab_tactical(
    vote_shares: dict[str, float],
    transfer_pct: float = 0.25,
    min_tory_share: float = 25.0,
) -> tuple[dict[str, float], TacticalAdjustment | None]:
    """Anti-Tory tactical: where Cons leads, Lab/LD consolidate behind
    whichever is closer to challenging the Tory.
    """
    tory = vote_shares.get("Conservative", 0.0)
    lab = vote_shares.get("Labour", 0.0)
    ld = vote_shares.get("Liberal Democrat", 0.0)

    if tory < min_tory_share:
        return vote_shares, None
    if lab < 5.0 or ld < 5.0:
        return vote_shares, None

    if lab > ld:
        transfer_party = "Liberal Democrat"
        target_party = "Labour"
        transfer_share = ld
    else:
        transfer_party = "Labour"
        target_party = "Liberal Democrat"
        transfer_share = lab

    transfer = round(transfer_share * transfer_pct, 2)

    new_shares = dict(vote_shares)
    new_shares[transfer_party] = max(0.0, transfer_share - transfer)
    new_shares[target_party] = vote_shares.get(target_party, 0.0) + transfer

    return new_shares, TacticalAdjustment(
        mode="lib_lab",
        transfer_from=transfer_party,
        transfer_to=target_party,
        transfer_pp=transfer,
        rationale=(
            f"Cons at {tory:.1f}% triggered Lib-Lab tactical; "
            f"{transfer_pct*100:.0f}% of {transfer_party}'s {transfer_share:.1f}% "
            f"transferred to {target_party}"
        ),
    )


def apply_tactical(
    vote_shares: dict[str, float],
    enabled: list[str] | None = None,
) -> tuple[dict[str, float], list[TacticalAdjustment]]:
    """Apply selected tactical-voting transformations.

    enabled: subset of ["stop_reform", "lib_lab"]. Defaults to both.
    Returns the adjusted shares plus a list of TacticalAdjustment records
    so the caller can log what happened (audit trail for the methodology).
    """
    enabled = enabled or ["stop_reform", "lib_lab"]
    shares = dict(vote_shares)
    adjustments: list[TacticalAdjustment] = []

    if "stop_reform" in enabled:
        shares, adj = stop_reform_tactical(shares)
        if adj:
            adjustments.append(adj)
    if "lib_lab" in enabled:
        shares, adj = lib_lab_tactical(shares)
        if adj:
            adjustments.append(adj)

    return shares, adjustments
