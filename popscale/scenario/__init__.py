"""Scenario — structured multi-domain simulation input for PopScale."""
from .model import Scenario, ScenarioBundle, SimulationDomain
from .renderer import render_stimulus, render_decision_scenario

__all__ = [
    "Scenario",
    "ScenarioBundle",
    "SimulationDomain",
    "render_stimulus",
    "render_decision_scenario",
]
