"""Scenario renderer — converts a PopScale Scenario into Persona Generator inputs.

The Persona Generator's cognitive loop takes two plain strings:
  - stimulus: str         → fed into perceive()
  - decision_scenario: str → fed into decide() when a decision is requested

This module renders those two strings from a structured PopScale Scenario,
with domain-aware language so consumer scenarios use market vocabulary,
policy scenarios use institutional vocabulary, and so on.

The renderer is deterministic: the same Scenario always produces the same
stimulus text — no LLM calls, no randomness.
"""

from __future__ import annotations

from .model import Scenario, SimulationDomain

# ── Domain vocabulary ──────────────────────────────────────────────────────

_DOMAIN_HEADERS = {
    SimulationDomain.CONSUMER:  "CONSUMER MARKET SCENARIO",
    SimulationDomain.POLICY:    "POLICY SCENARIO",
    SimulationDomain.POLITICAL: "POLITICAL SCENARIO",
}

_DOMAIN_CONTEXT_LABELS = {
    SimulationDomain.CONSUMER:  "Market context",
    SimulationDomain.POLICY:    "Policy context",
    SimulationDomain.POLITICAL: "Political context",
}

_DOMAIN_DECISION_INTROS = {
    SimulationDomain.CONSUMER: (
        "As a consumer, you are being asked to make a decision about the following:"
    ),
    SimulationDomain.POLICY: (
        "As a citizen, you are being asked to evaluate the following policy question:"
    ),
    SimulationDomain.POLITICAL: (
        "As a voter, you are being asked to consider the following political question:"
    ),
}

_OPEN_ENDED_PROMPTS = {
    SimulationDomain.CONSUMER:  "What is your reaction to this as a consumer?",
    SimulationDomain.POLICY:    "What is your reaction to this as a citizen?",
    SimulationDomain.POLITICAL: "What is your reaction to this as a voter?",
}


def render_stimulus(scenario: Scenario) -> str:
    """Render a Scenario as the plain string stimulus for perceive().

    This is what the persona first 'encounters' — it should read like
    a natural information encounter relevant to the domain (a news item,
    a product announcement, a policy briefing, a campaign message).

    The stimulus is intentionally shorter than the decision scenario —
    perceive() builds an initial impression; decide() gets the full framing.
    """
    domain = scenario.domain
    header = _DOMAIN_HEADERS[domain]
    context_label = _DOMAIN_CONTEXT_LABELS[domain]

    parts = [
        f"[{header}]",
        "",
        scenario.question,
        "",
        f"{context_label}: {scenario.context}",
    ]

    env = scenario.environment_summary()
    if env != "No specific environmental context provided.":
        parts += ["", f"Environment: {env}"]

    return "\n".join(parts)


def render_decision_scenario(scenario: Scenario) -> str:
    """Render a Scenario as the decision_scenario string for decide().

    This is the full framing the persona sees when making their decision.
    It includes the options (if any), domain framing, and environment.
    The decide() prompt wraps this in the persona's memory context.
    """
    domain = scenario.domain
    intro = _DOMAIN_DECISION_INTROS[domain]

    parts = [intro, "", scenario.question, "", scenario.context]

    env = scenario.environment_summary()
    if env != "No specific environmental context provided.":
        parts += ["", f"Context: {env}"]

    if scenario.is_choice_scenario():
        parts += [
            "",
            "Your options are:",
            scenario.options_formatted(),
            "",
            "Choose the option that best reflects your genuine reaction as someone "
            "with your background, values, and circumstances.",
        ]
    else:
        parts += [
            "",
            _OPEN_ENDED_PROMPTS[domain],
            "Describe your position in clear, personal terms — not as an expert "
            "or analyst, but as someone who this directly affects.",
        ]

    return "\n".join(parts)
