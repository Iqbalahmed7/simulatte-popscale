"""Pre-flight validation for benchmark configuration."""

from __future__ import annotations

import json
import os
from argparse import ArgumentTypeError
from dataclasses import dataclass, field
from pathlib import Path
from typing import NewType

AbsolutePath = NewType("AbsolutePath", Path)


class PreflightValidationError(ValueError):
    """Raised when preflight validation fails."""


@dataclass
class PreflightValidationResult:
    checks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    estimated_total_usd: float = 0.0
    cost_breakdown: dict[str, float] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.failures

    def render(self) -> str:
        lines = [
            "╔══════════════════════════════════════════╗",
            "║  Simulatte pre-flight check              ║",
            "╚══════════════════════════════════════════╝",
        ]
        lines.extend(f"✅ {c}" for c in self.checks)
        lines.extend(f"⚠️  {w}" for w in self.warnings)
        lines.extend(f"❌ {f}" for f in self.failures)
        if self.cost_breakdown:
            total = self.estimated_total_usd if self.estimated_total_usd > 0 else sum(self.cost_breakdown.values())
            lines.append("───")
            lines.append("Estimated cost breakdown:")
            for label, value in self.cost_breakdown.items():
                pct = (value / total * 100.0) if total else 0.0
                lines.append(f"  {label:<22} ~${value:.2f} ({pct:.0f}%)")
            lines.append("───")
        return "\n".join(lines)


def make_absolute_path(p: str | Path) -> AbsolutePath:
    path = Path(p).expanduser()
    if not path.is_absolute():
        raise ValueError(f"path must be absolute, got: {p!r} — try Path(p).resolve()")
    return AbsolutePath(path.resolve())


def parse_absolute_path(p: str) -> AbsolutePath:
    try:
        return make_absolute_path(p)
    except ValueError as exc:
        raise ArgumentTypeError(str(exc)) from exc


def _assert_readable_file(path: Path) -> None:
    if not path.exists():
        raise ValueError(f"file does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"path is not a file: {path}")
    if not os.access(path, os.R_OK):
        raise ValueError(f"file is not readable: {path}")


def _assert_writable_dir(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise ValueError(f"directory cannot be created: {path} ({exc})") from exc
    sentinel = path / ".preflight-write-test"
    try:
        sentinel.write_text("ok", encoding="utf-8")
        sentinel.unlink(missing_ok=True)
    except Exception as exc:
        raise ValueError(f"directory is not writable: {path} ({exc})") from exc


def _validate_baseline_schema(path: Path) -> None:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    required = {"run_id", "cluster_results"}
    missing = required.difference(data.keys())
    if missing:
        raise ValueError(
            f"baseline JSON missing required keys: {sorted(missing)} in {path}"
        )
    if not isinstance(data["cluster_results"], list):
        raise ValueError("baseline JSON key 'cluster_results' must be a list")


def validate_config(
    *,
    path_file_args: dict[str, Path | None] | None = None,
    path_dir_args: dict[str, Path | None] | None = None,
    budget_ceiling: float | None = None,
    estimated_total_usd: float = 0.0,
    force_over_budget: bool = False,
    baseline_path: Path | None = None,
    require_anthropic_key: bool = True,
    credit_detector_active: bool = False,
) -> PreflightValidationResult:
    result = PreflightValidationResult(
        estimated_total_usd=estimated_total_usd,
        cost_breakdown={
            "Niobe persona gen": round(estimated_total_usd * 0.62, 2),
            "PopScale scoring": round(estimated_total_usd * 0.31, 2),
            "Reflection + decide": round(estimated_total_usd * 0.07, 2),
        },
    )

    for arg_name, arg_path in (path_file_args or {}).items():
        if arg_path is None:
            continue
        try:
            _assert_readable_file(Path(arg_path))
            result.checks.append(f"{arg_name}: absolute and readable")
        except Exception as exc:
            result.failures.append(str(exc))

    for arg_name, arg_path in (path_dir_args or {}).items():
        if arg_path is None:
            continue
        try:
            _assert_writable_dir(Path(arg_path))
            result.checks.append(f"{arg_name}: directory writable")
        except Exception as exc:
            result.failures.append(str(exc))

    if require_anthropic_key:
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if key:
            result.checks.append("ANTHROPIC_API_KEY set")
        else:
            result.failures.append("ANTHROPIC_API_KEY is required but missing or empty")
    else:
        result.warnings.append("ANTHROPIC_API_KEY check skipped (non-API mode)")

    if credit_detector_active:
        topic = os.environ.get("SIMULATTE_NTFY_TOPIC", "").strip()
        if topic:
            result.checks.append("SIMULATTE_NTFY_TOPIC set")
        else:
            result.warnings.append("SIMULATTE_NTFY_TOPIC unset — push notifications disabled")

    if baseline_path is not None:
        try:
            _validate_baseline_schema(Path(baseline_path))
            result.checks.append("sensitivity baseline schema valid")
        except Exception as exc:
            result.failures.append(str(exc))

    if budget_ceiling is not None:
        if estimated_total_usd <= budget_ceiling:
            result.checks.append(
                f"Budget ceiling ${budget_ceiling:.2f} covers estimated ${estimated_total_usd:.2f}"
            )
        elif force_over_budget:
            result.warnings.append(
                f"Estimated ${estimated_total_usd:.2f} exceeds budget ceiling ${budget_ceiling:.2f} "
                f"but --force-over-budget enabled"
            )
        else:
            result.failures.append(
                f"Estimated cost ${estimated_total_usd:.2f} exceeds --budget-ceiling ${budget_ceiling:.2f}. "
                "Pass --force-over-budget to proceed anyway."
            )

    return result
