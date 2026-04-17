"""Scenario — the structured multi-domain input to any PopScale simulation.

A Scenario replaces the plain string stimulus with a domain-aware model that
knows the question, context, discrete options, environment conditions, and
target domain. The domain controls how the Persona Generator's PersonaRecord
attributes are framed when generating the decision prompt.

PopScale Scenario → renderer → plain str stimulus → Persona Generator run_loop()

Design principle: keep the Scenario thin. It carries the *question* and
*context*, not the analysis. All interpretation belongs to the agents.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class SimulationDomain(str, Enum):
    """The decision domain — controls agent behavioral framing.

    The same PersonaRecord attributes mean different things in different
    domains. A high risk_appetite is "willingness to try new things" in
    a consumer context and "tolerance for implementation risk" in policy.
    """
    CONSUMER  = "consumer"   # Brand, product, pricing, market decisions
    POLICY    = "policy"     # Government, regulation, public communications
    POLITICAL = "political"  # Elections, campaigns, voter sentiment


# Known environment keys and their display labels (for render and validation)
_ENV_LABELS: dict[str, str] = {
    "market_conditions":     "Market conditions",
    "competitive_intensity": "Competition",
    "region":                "Region",
    "regulatory_climate":    "Regulatory climate",
    "cultural_context":      "Cultural context",
    "economic_sentiment":    "Economic sentiment",
    "media_landscape":       "Media landscape",
    "public_trust_level":    "Public trust level",
}


class Scenario(BaseModel):
    """A simulation scenario — the stimulus all agents in a population respond to.

    Example (Consumer):
        Scenario(
            question="Should we launch a men's skincare line at 2× our women's price?",
            context=(
                "Our brand is known for natural ingredients, 80% female customers aged 25-40. "
                "Men's premium skincare is growing 18% YoY. We have no male brand equity today."
            ),
            options=["Launch at 2× price", "Launch at parity price", "Do not launch"],
            domain=SimulationDomain.CONSUMER,
            environment={"market_conditions": "premium_growth", "region": "India"},
        )

    Example (Policy):
        Scenario(
            question="How should we sequence the rollout of the new data privacy regulation?",
            context="Parliament has passed the Digital Data Protection Act...",
            options=["Immediate national rollout", "Phased state rollout", "Sector-by-sector"],
            domain=SimulationDomain.POLICY,
        )
    """

    question: str = Field(
        ...,
        min_length=10,
        description="The core decision question the population is evaluating.",
    )

    context: str = Field(
        ...,
        min_length=20,
        description=(
            "Background information agents use to interpret the question. "
            "Aim for 50-300 words — enough to be substantive, not so much that "
            "agents anchor on context rather than their own beliefs."
        ),
    )

    options: list[str] = Field(
        default_factory=list,
        description=(
            "Discrete options agents choose between. Leave empty for open-ended "
            "sentiment/reaction scenarios. Provide 2-5 options for choice scenarios."
        ),
    )

    domain: SimulationDomain = Field(
        default=SimulationDomain.CONSUMER,
        description="The decision domain — controls agent behavioral framing.",
    )

    environment: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Ambient environmental context that shifts agent perception globally. "
            "Recognised keys: market_conditions, competitive_intensity, region, "
            "regulatory_climate, cultural_context, economic_sentiment, "
            "media_landscape, public_trust_level. "
            "All are optional. Unknown keys are allowed and forwarded as-is."
        ),
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Caller-defined metadata (e.g. client_id, study_id, wave).",
    )

    @field_validator("options")
    @classmethod
    def validate_options(cls, v: list[str]) -> list[str]:
        if len(v) == 1:
            raise ValueError(
                "Provide 0 options (open-ended scenario) or 2-6 options (choice scenario). "
                "A single option is not valid."
            )
        if len(v) > 6:
            raise ValueError(
                "Scenarios support at most 6 options. "
                "Split into sub-scenarios if you need more."
            )
        return [opt.strip() for opt in v if opt.strip()]

    def is_choice_scenario(self) -> bool:
        """True if agents choose between discrete options; False if open-ended."""
        return len(self.options) >= 2

    def environment_summary(self) -> str:
        """Render environment as a compact string for prompt injection."""
        if not self.environment:
            return "No specific environmental context provided."
        parts: list[str] = []
        for key, label in _ENV_LABELS.items():
            if key in self.environment:
                parts.append(f"{label}: {self.environment[key]}")
        for key, val in self.environment.items():
            if key not in _ENV_LABELS:
                parts.append(f"{key.replace('_', ' ').title()}: {val}")
        return " | ".join(parts)

    def options_formatted(self) -> str:
        """Render options as a numbered list."""
        if not self.options:
            return "(Open-ended — agents form their own position)"
        return "\n".join(f"  {i+1}. {opt}" for i, opt in enumerate(self.options))


class ScenarioBundle(BaseModel):
    """A collection of related scenarios for multi-scenario batch runs.

    Useful for A/B testing scenario variants, or running multiple
    sub-questions from the same broader research question.
    """

    name: str = Field(
        ...,
        description="Bundle name (e.g. 'Brand Architecture Study Q2 2026')",
    )
    scenarios: list[Scenario] = Field(..., min_length=1)
    shared_context: Optional[str] = Field(
        None,
        description=(
            "Context shared across all scenarios. Prepended to each scenario's "
            "own context. Use for study-level background that doesn't change."
        ),
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("scenarios")
    @classmethod
    def validate_scenarios(cls, v: list[Scenario]) -> list[Scenario]:
        if len(v) > 20:
            raise ValueError(
                "Bundles support at most 20 scenarios. Split into multiple bundles."
            )
        return v
