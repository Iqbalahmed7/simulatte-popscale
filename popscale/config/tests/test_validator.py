from __future__ import annotations

import json
from pathlib import Path

import pytest

from popscale.config.validator import make_absolute_path, validate_config


def test_make_absolute_path_rejects_relative() -> None:
    with pytest.raises(ValueError, match="path must be absolute"):
        make_absolute_path("relative/file.json")


def test_make_absolute_path_accepts_and_normalizes(tmp_path: Path) -> None:
    candidate = tmp_path / "a" / ".." / "b.json"
    path = make_absolute_path(candidate)
    assert str(path).endswith("/b.json")


def test_validate_config_collects_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    bad_file = tmp_path / "missing.json"

    result = validate_config(
        path_file_args={"--sensitivity-baseline": bad_file},
        budget_ceiling=1.0,
        estimated_total_usd=5.0,
        require_anthropic_key=True,
        baseline_path=bad_file,
    )
    assert not result.ok
    joined = "\n".join(result.failures)
    assert "file does not exist" in joined
    assert "ANTHROPIC_API_KEY is required" in joined
    assert "exceeds --budget-ceiling" in joined


def test_validate_config_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x-test")
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "run_id": "r1",
                "cluster_results": [],
                "seat_prediction": {
                    "TMC": 1,
                    "BJP": 1,
                    "Left-Congress": 1,
                    "Others": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    result = validate_config(
        path_file_args={"--sensitivity-baseline": baseline},
        path_dir_args={"--out-dir": out_dir},
        budget_ceiling=100.0,
        estimated_total_usd=25.0,
        baseline_path=baseline,
        require_anthropic_key=True,
    )
    assert result.ok
    rendered = result.render()
    assert "Simulatte pre-flight check" in rendered
    assert "ANTHROPIC_API_KEY set" in rendered
    assert "Estimated cost breakdown" in rendered
