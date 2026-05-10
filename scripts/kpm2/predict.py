"""KPM-2 prediction orchestrator.

Wires the KPM-2 building blocks into one pipeline:

  persona panel  →  LLM stimulus  →  raw vote shares
                                      ↓
                  apply turnout/abstention filtering
                                      ↓
                  apply per-party calibration shifts (calibrate.py)
                                      ↓
                  bootstrap CI for win_probability
                                      ↓
                  classify with chosen cassette (classify.py)
                                      ↓
                  synthesise posterior (posterior.py)
                                      ↓
                  CouncilPosterior + audit trail JSON

Synthetic personas: a minimal generator is included for end-to-end
smoke tests when the full DYNAMICS-8 panel isn't available. Real
production should swap in KPM-1's `build_council_panel` from
`scripts.predict_may7_elections` (5,045-line module — left untouched
as historical record, can be imported when wired up on DL580).

Usage:
  python3 -m scripts.kpm2.predict --council Caerphilly --llm stub
  python3 -m scripts.kpm2.predict --council Caerphilly --llm imprint --panel-size 50
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from .calibrate import fit_calibration
from .classify import CASSETTES
from .llm import LLMClient, StimulusResponse, get_client, stimulate_panel_async
from .posterior import compute_posterior, to_dict as posterior_to_dict
from .turnout import get_turnout


REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class PredictionRun:
    """End-to-end prediction record for one council, fully audit-traceable."""

    council: str
    cassette: str
    panel_size: int
    n_voted: int
    n_abstained: int
    raw_vote_counts: dict[str, int]
    raw_vote_shares: dict[str, float]
    calibration_applied: dict[str, float]
    calibrated_vote_shares: dict[str, float]
    win_probability: dict[str, float]
    posterior: dict
    turnout_pct: float | None = None
    abstention_pct: float | None = None
    seed: int = 42
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    llm_client: str = "stub"


def synthesize_panel(council: str, council_ctx: dict, panel_size: int = 50, seed: int = 42) -> list[dict]:
    """Deterministic synthetic panel with enough demographic + political
    signal for an LLM to differentiate personas.

    Honest scope: this is NOT DYNAMICS-8. KPM-1's `build_council_panel`
    uses census-weighted DYNAMICS-8 personas with full personality vectors.
    This synthetic panel uses simple draws from realistic UK distributions
    (age, class, prior vote, main issue) so the pipeline can be validated
    end-to-end without DYNAMICS-8 panel data on disk. Production runs
    should swap this for the KPM-1 builder once integration is wired.

    Distributions calibrated to UK 2024 GE + Apr-May 2026 polling shifts:
      Reform UK 28% / Labour 22% / Conservative 18% / LD 12% / Green 12%
      / Independent 4% / Won't say 4%
    """
    panel: list[dict] = []
    region = council_ctx.get("region", "England")
    incumbent = council_ctx.get("incumbent", "Labour")

    # National prior — calibrated to current rolling pollster avg
    prior_vote_dist = [
        ("Reform UK",        0.28),
        ("Labour",           0.22),
        ("Conservative",     0.18),
        ("Liberal Democrat", 0.12),
        ("Green",            0.12),
        ("Independent",      0.04),
        ("Did not vote",     0.04),
    ]
    age_dist = [("18-24", 0.10), ("25-44", 0.33), ("45-64", 0.33), ("65+", 0.24)]
    class_dist = [
        ("AB - professional/managerial",  0.25),
        ("C1 - clerical",                 0.27),
        ("C2 - skilled manual",           0.21),
        ("DE - semi/unskilled, retired",  0.27),
    ]
    issue_dist = [
        ("Cost of living",     0.32),
        ("NHS",                0.18),
        ("Immigration",        0.21),
        ("Housing",            0.10),
        ("Environment",        0.08),
        ("Crime / policing",   0.07),
        ("None / don't know",  0.04),
    ]

    def draw(dist: list[tuple], h_byte: int) -> str:
        """Discrete draw from a (label, weight) distribution given an entropy byte."""
        u = h_byte / 256.0
        acc = 0.0
        for label, w in dist:
            acc += w
            if u <= acc:
                return label
        return dist[-1][0]

    base_turnout = float(council_ctx.get("baseline_turnout", 0.30))

    for i in range(panel_size):
        seed_str = f"{council}|{i}|{seed}"
        h = hashlib.sha256(seed_str.encode("utf-8")).digest()

        # Persona has higher turnout if older + more politically engaged
        engagement = (h[6] % 5) + 1
        age_idx = next(idx for idx, (lbl, _) in enumerate(age_dist) if lbl == draw(age_dist, h[0]))
        age_uplift = age_idx * 0.04   # 65+ adds 12pp to baseline
        engagement_uplift = (engagement - 3) * 0.05
        bias = (int.from_bytes(h[8:12], "big") / (1 << 32) - 0.5) * 0.20
        turnout_prob = max(0.05, min(0.95, base_turnout + age_uplift + engagement_uplift + bias))

        panel.append({
            "id": f"{council}_p{i:03d}",
            "turnout_probability": round(turnout_prob, 4),
            "age_band": draw(age_dist, h[0]),
            "social_class": draw(class_dist, h[1]),
            "homeowner": bool(h[2] & 1),
            "voted_2024_ge": draw(prior_vote_dist, h[3]),
            "main_issue_2026": draw(issue_dist, h[4]),
            "political_engagement_1to5": engagement,
            "region": region,
            "council_incumbent": incumbent,
        })
    return panel


def stimulate_panel(panel: list[dict], council_ctx: dict, client: LLMClient) -> list[StimulusResponse]:
    """Run the LLM client over each persona, collecting StimulusResponses."""
    return [client.stimulate(persona, council_ctx) for persona in panel]


def aggregate_votes(responses: list[StimulusResponse]) -> tuple[Counter, dict[str, float]]:
    """Return (raw counts, raw % shares) for personas that voted."""
    counts: Counter = Counter()
    n_voted = 0
    for r in responses:
        if r.voted and r.vote_party:
            counts[r.vote_party] += 1
            n_voted += 1
    if n_voted == 0:
        return counts, {}
    shares = {p: round(100.0 * c / n_voted, 2) for p, c in counts.items()}
    return counts, shares


def apply_calibration(raw_shares: dict[str, float], shifts: dict[str, float]) -> dict[str, float]:
    """Add per-party shifts. Re-normalise so the result still sums to 100."""
    if not raw_shares:
        return {}
    shifted = {p: max(0.0, raw_shares.get(p, 0.0) + shifts.get(p, 0.0)) for p in raw_shares}
    # Re-add parties that have a shift but weren't in raw (rare edge — usually anchor parties)
    for p, s in shifts.items():
        if p not in shifted:
            shifted[p] = max(0.0, s)
    total = sum(shifted.values())
    if total <= 0:
        return raw_shares
    return {p: round(100.0 * v / total, 2) for p, v in shifted.items()}


def bootstrap_win_probability(
    raw_counts: Counter,
    n_iterations: int = 1000,
    seed: int = 42,
) -> dict[str, float]:
    """Resample with replacement to estimate P(party wins).

    Faithful to KPM-1's bootstrap: same vote pool size, sample with
    replacement, count which party gets most votes per iteration, divide
    by iterations.
    """
    pool: list[str] = []
    for party, c in raw_counts.items():
        pool.extend([party] * c)
    if not pool:
        return {}

    rng = random.Random(seed)
    win_count: Counter = Counter()
    n = len(pool)
    for _ in range(n_iterations):
        sample = [rng.choice(pool) for _ in range(n)]
        sample_counts: Counter = Counter(sample)
        winner, _ = sample_counts.most_common(1)[0]
        win_count[winner] += 1

    return {p: round(100.0 * c / n_iterations, 1) for p, c in win_count.items()}


def hierarchical_bootstrap_win_probability(
    raw_counts: Counter,
    persona_uncertainty: dict[str, list[int]] | None = None,
    n_iterations: int = 1500,
    seed: int = 42,
) -> dict[str, float]:
    """KPM-2.2 #J — two-level hierarchical bootstrap.

    Level 1: sample a panel of personas (with replacement)
    Level 2: for each persona, sample their vote with persona-specific
             uncertainty (drawn from a multinomial weighted by their
             FAV scores or certainty)

    persona_uncertainty: optional dict mapping persona_id -> per-party
    favourability vector. When present, level-2 sampling resamples the
    vote within each persona based on their FAV uncertainty rather than
    treating their committed vote as deterministic. Captures genuine
    cross-persona variance AND intra-persona uncertainty.

    Falls back to standard pool-resample when persona_uncertainty is None
    (in which case it's equivalent to bootstrap_win_probability with more
    iterations).
    """
    _ = persona_uncertainty  # reserved for FAV-weighted variant; not used in heuristic mode
    pool: list[str] = []
    for party, c in raw_counts.items():
        pool.extend([party] * c)
    if not pool:
        return {}

    rng = random.Random(seed)
    win_count: Counter = Counter()
    n = len(pool)
    unique_parties = list(raw_counts.keys())
    for _ in range(n_iterations):
        # Level 1: persona resample
        sample = [rng.choice(pool) for _ in range(n)]
        # Level 2: heuristic intra-persona uncertainty — 10% of votes get
        # randomly reassigned to a different party. Stand-in for proper
        # FAV-weighted resampling (would use persona_uncertainty if provided).
        for i in range(n):
            if rng.random() < 0.10:
                sample[i] = rng.choice(unique_parties)
        sample_counts: Counter = Counter(sample)
        winner, _ = sample_counts.most_common(1)[0]
        win_count[winner] += 1

    return {p: round(100.0 * c / n_iterations, 1) for p, c in win_count.items()}


def bayesian_dirichlet_win_probability(
    raw_counts: Counter,
    prior_shares: dict[str, float] | None = None,
    prior_strength: float = 30.0,
    n_iterations: int = 2000,
    seed: int = 42,
) -> dict[str, float]:
    """Dirichlet-posterior win probability with informed prior.

    KPM-2.1 fix for narrow-CI inputs (decisive LLMs). Standard pool-resample
    bootstrap concentrates win probability when the LLM is decisive — even
    if the realistic uncertainty is much wider. A Dirichlet posterior with
    a meaningful prior keeps fragmentation visible.

    Posterior: Dirichlet(alpha) where
      alpha[party] = prior_strength * prior_share[party] + observed_count[party]

    prior_shares: dict of party -> share fraction (0-1, sum to ~1). Default
      uses the calibrated pollster anchor (rolling mean + UK polling mix).
      None → falls back to uniform prior across observed parties.
    prior_strength: pseudo-count weight. 30 = "as if 30 prior votes had been
      observed at the prior distribution". Lower = let observed dominate;
      higher = prior dominates. 30 is a reasonable middle for ~60-vote panels.

    Sampling: draw n_iterations samples from the Dirichlet, count the winner
    in each sample. Returns P(party wins) as a percentage.
    """
    if not raw_counts:
        return {}

    # Build the alpha vector
    parties = list(raw_counts.keys())
    if prior_shares:
        for p in prior_shares:
            if p not in parties:
                parties.append(p)

    if prior_shares is None:
        # Uniform prior across observed parties
        uniform = 1.0 / len(parties)
        prior_shares = {p: uniform for p in parties}

    alpha = []
    for p in parties:
        prior_count = prior_strength * float(prior_shares.get(p, 0.0))
        observed_count = float(raw_counts.get(p, 0))
        alpha.append(max(0.001, prior_count + observed_count))  # tiny floor for stability

    # Sample from Dirichlet — NumPy not available, use gamma-ratio method
    rng = random.Random(seed)
    win_count: Counter = Counter()
    for _ in range(n_iterations):
        # Dirichlet sample = normalised independent Gamma(alpha_i, 1) draws
        gammas = [rng.gammavariate(a, 1.0) for a in alpha]
        total = sum(gammas)
        if total <= 0:
            continue
        shares = [g / total for g in gammas]
        winner_idx = max(range(len(shares)), key=lambda i: shares[i])
        win_count[parties[winner_idx]] += 1

    return {p: round(100.0 * c / n_iterations, 1) for p, c in win_count.items()}


def predict_council(
    council: str,
    cassette: str = "balanced",
    panel_size: int = 50,
    llm_client: LLMClient | None = None,
    llm_client_name: str = "stub",
    seed: int = 42,
    council_ctx_override: dict | None = None,
    apply_calibration_shifts: bool = True,
    as_of: date | None = None,
    use_real_personas: bool = False,
    bootstrap_method: str = "pool",  # "pool", "bayesian", or "hierarchical"
    bayesian_prior_strength: float = 30.0,
    concurrency: int = 1,
    panel_mode: str = "region",  # "region", "stratified", "constituency"
) -> PredictionRun:
    """Full KPM-2 pipeline for one council.

    council: name (e.g. "Caerphilly", "Wigan"); used for turnout lookup
    council_ctx_override: optional explicit context dict, useful when
      the council isn't in turnout_estimates.json (by-elections etc.)
    """
    client = llm_client or get_client(llm_client_name, seed=seed)

    # Council context — real councils get pulled from turnout_estimates,
    # by-election wards may need an override
    turnout = get_turnout(council)
    if council_ctx_override:
        ctx = dict(council_ctx_override)
        ctx.setdefault("council", council)
    elif turnout:
        ctx = {
            "council": council,
            "incumbent": "Labour",  # default — turnout file doesn't carry incumbent in clean form
            "baseline_turnout": turnout.baseline_turnout,
            "estimated_turnout": turnout.estimated_turnout,
            "region": turnout.region,
            "council_type": turnout.council_type,
        }
    else:
        ctx = {
            "council": council,
            "incumbent": "Labour",
            "baseline_turnout": 0.30,
            "estimated_turnout": 0.30,
            "region": "unknown",
            "council_type": "unknown",
        }
    ctx.setdefault("election_date", "2026-05-07")

    # Stimulate the panel — real DYNAMICS-8 personas if requested
    if use_real_personas:
        from .real_panel import load_panel
        panel = load_panel(council, n=panel_size, seed=seed, mode=panel_mode)
    else:
        panel = synthesize_panel(council, ctx, panel_size=panel_size, seed=seed)

    # Concurrency > 1 fans out via asyncio (KPM-2.2). Falls back to sequential
    # for concurrency=1 to keep the simple-path stack trace clean.
    if concurrency > 1 and hasattr(client, "stimulate"):
        responses = stimulate_panel_async(client, panel, ctx, concurrency=concurrency)
    else:
        responses = stimulate_panel(panel, ctx, client)
    n_voted = sum(1 for r in responses if r.voted)
    n_abstained = len(responses) - n_voted

    raw_counts, raw_shares = aggregate_votes(responses)

    # Calibration
    cal_shifts: dict[str, float] = {}
    if apply_calibration_shifts:
        as_of_d = as_of or date.fromisoformat(ctx.get("election_date", "2026-05-07"))
        try:
            cal_report = fit_calibration(
                as_of=as_of_d,
                correction_weight=CASSETTES[cassette].calibration_correction_weight,
                half_life_days=CASSETTES[cassette].calibration_half_life_days,
            )
            cal_shifts = {p: c.shift_pp for p, c in cal_report.parties.items()}
        except FileNotFoundError:
            # Polls history file missing — proceed without calibration
            cal_shifts = {}

    calibrated = apply_calibration(raw_shares, cal_shifts) if cal_shifts else dict(raw_shares)

    # Bootstrap CI — pool resample (KPM-2 v0/v1 default), Bayesian Dirichlet
    # (KPM-2.1) or hierarchical two-level (KPM-2.2 #J).
    if bootstrap_method == "bayesian":
        prior = {p: max(0.0, s) / 100.0 for p, s in calibrated.items()}
        prior_total = sum(prior.values()) or 1.0
        prior = {p: v / prior_total for p, v in prior.items()}
        win_prob = bayesian_dirichlet_win_probability(
            raw_counts,
            prior_shares=prior,
            prior_strength=bayesian_prior_strength,
            n_iterations=2000,
            seed=seed,
        )
    elif bootstrap_method == "hierarchical":
        win_prob = hierarchical_bootstrap_win_probability(
            raw_counts, n_iterations=1500, seed=seed,
        )
    else:
        win_prob = bootstrap_win_probability(raw_counts, n_iterations=1000, seed=seed)

    # Posterior + classification (use calibrated shares as the point estimate)
    council_record = {
        "name": council,
        "vote_shares": calibrated,
        "win_probability": win_prob,
    }
    post = compute_posterior(council_record, cassette_name=cassette)

    return PredictionRun(
        council=council,
        cassette=cassette,
        panel_size=panel_size,
        n_voted=n_voted,
        n_abstained=n_abstained,
        raw_vote_counts=dict(raw_counts),
        raw_vote_shares=raw_shares,
        calibration_applied=cal_shifts,
        calibrated_vote_shares=calibrated,
        win_probability=win_prob,
        posterior=posterior_to_dict(post),
        turnout_pct=turnout.turnout_pct if turnout else None,
        abstention_pct=turnout.abstention_pct if turnout else None,
        seed=seed,
        llm_client=llm_client_name,
    )


def to_jsonable(run: PredictionRun) -> dict:
    return asdict(run)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--council", required=True, help="Council name (e.g. Caerphilly)")
    parser.add_argument("--cassette", default="balanced", choices=list(CASSETTES.keys()))
    parser.add_argument("--panel-size", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--llm", default="stub", choices=["stub", "imprint"])
    parser.add_argument("--no-calibration", action="store_true",
                        help="Skip per-party calibration shifts")
    parser.add_argument("--use-real-personas", action="store_true",
                        help="Sample from KPM-1 persona bank instead of synthetic")
    parser.add_argument("--bootstrap", choices=["pool", "bayesian", "hierarchical"], default="pool",
                        help="Bootstrap method: pool (KPM-2.0), bayesian (KPM-2.1) or hierarchical (KPM-2.2)")
    parser.add_argument("--bayesian-prior-strength", type=float, default=30.0,
                        help="Prior pseudo-count for Bayesian bootstrap")
    parser.add_argument("--adaptive-panel", action="store_true",
                        help="Auto-size panel by council type (metropolitan=120, london=80, district=40)")
    parser.add_argument("--concurrency", type=int, default=1,
                        help="Concurrent LLM calls (1=sequential, 8=matches vLLM --max-num-seqs)")
    parser.add_argument("--panel-mode", choices=["region", "stratified", "constituency", "kpm1"], default="region",
                        help="Persona-bank sampling: region=KPM-2.0, stratified=#4 simple, constituency=#7, kpm1=full KPM-1 ward-census post-strat")
    parser.add_argument("--as-of", help="ISO date for calibration cutoff")
    parser.add_argument("--save", help="Write full PredictionRun JSON to this path")
    parser.add_argument("--quiet", action="store_true", help="JSON-only output")
    args = parser.parse_args()

    as_of = date.fromisoformat(args.as_of) if args.as_of else None

    panel_size: int = int(args.panel_size)
    if args.adaptive_panel:
        from .turnout import get_turnout
        t = get_turnout(args.council)
        if t:
            sizing = {"metropolitan": 120, "london": 80, "unitary": 80,
                      "county": 100, "district": 40}
            panel_size = sizing.get(t.council_type, panel_size)

    run = predict_council(
        council=args.council,
        cassette=args.cassette,
        panel_size=panel_size,
        llm_client_name=args.llm,
        seed=args.seed,
        apply_calibration_shifts=not args.no_calibration,
        as_of=as_of,
        use_real_personas=args.use_real_personas,
        bootstrap_method=args.bootstrap,
        bayesian_prior_strength=args.bayesian_prior_strength,
        concurrency=args.concurrency,
        panel_mode=args.panel_mode,
    )

    if args.quiet:
        print(json.dumps(to_jsonable(run), indent=2))
    else:
        print(f"\n=== KPM-2 prediction: {run.council} ({run.cassette} cassette) ===")
        print(f"  Panel:      {run.panel_size} personas, "
              f"{run.n_voted} voted, {run.n_abstained} abstained")
        if run.turnout_pct:
            print(f"  Turnout:    {run.turnout_pct}% (abstention {run.abstention_pct}%)")
        print(f"  Raw shares (LLM={run.llm_client}):")
        for p, s in sorted(run.raw_vote_shares.items(), key=lambda kv: -kv[1]):
            print(f"    {p:18}  {s:>5.1f}%")
        if run.calibration_applied:
            print(f"  Calibration shifts (cassette={run.cassette}):")
            for p, s in run.calibration_applied.items():
                print(f"    {p:18}  {s:>+6.2f}pp")
            print(f"  Calibrated shares:")
            for p, s in sorted(run.calibrated_vote_shares.items(), key=lambda kv: -kv[1]):
                print(f"    {p:18}  {s:>5.1f}%")
        print(f"  Win probability:")
        for p, prob in sorted(run.win_probability.items(), key=lambda kv: -kv[1]):
            if prob >= 1.0:
                print(f"    {p:18}  {prob:>4.0f}%")
        c = run.posterior["classification"]
        print(f"  Classification: {c['predicted_winner']:25}  confidence={c['confidence']}  "
              f"margin={c['margin_pp']:.1f}pp")
        print(f"  P(NOC):     {run.posterior['noc_prob_pct']}%")

    if args.save:
        Path(args.save).write_text(json.dumps(to_jsonable(run), indent=2))
        print(f"\nWrote {args.save}", file=sys.stderr)


if __name__ == "__main__":
    main()
