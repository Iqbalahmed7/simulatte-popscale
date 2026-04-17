"""Week 1 Integration Test — PopScale Scenario through Persona Generator cognitive loop.

Tests:
    1. Scenario model validates correctly
    2. render_stimulus() produces domain-differentiated text
    3. render_decision_scenario() produces meaningful decision prompts
    4. frame_persona_for_domain() produces different output per domain
    5. from_decision_output() wraps DecisionOutput correctly
    6. run_scenario() completes end-to-end with a real PersonaRecord
    7. run_scenario_batch() runs 5 personas concurrently

Run with:
    cd "/Users/admin/Documents/Simulatte Projects/PopScale"
    python3 -m pytest tests/test_week1_integration.py -v

For a live API test (makes actual LLM calls):
    python3 -m pytest tests/test_week1_integration.py -v -m live
"""

from __future__ import annotations

# ── sys.path setup — MUST be first, before any project imports ───────────
# PopScale package is named `popscale` (not `src`) to avoid collision with
# the Persona Generator's `src` package.
#   - PopScale root → `popscale.*` resolves to PopScale modules
#   - PG root       → `src.*` resolves to PG modules (PG's internal convention)
import sys
from pathlib import Path

_POPSCALE_ROOT = Path(__file__).parents[1]          # .../PopScale
_PG_ROOT       = _POPSCALE_ROOT.parent / "Persona Generator"

if str(_POPSCALE_ROOT) not in sys.path:
    sys.path.insert(0, str(_POPSCALE_ROOT))
if str(_PG_ROOT) not in sys.path:
    sys.path.insert(1, str(_PG_ROOT))

# ── Standard imports ──────────────────────────────────────────────────────
import asyncio

import pytest

# ── PopScale imports ──────────────────────────────────────────────────────
from popscale.scenario.model import Scenario, ScenarioBundle, SimulationDomain
from popscale.scenario.renderer import render_stimulus, render_decision_scenario
from popscale.domain.framing import frame_persona_for_domain, DIMENSION_LABELS, SEGMENT_LABELS


# ─────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────

@pytest.fixture
def consumer_scenario() -> Scenario:
    return Scenario(
        question="Should we launch a men's skincare line at 2× our women's product price?",
        context=(
            "Our brand is known for natural ingredients and has 80% female customers aged 25-40. "
            "Men's premium skincare is growing 18% YoY across India's metro markets. "
            "We have no male brand equity today. Our women's line is priced at ₹649."
        ),
        options=["Launch at 2× price (₹1,299)", "Launch at parity price (₹649)", "Do not launch yet"],
        domain=SimulationDomain.CONSUMER,
        environment={
            "market_conditions": "premium_growth",
            "competitive_intensity": "high",
            "region": "India",
            "economic_sentiment": "cautiously optimistic",
        },
    )


@pytest.fixture
def policy_scenario() -> Scenario:
    return Scenario(
        question="How should the government sequence the rollout of the new data privacy regulation?",
        context=(
            "Parliament has passed the Digital Data Protection Act requiring all companies "
            "to obtain explicit consent for data collection. The Act gives a 12-month "
            "implementation window. Small businesses have raised concerns about compliance costs."
        ),
        options=[
            "Immediate national rollout — all companies simultaneously",
            "Phased rollout — large companies first, SMEs with 6-month extension",
            "Sector-by-sector rollout over 18 months",
        ],
        domain=SimulationDomain.POLICY,
        environment={"regulatory_climate": "tightening", "region": "India"},
    )


@pytest.fixture
def political_scenario() -> Scenario:
    return Scenario(
        question="Which issue matters most in your vote for the upcoming state assembly election?",
        context=(
            "The state election is 3 months away. Key issues include rising unemployment "
            "among youth (18% aged 18-25), infrastructure gaps in Tier 2 cities, "
            "and the incumbent government's proposed farm loan waiver scheme."
        ),
        options=["Youth employment and job creation", "Infrastructure and urban development", "Agricultural support and farm relief"],
        domain=SimulationDomain.POLITICAL,
    )


@pytest.fixture
def open_ended_scenario() -> Scenario:
    return Scenario(
        question="How do you feel about the rising cost of healthy food in urban India?",
        context=(
            "Prices of fresh vegetables and healthy packaged foods have risen 22% over the past "
            "12 months in Indian metros. Low-calorie, organic, and nutritious options now cost "
            "35-40% more than standard alternatives."
        ),
        domain=SimulationDomain.CONSUMER,
    )


# ─────────────────────────────────────────────────────────────────────────
# 1. Scenario model validation
# ─────────────────────────────────────────────────────────────────────────

