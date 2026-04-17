"""persistence — save and load PopScale StudyResult objects to disk.

Saves three files per study run:
    {run_id}_study.json       — full structured result (to_dict())
    {run_id}_report.md        — analytics report in markdown
    {run_id}_social_report.md — social report in markdown (only if social was run)

Usage::

    from popscale.study.persistence import save_study_result, list_saved_runs

    # Save automatically via output_dir in StudyConfig:
    config = StudyConfig(..., output_dir=Path("./results"))

    # Or save manually:
    save_study_result(result, Path("./results"))

    # List previous runs:
    runs = list_saved_runs(Path("./results"))
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .study_runner import StudyResult

logger = logging.getLogger(__name__)


def save_study_result(result: "StudyResult", output_dir: Path) -> Path:
    """Save a StudyResult to disk.

    Creates output_dir if it does not exist. Writes:
        {run_id}_study.json
        {run_id}_report.md
        {run_id}_social_report.md  (only if social was run)

    Args:
        result:     The StudyResult to save.
        output_dir: Directory to write files into.

    Returns:
        Path to the JSON file written.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = result.run_id

    # ── JSON (full structured output) ─────────────────────────────────────
    json_path = output_dir / f"{run_id}_study.json"
    json_path.write_text(
        json.dumps(result.to_dict(), indent=2, default=str),
        encoding="utf-8",
    )
    logger.info("save_study_result | JSON  → %s", json_path)

    # ── Markdown report ────────────────────────────────────────────────────
    md_path = output_dir / f"{run_id}_report.md"
    md_path.write_text(result.report.to_markdown(), encoding="utf-8")
    logger.info("save_study_result | MD    → %s", md_path)

    # ── Social report (optional) ───────────────────────────────────────────
    if result.social_report is not None:
        social_md_path = output_dir / f"{run_id}_social_report.md"
        social_md_path.write_text(result.social_report.to_markdown(), encoding="utf-8")
        logger.info("save_study_result | Social MD → %s", social_md_path)

    return json_path


def list_saved_runs(output_dir: Path) -> list[dict]:
    """Return metadata for all saved study runs in output_dir.

    Reads the _study.json files and returns a lightweight list of run summaries.

    Args:
        output_dir: Directory to scan.

    Returns:
        List of dicts with keys: run_id, started_at, n_personas, total_cost_usd.
        Sorted by started_at descending (most recent first).
    """
    output_dir = Path(output_dir)
    if not output_dir.exists():
        return []

    summaries: list[dict] = []
    for json_file in sorted(output_dir.glob("*_study.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            summaries.append({
                "run_id":        data.get("run_id", "unknown"),
                "started_at":    data.get("started_at", ""),
                "n_personas":    data.get("n_personas", 0),
                "total_cost_usd": data.get("total_cost_usd", 0.0),
                "file":          str(json_file),
            })
        except (json.JSONDecodeError, KeyError):
            logger.warning("list_saved_runs | Could not parse %s", json_file)

    return sorted(summaries, key=lambda x: x["started_at"], reverse=True)
