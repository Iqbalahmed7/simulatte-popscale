from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

from popscale.scenario.model import Scenario, SimulationDomain


def _scenario_kwargs() -> dict:
    return {
        "question": "Should we run manifesto sensitivity now?",
        "context": "This is a sufficiently long context for Scenario validation checks.",
        "options": ["Yes", "No"],
        "domain": SimulationDomain.POLITICAL,
    }


def test_relative_path_rejected() -> None:
    with pytest.raises(ValueError, match="path must be absolute"):
        Scenario(**_scenario_kwargs(), sensitivity_baseline=Path("relative/baseline.json"))


def test_absolute_path_normalized() -> None:
    raw = Path("/tmp/a/../baseline.json")
    scenario = Scenario(**_scenario_kwargs(), sensitivity_baseline=raw)
    assert scenario.sensitivity_baseline == raw.resolve()


def test_tilde_path_expanded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    scenario = Scenario(**_scenario_kwargs(), sensitivity_baseline=Path("~/baseline.json"))
    assert str(scenario.sensitivity_baseline).startswith(str(tmp_path))


def test_symlink_resolved(tmp_path: Path) -> None:
    target = tmp_path / "real"
    target.mkdir()
    real_file = target / "baseline.json"
    real_file.write_text("{}", encoding="utf-8")
    symlink = tmp_path / "link.json"
    symlink.symlink_to(real_file)
    scenario = Scenario(**_scenario_kwargs(), sensitivity_baseline=symlink)
    assert scenario.sensitivity_baseline == real_file.resolve()


def test_cli_relative_sensitivity_baseline_rejected() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "benchmarks.wb_2026.constituency.wb_2026_constituency_benchmark",
            "--dry-run",
            "--manifesto",
            "both",
            "--sensitivity-baseline",
            "relative/path.json",
        ],
        cwd="/Users/admin/Documents/Simulatte Projects/simulatte-workspace/popscale",
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "path must be absolute" in (proc.stdout + proc.stderr)
