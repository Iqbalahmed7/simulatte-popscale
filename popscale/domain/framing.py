"""Domain framing — translates PersonaRecord attributes into domain-specific language.

The Persona Generator's PersonaRecord is domain-neutral: its derived_insights
and behavioural_tendencies are expressed in universal terms (risk_appetite: high,
trust_anchor: peer, decision_style: emotional).

This module translates those domain-neutral attributes into domain-specific
behavioral frames that make the decide() prompt meaningful in the target context:
  - Consumer: "you are a price-conscious, peer-trusting consumer"
  - Policy:   "you are a risk-averse, evidence-demanding citizen"
  - Political:"you have a social decision style and trust your community networks"

The framing is appended to the decision_scenario string, injected into decide()
as additional context before the 5-step reasoning chain runs.

All translations are deterministic (no LLM, no randomness).
"""

from __future__ import annotations

import sys
from pathlib import Path

# ── Persona Generator import ───────────────────────────────────────────────
# PopScale package is named `popscale` (not `src`) to avoid collision with
# the Persona Generator's `src` package. PG root is in sys.path so PG modules
# are importable as `src.X` (PG's internal convention).
_PG_ROOT = Path(__file__).parents[3] / "Persona Generator"
if str(_PG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PG_ROOT))

from src.schema.persona import PersonaRecord  # noqa: E402  (PG)

from ..scenario.model import SimulationDomain  # noqa: E402  (PopScale)


# ── Dimension labels by domain ────────────────────────────────────────────
# Maps PersonaRecord.derived_insights field names to domain-specific labels.
# These labels appear in the behavioral framing block appended to decide().

DIMENSION_LABELS: dict[SimulationDomain, dict[str, str]] = {
    SimulationDomain.CONSUMER: {
        "risk_appetite":            "willingness to try new things",
        "trust_anchor":             "who you trust when making decisions",
        "decision_style":           "how you make purchase decisions",
        "primary_value_orientation":"what you value most when buying",
        "price_sensitivity":        "price sensitivity",
        "switching_propensity":     "openness to switching brands",
    },
    SimulationDomain.POLICY: {
        "risk_appetite":            "tolerance for implementation risk",
        "trust_anchor":             "who you trust in public institutions",
        "decision_style":           "how you evaluate policy proposals",
        "primary_value_orientation":"what outcomes matter most to you",
        "price_sensitivity":        "sensitivity to costs of compliance or change",
        "switching_propensity":     "openness to policy change",
    },
    SimulationDomain.POLITICAL: {
        "risk_appetite":            "political risk appetite",
        "trust_anchor":             "who shapes your political views",
        "decision_style":           "how you make political decisions",
        "primary_value_orientation":"your core political priority",
        "price_sensitivity":        "sensitivity to economic trade-offs",
        "switching_propensity":     "openness to changing your political position",
    },
}


# ── Segment labels by domain ───────────────────────────────────────────────
# Maps the persona's behavioral prior (high/medium/low openness) to
# domain-appropriate segment names.

SEGMENT_LABELS: dict[SimulationDomain, dict[str, str]] = {
    SimulationDomain.CONSUMER: {
        "high":   "likely converter",
        "medium": "uncertain / on the fence",
        "low":    "likely to resist",
    },
    SimulationDomain.POLICY: {
        "high":   "likely supporter",
        "medium": "undecided",
        "low":    "likely opponent",
    },
    SimulationDomain.POLITICAL: {
        "high":   "committed supporter",
        "medium": "persuadable",
        "low":    "firmly opposed",
    },
}


# ── Value orientation domain translation ──────────────────────────────────
# PersonaRecord.derived_insights.primary_value_orientation uses consumer-
# native labels ("price", "quality", "brand"). These map to domain equivalents.

_VALUE_ORIENTATION_LABELS: dict[SimulationDomain, dict[str, str]] = {
    SimulationDomain.CONSUMER: {
        "price":        "price-conscious — cost is the primary lens",
        "quality":      "quality-first — you pay for what works",
        "brand":        "brand-driven — trust and reputation matter most",
        "convenience":  "convenience-led — ease of use wins",
        "features":     "feature-oriented — you evaluate capabilities carefully",
    },
    SimulationDomain.POLICY: {
        "price":        "cost-focused — public spending efficiency matters most",
        "quality":      "outcome-focused — results matter more than method",
        "brand":        "institution-focused — you trust established systems",
        "convenience":  "implementation-focused — practical rollout matters",
        "features":     "detail-oriented — you evaluate policy specifications carefully",
    },
    SimulationDomain.POLITICAL: {
        "price":        "economically-driven — financial impact shapes your vote",
        "quality":      "results-driven — you judge on track record and delivery",
        "brand":        "party/candidate-driven — affiliation and character matter most",
        "convenience":  "pragmatic — you back whoever can get things done",
        "features":     "policy-detail-driven — you research platforms carefully",
    },
}


# ── Risk appetite descriptors ─────────────────────────────────────────────

_RISK_DESCRIPTORS: dict[SimulationDomain, dict[str, str]] = {
    SimulationDomain.CONSUMER: {
        "low":    "cautious — you prefer proven products and stick to what you know",
        "medium": "moderately open — you'll try new things if there's enough evidence",
        "high":   "adventurous — you're among the first to try new products",
    },
    SimulationDomain.POLICY: {
        "low":    "risk-averse — you prefer gradual, evidence-backed implementation",
        "medium": "balanced — you weigh risks but accept reasonable uncertainty",
        "high":   "reform-ready — you favour bold change even under uncertainty",
    },
    SimulationDomain.POLITICAL: {
        "low":    "stability-oriented — you prefer incremental change and proven leadership",
        "medium": "open — you'll consider new directions given compelling arguments",
        "high":   "change-oriented — you welcome bold new political directions",
    },
}