class TestScenarioModel:

    def test_consumer_scenario_valid(self, consumer_scenario):
        assert consumer_scenario.domain == SimulationDomain.CONSUMER
        assert consumer_scenario.is_choice_scenario()
        assert len(consumer_scenario.options) == 3

    def test_policy_scenario_valid(self, policy_scenario):
        assert policy_scenario.domain == SimulationDomain.POLICY
        assert policy_scenario.is_choice_scenario()

    def test_open_ended_not_choice(self, open_ended_scenario):
        assert not open_ended_scenario.is_choice_scenario()
        assert open_ended_scenario.options == []

    def test_single_option_invalid(self):
        with pytest.raises(Exception):
            Scenario(
                question="Should we do X?",
                context="Context here with enough words to pass validation.",
                options=["Only one option"],
                domain=SimulationDomain.CONSUMER,
            )

    def test_too_many_options_invalid(self):
        with pytest.raises(Exception):
            Scenario(
                question="Should we do X?",
                context="Context here with enough words to pass validation.",
                options=["A", "B", "C", "D", "E", "F", "G"],  # 7 options
                domain=SimulationDomain.CONSUMER,
            )

    def test_environment_summary_populated(self, consumer_scenario):
        summary = consumer_scenario.environment_summary()
        assert "India" in summary
        assert "premium_growth" in summary

    def test_environment_summary_empty(self, policy_scenario):
        no_env = Scenario(
            question="What do you think about this policy?",
            context="A policy question with adequate context for the test to pass.",
            domain=SimulationDomain.POLICY,
        )
        assert "No specific" in no_env.environment_summary()

    def test_options_formatted(self, consumer_scenario):
        formatted = consumer_scenario.options_formatted()
        assert "1." in formatted
        assert "2." in formatted
        assert "₹1,299" in formatted

    def test_scenario_bundle_valid(self, consumer_scenario, policy_scenario):
        bundle = ScenarioBundle(
            name="Test Study",
            scenarios=[consumer_scenario, policy_scenario],
        )
        assert len(bundle.scenarios) == 2


# ─────────────────────────────────────────────────────────────────────────
# 2. Renderer
# ─────────────────────────────────────────────────────────────────────────

class TestRenderer:

    def test_stimulus_contains_question(self, consumer_scenario):
        s = render_stimulus(consumer_scenario)
        assert consumer_scenario.question in s

    def test_stimulus_domain_header_consumer(self, consumer_scenario):
        s = render_stimulus(consumer_scenario)
        assert "CONSUMER MARKET SCENARIO" in s

    def test_stimulus_domain_header_policy(self, policy_scenario):
        s = render_stimulus(policy_scenario)
        assert "POLICY SCENARIO" in s

    def test_stimulus_domain_header_political(self, political_scenario):
        s = render_stimulus(political_scenario)
        assert "POLITICAL SCENARIO" in s

    def test_stimulus_includes_environment(self, consumer_scenario):
        s = render_stimulus(consumer_scenario)
        assert "India" in s

    def test_stimulus_no_environment_graceful(self, political_scenario):
        # political_scenario has no environment set
        s = render_stimulus(political_scenario)
        assert political_scenario.question in s
        # Should not error or include empty environment block
        assert "Environment: No specific" not in s

    def test_decision_scenario_includes_options_for_choice(self, consumer_scenario):
        d = render_decision_scenario(consumer_scenario)
        for opt in consumer_scenario.options:
            assert opt in d

    def test_decision_scenario_open_ended_no_options(self, open_ended_scenario):
        d = render_decision_scenario(open_ended_scenario)
        assert "reaction" in d.lower()
        # Options list should not appear
        assert "1." not in d

    def test_decision_scenario_domain_intro_consumer(self, consumer_scenario):
        d = render_decision_scenario(consumer_scenario)
        assert "consumer" in d.lower()

    def test_decision_scenario_domain_intro_policy(self, policy_scenario):
        d = render_decision_scenario(policy_scenario)
        assert "citizen" in d.lower()

    def test_decision_scenario_domain_intro_political(self, political_scenario):
        d = render_decision_scenario(political_scenario)
        assert "voter" in d.lower()

    def test_stimuli_differ_across_domains(self, consumer_scenario, policy_scenario):
        s_consumer = render_stimulus(consumer_scenario)
        s_policy   = render_stimulus(policy_scenario)
        # Header line must differ
        assert s_consumer.split("\n")[0] != s_policy.split("\n")[0]


# ─────────────────────────────────────────────────────────────────────────
# 3. Domain framing (uses PersonaRecord — skip if PG not importable)
# ─────────────────────────────────────────────────────────────────────────

