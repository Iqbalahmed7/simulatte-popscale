"""PopulationResponse — wraps Persona Generator DecisionOutput for population analysis.

Every agent that processes a PopScale Scenario produces a PopulationResponse.
It is a thin adapter around the Persona Generator's DecisionOutput, adding:
  - Persona identity (id, name, demographic snapshot)
  - Scenario reference (domain, options used)
  - Domain signals (extracted from decision reasoning, domain-specific)
  - Aggregation helpers (numeric confidence 0-1, valence estimate)

Design principles:
  - No re-parsing of LLM output — DecisionOutput is already validated
  - Confidence normalised to 0.0-1.0 (DecisionOutput uses 0-100 int)
  - Domain signals are lightweight proxies, not additional LLM calls
  - All fields must be computable without a second LLM call
"""

from __future__ import annotations

import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Optional

# ── Persona Generator import ───────────────────────────────────────────────
# PG root in sys.path → PG modules importable as `src.X` (PG's convention).
_PG_ROOT = Path(__file__).parents[3] / "Persona Generator"
if str(_PG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PG_ROOT))

from src.cognition.decide import DecisionOutput  # noqa: E402  (PG)
from src.schema.persona import PersonaRecord     # noqa: E402  (PG)

from ..scenario.model import SimulationDomain    # noqa: E402


# ── Domain signals ─────────────────────────────────────────────────────────
# Lightweight numeric proxies derived from PersonaRecord attributes.
# These are used for domain-specific segmentation in the analytics layer.
# They are deterministic (from the persona vector, not from LLM output)
# so they never require additional API calls.

@dataclass
class DomainSignals:
    """Domain-specific signals derived from PersonaRecord attributes.

    These are NOT LLM-generated — they are computed from the persona's
    behavioral profile so they are always available, even if decide() fails.

    Consumer signals:   price_sensitivity, brand_affinity, trial_likelihood
    Policy signals:     trust_in_institutions, implementation_concern
    Political signals:  turnout_likelihood, issue_salience
    """
    # Shared (always present)
    openness_score: float = 0.5        # Prior openness estimate (0-1)

    # Consumer-specific
    price_sensitivity: Optional[float] = None
    brand_affinity: Optional[float] = None
    trial_likelihood: Optional[float] = None

    # Policy-specific
    trust_in_institutions: Optional[float] = None
    implementation_concern: Optional[float] = None
    compliance_likelihood: Optional[float] = None

    # Political-specific
    turnout_likelihood: Optional[float] = None
    issue_salience: Optional[float] = None
    persuadability: Optional[float] = None


def _extract_domain_signals(
    persona: PersonaRecord, domain: SimulationDomain
) -> DomainSignals:
    """Derive domain signals from PersonaRecord attributes.

    All values are 0-1. Derived from validated persona fields —
    no LLM call, no additional latency.
    """
    di = persona.derived_insights
    bt = persona.behavioural_tendencies

    # Openness: risk_appetite + (inverse of) decision_style conservatism
    risk_map = {"low": 0.2, "medium": 0.5, "high": 0.8}
    openness = risk_map.get(di.risk_appetite, 0.5)

    if domain == SimulationDomain.CONSUMER:
        price_sens_map = {"low": 0.2, "medium": 0.5, "high": 0.8, "extreme": 0.95}
        price_sensitivity = price_sens_map.get(bt.price_sensitivity.band, 0.5)
        switch_map = {"low": 0.15, "medium": 0.5, "high": 0.85}
        trial_likelihood = switch_map.get(bt.switching_propensity.band, 0.5)
        # Brand affinity: inverse of price sensitivity + switching propensity
        brand_affinity = round(1.0 - (price_sensitivity * 0.5 + trial_likelihood * 0.5), 2)
        return DomainSignals(
            openness_score=openness,
            price_sensitivity=round(price_sensitivity, 2),
            brand_affinity=brand_affinity,
            trial_likelihood=round(trial_likelihood, 2),
        )

    elif domain == SimulationDomain.POLICY:
        trust_map = {"authority": 0.8, "self": 0.6, "peer": 0.45, "family": 0.35}
        trust_in_institutions = trust_map.get(di.trust_anchor, 0.5)
        # Implementation concern: inverse of risk appetite
        impl_concern = 1.0 - openness
        compliance = round((trust_in_institutions * 0.5 + openness * 0.5), 2)
        return DomainSignals(
            openness_score=openness,
            trust_in_institutions=round(trust_in_institutions, 2),
            implementation_concern=round(impl_concern, 2),
            compliance_likelihood=compliance,
        )

    elif domain == SimulationDomain.POLITICAL:
        # Turnout: high openness + habitual decision style → higher turnout
        style_boost = {"habitual": 0.15, "social": 0.1, "analytical": 0.05, "emotional": 0.0}
        turnout = min(1.0, openness + style_boost.get(di.decision_style, 0.0))
        # Persuadability: medium openness → most persuadable; extremes → anchored
        persuadability = 1.0 - abs(openness - 0.5) * 2
        return DomainSignals(
            openness_score=openness,
            turnout_likelihood=round(turnout, 2),
            issue_salience=round(openness, 2),
            persuadability=round(persuadability, 2),
        )

    return DomainSignals(openness_score=openness)


# ── Core response schema ───────────────────────────────────────────────────