# ── Trust anchor descriptors ──────────────────────────────────────────────

_TRUST_DESCRIPTORS: dict[SimulationDomain, dict[str, str]] = {
    SimulationDomain.CONSUMER: {
        "self":      "you trust your own research and direct experience",
        "peer":      "you rely heavily on recommendations from people like you",
        "authority": "you trust expert reviews and certified credentials",
        "family":    "family opinions and traditions guide your choices",
    },
    SimulationDomain.POLICY: {
        "self":      "you form your own views from primary sources",
        "peer":      "you're influenced by what your community thinks",
        "authority": "you trust official bodies, experts, and institutions",
        "family":    "family values and community norms anchor your views",
    },
    SimulationDomain.POLITICAL: {
        "self":      "you're a self-researcher — you don't rely on others' political cues",
        "peer":      "your community's views heavily influence your political position",
        "authority": "you follow respected political figures and credentialed experts",
        "family":    "family tradition and community identity shape your politics",
    },
}


_POLITICAL_LEAN_FRAMING: dict[str, str] = {
    "opposition":      "You are a committed TMC/Trinamool Congress supporter — you see the party as the protector of Bengal's identity and secular fabric.",
    "opposition_lean": "You lean towards TMC/Trinamool Congress — you broadly support the incumbent government, though you have some reservations.",
    "bjp_supporter":   "You are a firm BJP supporter — you believe in Hindu consolidation and Modi's national leadership, and see TMC as corrupt.",
    "bjp_lean":        "You lean BJP — you're drawn to the BJP's Hindu nationalist platform and are frustrated with TMC's governance failures.",
    "left_lean":       "Your political identity is rooted in the Left-Congress alliance — you oppose both TMC's syndicate politics and BJP's communal agenda. You would vote Left-Congress or a third alternative before either main party.",
    "neutral":         "You are a genuine swing voter — you have no firm party loyalty and will decide based on local candidate quality and immediate issues.",
}


def frame_persona_for_domain(persona: PersonaRecord, domain: SimulationDomain) -> str:
    """Generate a domain-specific behavioral framing block for a PersonaRecord.

    This block is appended to the decision_scenario string before decide() runs.
    It translates the persona's domain-neutral attributes (risk_appetite, trust_anchor,
    decision_style, etc.) into domain-specific language so the 5-step reasoning
    chain is anchored to the right context.

    Returns a compact paragraph — not a bulleted list — so it reads naturally
    inside the decide() prompt without adding excessive structure.
    """
    di = persona.derived_insights
    bt = persona.behavioural_tendencies

    risk_desc = _RISK_DESCRIPTORS[domain].get(di.risk_appetite, di.risk_appetite)
    trust_desc = _TRUST_DESCRIPTORS[domain].get(di.trust_anchor, di.trust_anchor)
    value_desc = _VALUE_ORIENTATION_LABELS[domain].get(
        di.primary_value_orientation, di.primary_value_orientation
    )

    # Prior segment estimate (before seeing the scenario)
    prior = _estimate_prior(persona)
    segment_label = SEGMENT_LABELS[domain][prior]

    # Decision style natural language
    style_map = {
        "emotional":   "your gut and emotional reaction guide you",
        "analytical":  "you think through information systematically before deciding",
        "habitual":    "you rely on established patterns and past experience",
        "social":      "you look to others around you before committing",
    }
    style_desc = style_map.get(di.decision_style, di.decision_style)

    # For POLITICAL domain: inject explicit political lean so the LLM doesn't
    # have to infer it from demographic signals alone. This anchors left_lean
    # personas to Left-Congress and prevents them from defaulting to TMC/BJP.
    political_lean_sentence = ""
    if domain == SimulationDomain.POLITICAL:
        try:
            import sys
            from pathlib import Path
            _pg = Path(__file__).parents[3] / "Persona Generator"
            if str(_pg) not in sys.path:
                sys.path.insert(0, str(_pg))
            from src.memory.core_memory import _get_political_lean  # noqa: E402
            lean = _get_political_lean(persona)
            if lean and lean in _POLITICAL_LEAN_FRAMING:
                political_lean_sentence = " " + _POLITICAL_LEAN_FRAMING[lean]
        except Exception:
            pass  # silently skip if PG unavailable

    return (
        f"\n[DOMAIN FRAMING — {domain.value.upper()}]\n"
        f"In this context, you are {risk_desc}. "
        f"When it comes to trust, {trust_desc}. "
        f"You are {value_desc}. "
        f"When making decisions, {style_desc}. "
        f"Based on your profile, you start as a '{segment_label}' — "
        f"but the specifics of this scenario may shift that."
        f"{political_lean_sentence}"
    )


def _estimate_prior(persona: PersonaRecord) -> str:
    """Estimate the persona's prior segment before seeing the scenario.

    Uses risk_appetite (primary) and trust_anchor (modifier) as proxies.
    This mirrors PersonaBehavior.segment_prior() from the VC Universe adapter
    but reads from PersonaRecord rather than the VC 9-dim vector.
    """
    risk_map = {"low": 0.2, "medium": 0.5, "high": 0.8}
    risk_score = risk_map.get(persona.derived_insights.risk_appetite, 0.5)

    # Trust anchor modifier: authority/expert trust correlates with lower resistance
    trust_modifier = {
        "authority": +0.05,
        "self":      +0.0,
        "peer":      -0.0,
        "family":    -0.05,
    }.get(persona.derived_insights.trust_anchor, 0.0)

    openness = min(1.0, max(0.0, risk_score + trust_modifier))

    if openness >= 0.6:
        return "high"
    elif openness <= 0.35:
        return "low"
    return "medium"
