"""KPM-2 LLM client — pluggable stimulus interface.

KPM-2 keeps the LLM call behind a Protocol so the rest of the pipeline
can be exercised end-to-end with a deterministic stub. Real runs swap in
the Imprint client (Qwen3.5-27B via vLLM on DL580 GPU 3090).

Two implementations:
  - StubLLMClient: deterministic seeded mock for tests + offline backtests
  - ImprintLLMClient: HTTP POST to imprint-14b vLLM endpoint, chat-completions

The shape of the response is always: {"vote_party": "<canonical_name>"}
plus optional reasoning/favourability fields. Aggregation in predict.py
only requires vote_party.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol


PARTY_CANONICAL = [
    "Reform UK",
    "Labour",
    "Conservative",
    "Liberal Democrat",
    "Green",
    "Independent",
    "Other",
]


@dataclass(frozen=True)
class StimulusResponse:
    """One persona's response to the voting prompt.

    KPM-2.1 fields:
      favourability_max: highest 1-10 favourability across parties (None if not asked)
      certainty_1to5: persona's self-reported confidence in their vote (None if not asked)

    These power abstention modelling (low max favourability → won't bother)
    and uncertainty-weighted bootstrap (down-weight uncertain votes).
    """

    persona_id: str
    voted: bool                  # False = abstained
    vote_party: str | None       # None when voted=False
    raw_response: str = ""
    favourability_max: int | None = None
    certainty_1to5: int | None = None


class LLMClient(Protocol):
    """All KPM-2 LLM clients honour this single method.

    KPM-2.2 adds async support — clients implementing `stimulate_async` can
    be driven concurrently via asyncio.gather with a semaphore. The sync
    `stimulate` remains the primary interface for back-compat.
    """

    def stimulate(self, persona: dict, council_context: dict) -> StimulusResponse: ...


def stimulate_panel_async(
    client: "ImprintLLMClient",
    panel: list[dict],
    council_context: dict,
    concurrency: int = 8,
) -> list[StimulusResponse]:
    """Drive a panel concurrently via asyncio. Returns ordered responses.

    Concurrency = 8 matches vLLM's default --max-num-seqs. Each persona's
    LLM call goes through aiohttp + asyncio.Semaphore. 8x throughput for
    sequential workloads.

    Implementation note: we run a fresh event loop per call. Caller never
    sees coroutines — this is a sync wrapper around async fan-out.
    """
    return asyncio.run(_stimulate_panel_async_impl(client, panel, council_context, concurrency))


async def _stimulate_panel_async_impl(
    client: "ImprintLLMClient",
    panel: list[dict],
    council_context: dict,
    concurrency: int,
) -> list[StimulusResponse]:
    sem = asyncio.Semaphore(concurrency)

    async def one(persona: dict) -> StimulusResponse:
        async with sem:
            # Run the sync stimulus in a thread so urllib doesn't block the loop
            return await asyncio.to_thread(client.stimulate, persona, council_context)

    return await asyncio.gather(*[one(p) for p in panel])


class StubLLMClient:
    """Deterministic stub — for tests and offline pipeline validation.

    Voting decision is hashed from (persona_id, council, seed) so the same
    persona produces the same vote each run. Distribution is biased by the
    council's incumbent to roughly mirror baseline expectation, then the
    full pipeline (calibration, classifier, posterior) gets to act on a
    realistic-ish raw signal.
    """

    def __init__(self, seed: int = 42, abstention_rate: float = 0.30) -> None:
        self.seed = seed
        self.abstention_rate = abstention_rate

    def _hash_to_unit(self, *parts: str) -> float:
        """Stable [0, 1) float from any string parts."""
        joined = "|".join(parts) + f"|{self.seed}"
        h = hashlib.sha256(joined.encode("utf-8")).digest()
        return int.from_bytes(h[:8], "big") / (1 << 64)

    def stimulate(self, persona: dict, council_context: dict) -> StimulusResponse:
        pid = str(persona.get("id", ""))
        council = str(council_context.get("council", ""))

        # Abstention check — gated by persona's turnout probability when
        # provided; falls back to the configured abstention rate.
        turnout_prob = float(persona.get("turnout_probability", 1.0 - self.abstention_rate))
        if self._hash_to_unit(pid, council, "turnout") > turnout_prob:
            return StimulusResponse(persona_id=pid, voted=False, vote_party=None)

        # Bias towards incumbent at a council-level base rate, with the
        # remaining mass split across other parties weighted by a baseline
        # prior the council provides (or even split if absent).
        incumbent = str(council_context.get("incumbent", "Labour"))
        base_priors = council_context.get("party_priors", {})
        if not base_priors:
            base_priors = {p: 1.0 / len(PARTY_CANONICAL) for p in PARTY_CANONICAL}

        # Weight incumbent up by 1.5x then normalise
        weighted = {p: w for p, w in base_priors.items()}
        weighted[incumbent] = weighted.get(incumbent, 0.0) * 1.5 + 0.05
        total = sum(weighted.values())
        if total <= 0:
            weighted = {p: 1.0 / len(PARTY_CANONICAL) for p in PARTY_CANONICAL}
            total = 1.0

        # Cumulative draw
        u = self._hash_to_unit(pid, council, "vote")
        acc = 0.0
        for party, w in weighted.items():
            acc += w / total
            if u <= acc:
                return StimulusResponse(persona_id=pid, voted=True, vote_party=party)
        # Fallback (numerical drift): last party
        last = next(reversed(weighted))
        return StimulusResponse(persona_id=pid, voted=True, vote_party=last)


class ImprintLLMClient:
    """vLLM Imprint client (Qwen3.5-27B). DL580:18000 default.

    Real production stimulus. Honours the chat_template_kwargs trick to
    suppress thinking tags. Defensive: if the endpoint is unreachable or
    the response is unparseable, falls back to abstention rather than
    fabricating votes.

    Two prompt modes (KPM-2.1):
      - "single" (KPM-2.0 default): one shot, vote OR abstain
      - "two_stage" (KPM-2.1 default): favourability per major party 1-10
        + certainty 1-5 + vote. Captures intensity, drives uncertainty-
        weighted bootstrap, lets low-favourability personas correctly
        abstain rather than reinforce incumbent inertia.
    """

    def __init__(
        self,
        url: str = "http://localhost:18000/v1/chat/completions",
        model: str = "imprint-9b",
        timeout_s: float = 30.0,
        prompt_mode: str = "two_stage",
    ) -> None:
        self.url = url
        self.model = model
        self.timeout_s = timeout_s
        self.prompt_mode = prompt_mode

    def stimulate(self, persona: dict, council_context: dict) -> StimulusResponse:
        pid = str(persona.get("id", ""))
        if self.prompt_mode == "two_stage":
            prompt = self._build_prompt_two_stage(persona, council_context)
            max_tokens = 450  # extra budget for REASON line (CoT)
        else:
            prompt = self._build_prompt(persona, council_context)
            max_tokens = 200

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.45 if self.prompt_mode == "two_stage" else 0.35,
            "max_tokens": max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
        }

        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
            return StimulusResponse(persona_id=pid, voted=False, vote_party=None)

        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return StimulusResponse(persona_id=pid, voted=False, vote_party=None)

        if self.prompt_mode == "two_stage":
            return self._parse_two_stage(pid, text)
        party = self._parse_vote(text)
        if party is None:
            return StimulusResponse(persona_id=pid, voted=False, vote_party=None, raw_response=text[:300])
        return StimulusResponse(persona_id=pid, voted=True, vote_party=party, raw_response=text[:300])

    def _build_prompt(self, persona: dict, council_context: dict) -> str:
        """Voting prompt with realistic persona dimensions.

        Argyle et al. (2023) "silicon sampling" approach: give the LLM
        enough demographic + prior-vote signal to reason about whether
        this voter switches party in this election.

        Prompt framing avoids priming any one party — all six options
        get equal billing in the choice list, and the persona's prior
        vote + main issue + party affiliation are the primary signal
        the LLM should reason from.
        """
        prior = persona.get("voted_2024_ge", "Did not vote")
        age = persona.get("age_band", "unknown")
        klass = persona.get("social_class", "unknown")
        issue = persona.get("main_issue_2026", "unknown")
        engagement = persona.get("political_engagement_1to5", 3)
        region = persona.get("region", "England")
        homeowner = "homeowner" if persona.get("homeowner") else "renter"
        occupation = persona.get("occupation", "")
        affiliation = persona.get("party_affiliation", "")
        incumbent = council_context.get("incumbent", "Labour")
        council = council_context.get("council", "this council")

        affil_line = f"  Party you most identify with: {affiliation}\n" if affiliation and affiliation != "Unknown" else ""
        occ_line = f"  Occupation: {occupation}\n" if occupation else ""

        return (
            f"You are a UK voter in the {council_context.get('election_date', '7 May 2026')} "
            f"local council election. Your council: {council} ({region}). "
            f"Currently controlled by: {incumbent}.\n\n"
            f"Your profile:\n"
            f"  Age band: {age}\n"
            f"  Social class: {klass}\n"
            f"{occ_line}"
            f"  Tenure: {homeowner}\n"
            f"  Political engagement (1-5): {engagement}\n"
            f"{affil_line}"
            f"  Voted in 2024 General Election: {prior}\n"
            f"  Top issue right now: {issue}\n\n"
            f"How will you vote? Be true to the profile — do not assume everyone votes the "
            f"same way. Consider switching parties only if your top issue or recent "
            f"political shifts give you reason to.\n\n"
            f"Reply with ONE option from this list (choose the one that best fits this profile):\n"
            f"  - Labour\n  - Conservative\n  - Reform UK\n  - Liberal Democrat\n"
            f"  - Green\n  - Independent\n  - Other\n  - ABSTAIN (won't vote)\n"
        )

    def _parse_vote(self, text: str) -> str | None:
        cleaned = text.strip().splitlines()[0].strip().rstrip(".")
        upper = cleaned.upper()
        if "ABSTAIN" in upper or "WILL NOT VOTE" in upper:
            return None
        for party in PARTY_CANONICAL:
            if party.lower() in cleaned.lower():
                return party
        return None

    def _build_prompt_two_stage(self, persona: dict, council_context: dict) -> str:
        """KPM-2.2 two-stage prompt with DYNAMICS-8 + CoT + few-shot.

        Combines:
          - Two-stage favourability + vote (KPM-2.1 #2)
          - DYNAMICS-8 personality vector (KPM-2.2 #D)
          - Brief CoT reasoning prelude (KPM-2.2 #F)
          - 2 inline voter examples (KPM-2.2 #E)
        """
        prior = persona.get("voted_2024_ge", "Did not vote")
        age = persona.get("age_band", "unknown")
        klass = persona.get("social_class", "unknown")
        issue = persona.get("main_issue_2026", "unknown")
        engagement = persona.get("political_engagement_1to5", 3)
        region = persona.get("region", "England")
        homeowner = "homeowner" if persona.get("homeowner") else "renter"
        occupation = persona.get("occupation", "")
        affiliation = persona.get("party_affiliation", "")
        ethnicity = persona.get("ethnicity", "")
        incumbent = council_context.get("incumbent", "Labour")
        council = council_context.get("council", "this council")

        affil_line = f"  Party you most identify with: {affiliation}\n" if affiliation and affiliation != "Unknown" else ""
        occ_line = f"  Occupation: {occupation}\n" if occupation else ""
        eth_line = f"  Ethnicity: {ethnicity}\n" if ethnicity else ""

        # DYNAMICS-8 (KPM-2.2 #D) — the persona's full personality vector
        dyn = persona.get("_dynamics_8", {})
        dyn_block = ""
        if dyn:
            dyn_block = (
                "  DYNAMICS-8 personality (each 0-1; higher = more of trait):\n"
                f"    D=Discipline {dyn.get('D', 0.5):.2f}  Y=Youthfulness {dyn.get('Y', 0.5):.2f}  "
                f"N=Neuroticism {dyn.get('N', 0.5):.2f}  A=Agreeableness {dyn.get('A', 0.5):.2f}\n"
                f"    M=Mercuriality {dyn.get('M', 0.5):.2f}  I=Idealism {dyn.get('I', 0.5):.2f}  "
                f"C=Curiosity {dyn.get('C', 0.5):.2f}  S=Sociability {dyn.get('S', 0.5):.2f}\n"
                "    (High N = anxious about change. High M = swing voter. "
                "High I = vote on principle. High D = unlikely to abstain.)\n"
            )

        # Few-shot examples (KPM-2.2 #E) — three balanced examples covering
        # switch / stay / abstain. Earlier two-example version (Lab->Reform +
        # LD->LD) over-anchored on switching; this triplet shows the LLM
        # that staying with party affiliation is also a valid outcome.
        examples = (
            "EXAMPLE 1 (switcher): 45yo C2 Lab-2024 voter in NE England, top issue "
            "Cost of living, high N (anxiety) + low D (low discipline). Reasoning: "
            "disillusioned with Lab government, anxious about change, drifts to Reform.\n"
            "FAV_LAB: 4 / FAV_REF: 8 / FAV_CON: 3 / FAV_LD: 4 / FAV_GRN: 3 / CERTAIN: 3 / "
            "VOTE: Reform UK\n\n"
            "EXAMPLE 2 (stayer): 52yo C1 Lab-2024 voter in West Midlands, top issue NHS, "
            "high A (agreeableness) + medium D + low M (low mercuriality). Reasoning: "
            "loyal to party, NHS aligned with Lab values, doesn't switch under pressure.\n"
            "FAV_LAB: 7 / FAV_REF: 3 / FAV_CON: 2 / FAV_LD: 4 / FAV_GRN: 4 / CERTAIN: 4 / "
            "VOTE: Labour\n\n"
            "EXAMPLE 3 (idealist): 28yo AB LD-2024 voter in South East, top issue "
            "Environment, high I (idealism) + high C (curiosity). Reasoning: "
            "ideologically aligned LD/Green, would never vote Reform.\n"
            "FAV_LAB: 5 / FAV_REF: 1 / FAV_CON: 2 / FAV_LD: 8 / FAV_GRN: 7 / CERTAIN: 4 / "
            "VOTE: Liberal Democrat\n\n"
        )

        return (
            f"You are a UK voter in the {council_context.get('election_date', '7 May 2026')} "
            f"local council election. Council: {council} ({region}). "
            f"Currently controlled by: {incumbent}.\n\n"
            f"Your profile:\n"
            f"  Age band: {age}\n"
            f"  Social class: {klass}\n"
            f"{occ_line}"
            f"{eth_line}"
            f"  Tenure: {homeowner}\n"
            f"  Political engagement (1-5): {engagement}\n"
            f"{affil_line}"
            f"  Voted in 2024 General Election: {prior}\n"
            f"  Top issue right now: {issue}\n"
            f"{dyn_block}\n"
            f"Reference examples of how UK voters reason in 2026:\n"
            f"{examples}"
            f"Now reason about YOUR vote, then answer in EXACTLY this format:\n\n"
            f"REASON: <one sentence — what's the dominant pull for THIS profile?>\n"
            f"FAV_LAB: <1-10>\n"
            f"FAV_CON: <1-10>\n"
            f"FAV_REF: <1-10>\n"
            f"FAV_LD: <1-10>\n"
            f"FAV_GRN: <1-10>\n"
            f"CERTAIN: <1-5>\n"
            f"VOTE: <one of: Labour, Conservative, Reform UK, Liberal Democrat, "
            f"Green, Independent, Other, ABSTAIN>\n\n"
            f"Rules:\n"
            f"- Vote according to YOUR profile, not the incumbent. Many voters switch.\n"
            f"- High N (anxiety) leans toward Reform on cost-of-living, NHS, immigration.\n"
            f"- High I (idealism) leans Green or LD on environment, fairness.\n"
            f"- High M (mercuriality) — you ARE the swing voter, decide by issue not loyalty.\n"
            f"- If highest FAV across parties is below 4, VOTE: ABSTAIN.\n"
        )

    def _parse_two_stage(self, pid: str, text: str) -> StimulusResponse:
        """Extract REASON, FAV_*, CERTAIN, VOTE fields from a two-stage response.

        REASON: optional CoT prelude (KPM-2.2). Captured into raw_response
        for trace publication (#O); not used for vote decision.
        """
        favs: dict[str, int] = {}
        certainty: int | None = None
        vote: str | None = None

        fav_keys = {"FAV_LAB": 10, "FAV_CON": 10, "FAV_REF": 10, "FAV_LD": 10, "FAV_GRN": 10}
        for line in text.splitlines():
            line = line.strip()
            for k in fav_keys:
                if line.upper().startswith(k):
                    m = re.search(r"(\d+)", line)
                    if m:
                        favs[k] = max(1, min(10, int(m.group(1))))
                    break
            if line.upper().startswith("CERTAIN"):
                m = re.search(r"(\d+)", line)
                if m:
                    certainty = max(1, min(5, int(m.group(1))))
            if line.upper().startswith("VOTE"):
                value = line.split(":", 1)[-1].strip().rstrip(".")
                vote = value

        fav_max = max(favs.values()) if favs else None

        if vote is None:
            return StimulusResponse(persona_id=pid, voted=False, vote_party=None,
                                    raw_response=text[:400], favourability_max=fav_max,
                                    certainty_1to5=certainty)

        upper_vote = vote.upper()
        if "ABSTAIN" in upper_vote or "WILL NOT VOTE" in upper_vote or "DID NOT" in upper_vote:
            return StimulusResponse(persona_id=pid, voted=False, vote_party=None,
                                    raw_response=text[:400], favourability_max=fav_max,
                                    certainty_1to5=certainty)

        party = None
        for p in PARTY_CANONICAL:
            if p.lower() in vote.lower():
                party = p
                break

        # Honour the abstention rule even if the LLM didn't comply
        if fav_max is not None and fav_max < 4:
            return StimulusResponse(persona_id=pid, voted=False, vote_party=None,
                                    raw_response=text[:400], favourability_max=fav_max,
                                    certainty_1to5=certainty)

        if party is None:
            return StimulusResponse(persona_id=pid, voted=False, vote_party=None,
                                    raw_response=text[:400], favourability_max=fav_max,
                                    certainty_1to5=certainty)

        return StimulusResponse(persona_id=pid, voted=True, vote_party=party,
                                raw_response=text[:400], favourability_max=fav_max,
                                certainty_1to5=certainty)


def get_client(name: str = "stub", **kwargs) -> LLMClient:
    """Factory — use by name from CLI. Silently drops kwargs the
    target client doesn't accept (e.g. `seed` only applies to stub)."""
    if name == "stub":
        accepted = {k: v for k, v in kwargs.items() if k in {"seed", "abstention_rate"}}
        return StubLLMClient(**accepted)
    if name == "imprint":
        accepted = {k: v for k, v in kwargs.items() if k in {"url", "model", "timeout_s", "prompt_mode"}}
        return ImprintLLMClient(**accepted)
    raise ValueError(f"Unknown LLM client: {name}")