@dataclass
class PopulationResponse:
    """Structured response from a single persona to a PopScale Scenario.

    Wraps the Persona Generator's DecisionOutput with persona identity,
    domain signals, and aggregation-friendly fields.

    Produced by: integration.run_scenario.run_scenario()
    Consumed by: analytics.segmentation, analytics.distributions, analytics.drivers
    """

    # ── Identity ──────────────────────────────────────────────────────────
    persona_id: str
    persona_name: str
    age: int
    gender: str
    location_city: str
    location_country: str
    income_bracket: str

    # ── Scenario reference ────────────────────────────────────────────────
    scenario_domain: str        # SimulationDomain.value
    scenario_options: list[str]

    # ── Decision (from DecisionOutput) ───────────────────────────────────
    decision: str               # The actual decision made
    confidence: float           # Normalised 0.0-1.0 (DecisionOutput uses 0-100)
    reasoning_trace: str        # Full 5-step reasoning from decide()
    gut_reaction: str           # Step 1 — immediate emotional response
    key_drivers: list[str]      # Top 2-3 factors that drove the decision
    objections: list[str]       # Hesitations / blockers raised
    what_would_change_mind: str
    follow_up_action: str       # What the persona does immediately after deciding

    # ── Derived sentiment ────────────────────────────────────────────────
    emotional_valence: float    # -1.0 (strongly negative) to +1.0 (strongly positive)
    # Computed from: confidence × (positive/negative decision direction)
    # Populated by _estimate_valence()

    # ── Domain signals ────────────────────────────────────────────────────
    domain_signals: DomainSignals

    # ── Derived insights snapshot (for driver analysis) ────────────────────
    risk_appetite: str          # "low" | "medium" | "high"
    trust_anchor: str           # "self" | "peer" | "authority" | "family"
    decision_style: str         # "emotional" | "analytical" | "habitual" | "social"
    primary_value_orientation: str
    consistency_score: int      # 0-100 from PersonaRecord
    price_sensitivity_band: str # "low" | "medium" | "high" | "extreme"
    switching_propensity_band: str

    # ── Metadata ──────────────────────────────────────────────────────────
    model_used: Optional[str] = field(default=None)
    run_id: Optional[str] = field(default=None)


def from_decision_output(
    decision: DecisionOutput,
    persona: PersonaRecord,
    domain: SimulationDomain,
    scenario_options: list[str],
    model_used: Optional[str] = None,
    run_id: Optional[str] = None,
) -> PopulationResponse:
    """Construct a PopulationResponse from Persona Generator outputs.

    This is the primary factory — called once per persona per scenario.
    """
    anchor = persona.demographic_anchor
    di = persona.derived_insights
    bt = persona.behavioural_tendencies

    # Normalise confidence from 0-100 int to 0.0-1.0 float
    confidence_01 = max(0.0, min(1.0, decision.confidence / 100.0))

    # Estimate emotional valence from decision text + gut reaction
    valence = _estimate_valence(decision, confidence_01)

    domain_signals = _extract_domain_signals(persona, domain)

    return PopulationResponse(
        persona_id=persona.persona_id,
        persona_name=anchor.name,
        age=anchor.age,
        gender=anchor.gender,
        location_city=anchor.location.city,
        location_country=anchor.location.country,
        income_bracket=anchor.household.income_bracket,
        scenario_domain=domain.value,
        scenario_options=scenario_options,
        decision=decision.decision,
        confidence=confidence_01,
        reasoning_trace=decision.reasoning_trace,
        gut_reaction=decision.gut_reaction,
        key_drivers=decision.key_drivers,
        objections=decision.objections,
        what_would_change_mind=decision.what_would_change_mind,
        follow_up_action=decision.follow_up_action,
        emotional_valence=valence,
        domain_signals=domain_signals,
        risk_appetite=di.risk_appetite,
        trust_anchor=di.trust_anchor,
        decision_style=di.decision_style,
        primary_value_orientation=di.primary_value_orientation,
        consistency_score=di.consistency_score,
        price_sensitivity_band=bt.price_sensitivity.band,
        switching_propensity_band=bt.switching_propensity.band,
        model_used=model_used,
        run_id=run_id,
    )


def _estimate_valence(decision: DecisionOutput, confidence: float) -> float:
    """Estimate emotional valence (-1 to +1) from decision text and gut reaction.

    Positive valence: decision includes positive words and high confidence
    Negative valence: objections outweigh key_drivers, or negative gut reaction

    This is a lightweight heuristic — no LLM call. The Persona Generator's
    perceive() already captures emotional_valence on observations; this
    is a population-level proxy derived from the decide() output.
    """
    positive_signals = {
        "yes", "support", "agree", "launch", "proceed", "approve", "positive",
        "forward", "buy", "purchase", "trial", "adopt", "implement", "yes,",
    }
    negative_signals = {
        "no", "oppose", "disagree", "reject", "decline", "resist", "against",
        "don't", "not", "never", "cancel", "stop", "block", "avoid",
    }

    text = (decision.decision + " " + decision.gut_reaction).lower()
    pos_count = sum(1 for w in positive_signals if w in text)
    neg_count = sum(1 for w in negative_signals if w in text)

    # Objections drag valence down
    objection_drag = len(decision.objections) * 0.05

    if pos_count > neg_count:
        raw = confidence * 0.6 + 0.4 - objection_drag
    elif neg_count > pos_count:
        raw = -(confidence * 0.6 + 0.4) + objection_drag
    else:
        raw = (confidence - 0.5) * 0.5 - objection_drag

    return round(max(-1.0, min(1.0, raw)), 2)
