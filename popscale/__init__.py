"""PopScale — Population-scale simulation layer for Simulatte.

PopScale is a scenario orchestration, domain framing, and analytics layer
built on top of the Persona Generator. It does NOT re-implement the cognitive
loop, social simulation, memory, or tier routing — those live in the Persona
Generator and are imported directly.

Quick start::

    import asyncio
    from popscale import (
        PopulationSpec, Scenario, SimulationDomain,
        StudyConfig, run_study,
    )

    config = StudyConfig(
        spec=PopulationSpec(
            state="west_bengal", n_personas=500,
            domain="policy",
            business_problem="Bengal election sentiment",
            stratify_by_religion=True,
        ),
        scenario=Scenario(
            question="Will you vote for TMC?",
            context="Elections are next month...",
            options=["Yes", "No", "Undecided"],
            domain=SimulationDomain.POLITICAL,
        ),
    )
    result = asyncio.run(run_study(config))
    print(result.report.to_markdown())

Public API
----------
Study entry points:
    run_study(config)                — async; full pipeline
    run_study_sync(config)           — sync wrapper
    StudyConfig                      — full study configuration
    StudyResult                      — full study output
    BudgetExceededError              — raised when cost estimate exceeds cap
    GenerationFailedError            — raised when PG orchestrator fails entirely
    estimate_study_cost(config)      — pre-flight cost estimate

Population:
    PopulationSpec                   — demographic configuration
    get_profile(state)               — lookup DemographicProfile
    list_states()                    — all available geography codes
    calibrate(spec)                  — produce PersonaSegment list
    PersonaSegment                   — single demographic segment

Scenario:
    Scenario                         — the question posed to personas
    SimulationDomain                 — CONSUMER / POLICY / POLITICAL
    EventTimeline                    — temporal event injection
    SimulationEvent                  — individual event
    EventCategory                    — ECONOMIC / POLITICAL / SOCIAL / …

Environment:
    SimulationEnvironment            — named environment preset
    get_preset(name)                 — lookup preset by name
    list_presets()                   — all registered preset names
    apply_environment(scenario, env) — merge env into scenario

Social:
    SocialSimulationLevel            — ISOLATED / LOW / MODERATE / HIGH / SATURATED

Analytics:
    PopScaleReport                   — aggregate analytics output

Persistence:
    save_study_result(result, dir)   — save result to disk
    list_saved_runs(dir)             — list previously saved runs
"""

from .calibration.calibrator import PersonaSegment, calibrate
from .calibration.population_spec import PopulationSpec
from .calibration.profiles import DemographicProfile, get_profile, list_states, list_profiles
from .environment import (
    SimulationEnvironment,
    apply_environment,
    get_preset,
    list_presets,
)
from .scenario.events import EventCategory, EventTimeline, SimulationEvent
from .scenario.model import Scenario, SimulationDomain
try:
    from .social.social_runner import SocialSimulationLevel
except ImportError:
    SocialSimulationLevel = None  # type: ignore[assignment,misc]  # PG not available
from .study.persistence import list_saved_runs, save_study_result
from .study.study_runner import (
    BudgetExceededError,
    GenerationFailedError,
    StudyConfig,
    StudyResult,
    estimate_study_cost,
    run_study,
    run_study_sync,
)

__all__ = [
    # Study
    "run_study",
    "run_study_sync",
    "StudyConfig",
    "StudyResult",
    "BudgetExceededError",
    "GenerationFailedError",
    "estimate_study_cost",
    # Population
    "PopulationSpec",
    "PersonaSegment",
    "calibrate",
    "DemographicProfile",
    "get_profile",
    "list_states",
    "list_profiles",
    # Scenario
    "Scenario",
    "SimulationDomain",
    "EventTimeline",
    "SimulationEvent",
    "EventCategory",
    # Environment
    "SimulationEnvironment",
    "apply_environment",
    "get_preset",
    "list_presets",
    # Social
    "SocialSimulationLevel",
    # Persistence
    "save_study_result",
    "list_saved_runs",
]
