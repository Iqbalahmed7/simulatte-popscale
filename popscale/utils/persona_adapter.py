"""persona_adapter.py — migrates older Persona Generator schemas to current PersonaRecord.

The Persona Generator has evolved across sprints. Older cohorts (e.g. Montage v1.0)
use different field names and structures than the current PersonaRecord schema.

This adapter converts v1.0 persona dicts to the current schema so they can be
used in PopScale without regenerating the cohort.

Supported migrations:
    v1.0 → current:
        behavioural_params  → behavioural_tendencies
        narrative (str)     → narrative (Narrative object)
        memory.core_memory  → memory.core
        memory.operational_stream → memory.working.observations
        memory.simulation_state.awareness → awareness_set (dict preserved)

Usage:
    from popscale.utils.persona_adapter import adapt_persona_dict, load_cohort_file

    personas = load_cohort_file("/path/to/cohort.json")  # returns list[PersonaRecord]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_PG_ROOT = Path(__file__).parents[3] / "Persona Generator"
if str(_PG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PG_ROOT))

from src.schema.persona import PersonaRecord


# ── Objection type mapping (v1.0 domain-specific → current canonical types) ──

_OBJECTION_TYPE_MAP: dict[str, str] = {
    "workflow_disruption":        "switching_cost_concern",
    "tool_overlap_with_premiere": "feature_gap",
    "ai_control_loss":            "risk_aversion",
    "ai_quality_concerns":        "risk_aversion",
    "price_vs_value":             "price_vs_value",
    "trust_deficit":              "trust_deficit",
    "need_more_information":      "need_more_information",
    "social_proof_gap":           "social_proof_gap",
    "switching_cost_concern":     "switching_cost_concern",
    "risk_aversion":              "risk_aversion",
    "budget_ceiling":             "budget_ceiling",
    "feature_gap":                "feature_gap",
    "timing_mismatch":            "timing_mismatch",
}

_VALID_OBJECTION_TYPES = set(_OBJECTION_TYPE_MAP.values())


def _float_to_band(value: float, *, low: float = 0.35, high: float = 0.65) -> str:
    """Convert a 0-1 probability/score to low/medium/high band label."""
    if value >= high:
        return "high"
    if value <= low:
        return "low"
    return "medium"


def _adapt_behavioural_tendencies(bp: dict) -> dict:
    """Convert v1.0 behavioural_params → current behavioural_tendencies schema."""

    # ── price_sensitivity ─────────────────────────────────────────────────
    pe = bp.get("price_elasticity", {})
    price_band_raw = pe.get("band", "medium")
    # v1.0 uses elasticity magnitude; map to sensitivity band
    price_band_map = {"low": "low", "medium": "medium", "high": "high", "extreme": "extreme"}
    price_band = price_band_map.get(price_band_raw, "medium")
    price_desc = pe.get("proxy_signal", f"Price sensitivity: {price_band}")

    price_sensitivity = {
        "band": price_band,
        "description": price_desc[:200],  # cap length
        "source": "proxy",
    }

    # ── trust_orientation ─────────────────────────────────────────────────
    tv = bp.get("trust_vector", {})
    dominant = tv.get("dominant_anchor", "peer")
    trust_weights = {
        "expert":     float(tv.get("expert", 0.5)),
        "peer":       float(tv.get("peer", 0.5)),
        "brand":      float(tv.get("brand", 0.3)),
        "ad":         float(tv.get("ad", 0.2)),
        "community":  float(tv.get("community", 0.4)),
        "influencer": float(tv.get("influencer", 0.3)),
    }
    trust_orientation = {
        "weights": trust_weights,
        "dominant": dominant,
        "description": f"Primarily trusts {dominant} sources when making decisions.",
        "source": "proxy",
    }

    # ── switching_propensity ──────────────────────────────────────────────
    sh = bp.get("switching_hazard", {})
    # High switching_cost_index → low propensity to switch
    cost_index = float(sh.get("switching_cost_index", 0.5))
    switch_band = _float_to_band(1.0 - cost_index)  # invert: high cost → low propensity
    switch_desc = (
        f"Estimated tenure: {sh.get('estimated_tenure_periods', 'unknown')} periods. "
        f"Competitive stimulus multiplier: {sh.get('competitive_stimulus_multiplier', 1.0):.1f}."
    )
    switching_propensity = {
        "band": switch_band,
        "description": switch_desc,
        "source": "proxy",
    }

    # ── objection_profile ─────────────────────────────────────────────────
    raw_objections = bp.get("objection_profile", [])
    objections = []
    for obj in raw_objections:
        raw_type = obj.get("objection_type", "")
        mapped_type = _OBJECTION_TYPE_MAP.get(raw_type)
        if mapped_type is None:
            # Skip unknown types rather than crashing
            continue
        prob = float(obj.get("probability", 0.5))
        severity_raw = obj.get("severity", "friction")
        # Ensure severity is one of the valid literals
        severity = severity_raw if severity_raw in ("blocking", "friction", "minor") else "friction"
        likelihood = _float_to_band(prob, low=0.4, high=0.65)
        objections.append({
            "objection_type": mapped_type,
            "likelihood": likelihood,
            "severity": severity,
        })

    # ── reasoning_prompt ──────────────────────────────────────────────────
    # Derive a minimal prompt from available signals
    pp = bp.get("purchase_prob", {})
    baseline = pp.get("baseline_at_ask_price", 0.5)
    reasoning_prompt = (
        f"Purchase baseline at ask price: {baseline:.0%}. "
        f"Primary trust anchor: {dominant}. "
        f"Price band: {price_band}. "
        f"Switching propensity: {switch_band}."
    )

    return {
        "price_sensitivity": price_sensitivity,
        "trust_orientation": trust_orientation,
        "switching_propensity": switching_propensity,
        "objection_profile": objections,
        "reasoning_prompt": reasoning_prompt,
    }


def _adapt_narrative(raw_narrative: Any, name: str) -> dict:
    """Convert v1.0 narrative string → current Narrative object."""
    if isinstance(raw_narrative, dict):
        # Already in new format
        return raw_narrative
    text = str(raw_narrative) if raw_narrative else f"I am {name}."
    # Rough third-person: replace first-person pronouns
    third = (text
             .replace("I've", "They've").replace("I'm", "They're")
             .replace("I am", "They are").replace("I have", "They have")
             .replace("I was", "They were").replace("I do", "They do")
             .replace(" I ", " they ").replace(" I.", " they."))
    # Use first sentence as display name context
    first_sentence = text.split(".")[0].strip()
    display = name
    return {
        "first_person": text,
        "third_person": third,
        "display_name": display,
    }


def _adapt_memory(old_memory: dict, bp: dict) -> dict:
    """Convert v1.0 memory structure → current Memory schema (core + working)."""

    old_core = old_memory.get("core_memory", {})

    # ── CoreMemory ────────────────────────────────────────────────────────
    # Generate tendency_summary from behavioural_params signals
    pp = bp.get("purchase_prob", {})
    tv = bp.get("trust_vector", {})
    dominant = tv.get("dominant_anchor", "peer")
    baseline = pp.get("baseline_at_ask_price", 0.5)
    tendency_summary = (
        f"Purchase baseline: {baseline:.0%} at ask price. "
        f"Primarily trusts {dominant} sources. "
        f"Decision shaped by habit, consistency, and careful evaluation."
    )

    core = {
        "identity_statement": old_core.get("identity_statement", ""),
        "key_values": old_core.get("key_values", []),
        "life_defining_events": old_core.get("life_defining_events", []),
        "relationship_map": old_core.get("relationship_map", {
            "primary_decision_partner": "self",
            "key_influencers": [],
            "trust_network": [],
        }),
        "immutable_constraints": old_core.get("immutable_constraints", {
            "budget_ceiling": None,
            "non_negotiables": [],
            "absolute_avoidances": [],
        }),
        "tendency_summary": tendency_summary,
    }

    # ── WorkingMemory ─────────────────────────────────────────────────────
    old_sim = old_memory.get("simulation_state", {})
    # v1.0 has `awareness` dict; current schema expects `awareness_set` dict
    old_awareness = old_sim.get("awareness", {})
    awareness_set = old_awareness if isinstance(old_awareness, dict) else {}

    simulation_state = {
        "current_turn":          old_sim.get("current_turn", 0),
        "importance_accumulator": float(old_sim.get("importance_accumulator", 0.0)),
        "reflection_count":      old_sim.get("reflection_count", 0),
        "awareness_set":         awareness_set,
        "consideration_set":     old_sim.get("consideration_set", []),
        "last_decision":         old_sim.get("last_decision"),
    }

    working = {
        "observations":     [],   # operational_stream was empty in v1.0
        "reflections":      [],
        "plans":            [],
        "brand_memories":   old_memory.get("brand_memories", {}),
        "simulation_state": simulation_state,
    }

    return {"core": core, "working": working}


def adapt_persona_dict(raw: dict) -> dict:
    """Convert a v1.0 persona dict to the current PersonaRecord-compatible dict.

    Handles:
    - behavioural_params → behavioural_tendencies
    - narrative str → Narrative object
    - memory.core_memory → memory.core + memory.working
    - Strips extra fields (slot, archetype, persona_type, behavioural_params)
    """
    adapted = dict(raw)

    # Strip v1.0-only fields that PersonaRecord forbids
    for field in ("slot", "archetype", "persona_type", "behavioural_params"):
        adapted.pop(field, None)

    bp = raw.get("behavioural_params", {})

    # Adapt behavioural_tendencies
    if "behavioural_tendencies" not in adapted and bp:
        adapted["behavioural_tendencies"] = _adapt_behavioural_tendencies(bp)

    # Adapt narrative
    name = raw.get("demographic_anchor", {}).get("name", "Unknown")
    if "narrative" in adapted:
        adapted["narrative"] = _adapt_narrative(adapted["narrative"], name)

    # Adapt memory — only migrate v1.0 layouts (those that have "core_memory" or
    # lack a "core" key entirely).  Current-schema personas already have "core"
    # with the correct structure; running the migration on them drops key_values.
    if "memory" in adapted:
        mem = adapted["memory"]
        needs_migration = isinstance(mem, dict) and ("core_memory" in mem or "core" not in mem)
        if needs_migration:
            adapted["memory"] = _adapt_memory(mem, bp)

    return adapted


def load_cohort_file(path: str | Path) -> list[PersonaRecord]:
    """Load a persona cohort JSON file and return a list of PersonaRecord objects.

    Handles both current-schema CohortEnvelopes and v1.0 cohort files.
    Skips personas that fail validation after adaptation and logs warnings.

    Args:
        path: Path to a cohort envelope JSON file.

    Returns:
        List of valid PersonaRecord objects. May be shorter than the source
        cohort if some personas fail adaptation.
    """
    import logging
    logger = logging.getLogger(__name__)

    data = json.loads(Path(path).read_text())

    if "personas" in data:
        raw_list = data["personas"]
    elif "persona_id" in data:
        raw_list = [data]
    else:
        raise ValueError(f"Unrecognised cohort file format: {path}")

    records: list[PersonaRecord] = []
    for i, raw in enumerate(raw_list):
        try:
            adapted = adapt_persona_dict(raw)
            record = PersonaRecord(**adapted)
            records.append(record)
        except Exception as e:
            logger.warning("Skipping persona %d (%s): %s", i, raw.get("persona_id", "?"), e)

    logger.info("Loaded %d/%d personas from %s", len(records), len(raw_list), path)
    return records