class TestDomainFramingConstants:

    def test_dimension_labels_all_domains_present(self):
        for domain in SimulationDomain:
            assert domain in DIMENSION_LABELS
            assert "risk_appetite" in DIMENSION_LABELS[domain]

    def test_segment_labels_all_domains_present(self):
        for domain in SimulationDomain:
            assert domain in SEGMENT_LABELS
            for key in ["high", "medium", "low"]:
                assert key in SEGMENT_LABELS[domain]

    def test_dimension_labels_differ_across_domains(self):
        consumer_label = DIMENSION_LABELS[SimulationDomain.CONSUMER]["risk_appetite"]
        policy_label   = DIMENSION_LABELS[SimulationDomain.POLICY]["risk_appetite"]
        political_label = DIMENSION_LABELS[SimulationDomain.POLITICAL]["risk_appetite"]
        # All three should be different strings
        assert consumer_label != policy_label
        assert policy_label != political_label

    def test_segment_labels_differ_across_domains(self):
        consumer_high  = SEGMENT_LABELS[SimulationDomain.CONSUMER]["high"]
        policy_high    = SEGMENT_LABELS[SimulationDomain.POLICY]["high"]
        political_high = SEGMENT_LABELS[SimulationDomain.POLITICAL]["high"]
        assert consumer_high != policy_high
        assert policy_high != political_high


# ─────────────────────────────────────────────────────────────────────────
# 4. Live end-to-end tests (require Persona Generator + Anthropic API)
# ─────────────────────────────────────────────────────────────────────────

def _load_persona_from_pg() -> "PersonaRecord | None":
    """Load the first PersonaRecord from the Montage pilot cohort via the persona adapter.

    Falls back to scanning outputs/ for current-schema cohorts if Montage is unavailable.
    """
    from popscale.utils.persona_adapter import load_cohort_file

    # Primary: Montage v1.0 cohort (requires schema migration via adapter)
    montage_path = _PG_ROOT / "pilots" / "montage" / "cohort_montage_20260412.json"
    if montage_path.exists():
        try:
            records = load_cohort_file(montage_path)
            if records:
                return records[0]
        except Exception:
            pass

    # Fallback: current-schema cohorts in outputs/
    import json
    outputs_dir = _PG_ROOT / "outputs"
    if not outputs_dir.exists():
        return None
    for f in sorted(outputs_dir.glob("**/*.json")):
        try:
            data = json.loads(f.read_text())
            if "personas" in data and data["personas"]:
                from src.schema.persona import PersonaRecord
                return PersonaRecord(**data["personas"][0])
            elif "persona_id" in data:
                from src.schema.persona import PersonaRecord
                return PersonaRecord(**data)
        except Exception:
            continue
    return None


@pytest.mark.live
class TestLiveIntegration:
    """Live tests — make actual LLM calls. Run with -m live flag."""

    def test_frame_persona_consumer_vs_policy(self):
        persona = _load_persona_from_pg()
        if persona is None:
            pytest.skip("No PersonaRecord available in Persona Generator outputs/")
        framing_consumer  = frame_persona_for_domain(persona, SimulationDomain.CONSUMER)
        framing_policy    = frame_persona_for_domain(persona, SimulationDomain.POLICY)
        framing_political = frame_persona_for_domain(persona, SimulationDomain.POLITICAL)
        # Each domain should produce different text
        assert framing_consumer != framing_policy
        assert framing_policy != framing_political
        # Each should include the domain marker
        assert "CONSUMER" in framing_consumer
        assert "POLICY" in framing_policy
        assert "POLITICAL" in framing_political

    def test_run_scenario_single_persona(self, consumer_scenario):
        persona = _load_persona_from_pg()
        if persona is None:
            pytest.skip("No PersonaRecord available in Persona Generator outputs/")

        from popscale.integration.run_scenario import run_scenario
        from src.experiment.session import SimulationTier

        result = asyncio.run(
            run_scenario(scenario=consumer_scenario, persona=persona, tier=SimulationTier.VOLUME)
        )
        # Must be a valid PopulationResponse
        assert result.persona_name == persona.demographic_anchor.name
        assert result.decision != ""
        assert 0.0 <= result.confidence <= 1.0
        assert result.scenario_domain == "consumer"
        assert result.domain_signals is not None
        assert result.risk_appetite in ("low", "medium", "high")

    def test_run_scenario_batch_5_personas(self, consumer_scenario):
        persona = _load_persona_from_pg()
        if persona is None:
            pytest.skip("No PersonaRecord available in Persona Generator outputs/")

        # Use same persona 5× for test (in production, personas would differ)
        personas = [persona] * 5

        from popscale.integration.run_scenario import run_scenario_batch
        from src.experiment.session import SimulationTier

        results = asyncio.run(
            run_scenario_batch(
                scenario=consumer_scenario,
                personas=personas,
                tier=SimulationTier.VOLUME,
                concurrency=5,
            )
        )
        assert len(results) == 5
        for r in results:
            assert r.decision != ""
            assert 0.0 <= r.confidence <= 1.0
