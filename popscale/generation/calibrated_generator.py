"""calibrated_generator — bridge from PopulationSpec to a generated persona cohort.

Converts a demographically-calibrated PopulationSpec into PG PersonaGenerationBriefs,
runs them through PG's orchestrator, and returns a unified list of PersonaRecords with
cost and quality accounting across all segments.

Key behaviours:

  1. Segment loop: each PersonaSegment from calibrate() becomes one or more PG briefs.
     Segments exceeding PG's 500-persona limit are split into sub-batches automatically.

  2. Auto-confirm: all briefs run with auto_confirm=True so no stdin prompts interrupt
     programmatic use. Cost is tracked in the result instead.

  3. Persona ID uniqueness: prefix is disambiguated per segment and sub-batch so IDs
     never collide across segments in the same cohort.

  4. Deserialization: PG returns list[dict]; this module converts them to PersonaRecord
     objects via the PopScale persona_adapter layer, handling v1.0 schema differences.

Usage::

    import asyncio
    from popscale.generation.calibrated_generator import run_calibrated_generation
    from popscale.calibration.population_spec import PopulationSpec

    spec = PopulationSpec(
        state="west_bengal",
        n_personas=500,
        domain="policy",
        business_problem="West Bengal electoral sentiment study.",
        stratify_by_religion=True,
    )

    result = asyncio.run(run_calibrated_generation(spec))
    print(f"Generated {result.total_delivered} personas, cost ${result.total_cost_usd:.4f}")
    personas = result.personas  # list[PersonaRecord]
"""

from __future__ import annotations

import asyncio
import logging
import sys
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_PG_ROOT = Path(__file__).parents[4] / "Persona Generator"
if str(_PG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PG_ROOT))

from src.orchestrator.brief import PersonaGenerationBrief          # noqa: E402
from src.orchestrator.invoke import invoke_persona_generator        # noqa: E402
from src.schema.persona import PersonaRecord                        # noqa: E402

from ..calibration.calibrator import PersonaSegment, calibrate     # noqa: E402
from ..calibration.population_spec import PopulationSpec           # noqa: E402
from ..utils.persona_adapter import adapt_persona_dict             # noqa: E402

# PG's hard per-brief limit.
# Calibration data (India+Sarvam pipeline) shows ~500s per 10-persona brief.
# Keep sub-batches ≤ 10 personas so every brief completes within the 600s timeout.
# Larger values cause timeouts on segments of 20+ personas.
_PG_MAX_PER_BRIEF = 10

# Maximum concurrent PG invocations across all segments.
# Running all segments fully in parallel floods the PG pipeline and causes
# rate-limit-induced timeouts. 3 concurrent calls is a safe upper bound.
_MAX_CONCURRENT_PG_CALLS = 3

# Per-brief timeout in seconds. 300s is too tight when multiple segments
# are competing for PG capacity. 600s (10 min) accommodates briefs of
# up to ~100 personas under moderate load.
_PG_BRIEF_TIMEOUT_S = 600.0


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class SegmentGenerationResult:
    """Generation outcome for a single demographic segment."""
    segment: PersonaSegment
    count_requested: int
    count_delivered: int
    cost_usd: float
    personas: list[Any]          # list[PersonaRecord]
    quality_summary: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class CohortGenerationResult:
    """Unified result from run_calibrated_generation().

    Attributes:
        run_id:             Unique identifier for this generation run.
        spec:               The PopulationSpec used.
        segments:           The calibrated segments that were generated.
        segment_results:    Per-segment generation outcomes.
        personas:           All PersonaRecord objects — ready for PopScale.
        total_requested:    Sum of persona counts across segments.
        total_delivered:    Actual personas successfully generated.
        total_cost_usd:     Sum of generation costs across all briefs.
        started_at:         UTC start timestamp.
        completed_at:       UTC completion timestamp.
    """
    run_id: str
    spec: PopulationSpec
    segments: list[PersonaSegment]
    segment_results: list[SegmentGenerationResult]
    personas: list[Any]          # list[PersonaRecord]
    total_requested: int
    total_delivered: int
    total_cost_usd: float
    started_at: datetime
    completed_at: datetime

    @property
    def duration_seconds(self) -> float:
        return (self.completed_at - self.started_at).total_seconds()

    @property
    def delivery_rate(self) -> float:
        return self.total_delivered / max(self.total_requested, 1)

    @property
    def cost_per_persona(self) -> float:
        return self.total_cost_usd / max(self.total_delivered, 1)

    def summary(self) -> str:
        return (
            f"CohortGen {self.run_id} | {self.total_delivered}/{self.total_requested} personas "
            f"({self.delivery_rate:.0%}) | ${self.total_cost_usd:.4f} total "
            f"(${self.cost_per_persona:.4f}/persona) | {self.duration_seconds:.1f}s"
        )

    def segment_breakdown(self) -> list[dict]:
        return [
            {
                "label":            sr.segment.label,
                "requested":        sr.count_requested,
                "delivered":        sr.count_delivered,
                "cost_usd":         round(sr.cost_usd, 4),
                "proportion":       round(sr.segment.proportion, 3),
            }
            for sr in self.segment_results
        ]


# ── Public API ────────────────────────────────────────────────────────────────

async def run_calibrated_generation(
    spec: PopulationSpec,
    *,
    run_id: Optional[str] = None,
    tier_override: Optional[str] = "volume",
    llm_client: Any = None,
    on_segment_complete: Optional[Callable[[SegmentGenerationResult], None]] = None,
) -> CohortGenerationResult:
    """Generate a demographically calibrated persona cohort from a PopulationSpec.

    Converts the spec into calibrated segments, builds PG briefs for each,
    and returns a unified cohort with all PersonaRecords aggregated.

    Args:
        spec:                The PopulationSpec describing the target population.
        run_id:              Optional identifier. Auto-generated if None.
        tier_override:       PG tier to use. Default "volume" for large population runs.
                             Use "signal" for exploratory, "deep" for client-facing quality.
        llm_client:          Optional Anthropic client. PG creates one if None.
        on_segment_complete: Optional callback fired after each segment finishes.
                             Receives the SegmentGenerationResult for streaming use.

    Returns:
        CohortGenerationResult with all PersonaRecords and cost/quality accounting.

    Raises:
        ValueError: If spec produces no segments or no personas are delivered.
        KeyError: If spec.state is not in the demographic profile library.
    """
    run_id    = run_id or f"cg-{uuid.uuid4().hex[:8]}"
    started_at = datetime.now(timezone.utc)

    segments = calibrate(spec)

    logger.info(
        "run_calibrated_generation | run=%s | state=%s | n=%d | segments=%d | tier=%s",
        run_id, spec.state, spec.n_personas, len(segments), tier_override,
    )

    # ── Per-segment coroutine ─────────────────────────────────────────────────

    async def _run_segment(seg_idx: int, segment: PersonaSegment) -> SegmentGenerationResult:
        """Generate all personas for one demographic segment (all sub-batches)."""
        logger.info("  segment %d/%d — %s (%d personas)…",
                    seg_idx + 1, len(segments), segment.label, segment.count)

        seg_personas: list[PersonaRecord] = []
        seg_cost = 0.0
        seg_warnings: list[str] = []
        seg_quality: dict = {}

        sub_batches = _split_count(segment.count, _PG_MAX_PER_BRIEF)

        for batch_idx, batch_count in enumerate(sub_batches):
            prefix = f"{spec.persona_id_prefix}-s{seg_idx}-b{batch_idx}"

            # Shift the pool start index so different segments/sub-batches
            # cycle through different entries.  Without this, every segment
            # starts at index 0 and produces the same repeated personas.
            # We use seg_idx * 7 + batch_idx * 3 to spread segments across
            # the ~40-entry India pool without repeating patterns.
            pool_offset = seg_idx * 7 + batch_idx * 3
            overrides_with_offset = {
                **segment.anchor_overrides,
                "_pool_start_index": pool_offset,
            }

            brief = PersonaGenerationBrief(
                client=spec.client,
                domain=spec.domain,
                business_problem=spec.business_problem,
                count=batch_count,
                anchor_overrides=overrides_with_offset,
                persona_id_prefix=prefix,
                sarvam_enabled=spec.sarvam_enabled,
                auto_confirm=True,
                tier_override=tier_override,
                # PopScale generates per-segment sub-batches that are intentionally
                # demographically homogeneous (one religion+income slice).  Cohort-
                # level diversity gates (G6) fail on small homogeneous batches even
                # though the full assembled cohort IS diverse.  Skip PG's internal
                # gates here; PopScale's parity_validator runs after full assembly.
                skip_gates=True,
            )

            logger.info("    sub-batch %d/%d — %d personas (prefix=%s)…",
                        batch_idx + 1, len(sub_batches), batch_count, prefix)

            try:
                pg_result = await asyncio.wait_for(
                    invoke_persona_generator(brief),
                    timeout=_PG_BRIEF_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "  segment %d sub-batch %d timed out after %.0fs — skipping",
                    seg_idx, batch_idx, _PG_BRIEF_TIMEOUT_S,
                )
                seg_warnings.append(f"Sub-batch {batch_idx}: timed out after {_PG_BRIEF_TIMEOUT_S:.0f}s")
                continue
            except Exception as exc:
                logger.error(
                    "  segment %d sub-batch %d failed — skipping (%s: %s)\n%s",
                    seg_idx, batch_idx, type(exc).__name__, exc,
                    traceback.format_exc(),
                )
                seg_warnings.append(
                    f"Sub-batch {batch_idx}: failed with {type(exc).__name__}: {exc}"
                )
                continue

            batch_personas = _deserialise_personas(pg_result.personas)
            seg_personas.extend(batch_personas)

            if hasattr(pg_result, "cost_actual") and pg_result.cost_actual:
                ca = pg_result.cost_actual
                batch_cost = getattr(ca, "total", 0.0) or getattr(ca, "generation", 0.0) or 0.0
                seg_cost += batch_cost

            if hasattr(pg_result, "quality_report") and pg_result.quality_report:
                qr = pg_result.quality_report
                seg_quality = {
                    "gates_passed": getattr(qr, "gates_passed", None),
                    "quarantine_count": getattr(qr, "quarantine_count", 0),
                }

            delivered = len(batch_personas)
            if delivered < batch_count:
                seg_warnings.append(
                    f"Sub-batch {batch_idx}: requested {batch_count}, delivered {delivered}"
                )

        sr = SegmentGenerationResult(
            segment=segment,
            count_requested=segment.count,
            count_delivered=len(seg_personas),
            cost_usd=seg_cost,
            personas=seg_personas,
            quality_summary=seg_quality,
            warnings=seg_warnings,
        )

        logger.info("  segment %d/%d done — %d personas, $%.4f",
                    seg_idx + 1, len(segments), sr.count_delivered, sr.cost_usd)

        if on_segment_complete is not None:
            if asyncio.iscoroutinefunction(on_segment_complete):
                await on_segment_complete(sr)
            else:
                on_segment_complete(sr)

        return sr

    # ── Run segments with bounded concurrency ────────────────────────────────
    # asyncio.gather preserves order — segment_results[i] corresponds to segments[i].
    # A semaphore caps concurrent PG invocations at _MAX_CONCURRENT_PG_CALLS.
    # Running all segments fully in parallel floods the PG pipeline and causes
    # rate-limit-induced timeouts; 3 concurrent calls is a safe upper bound.
    _pg_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_PG_CALLS)

    async def _run_segment_gated(seg_idx: int, segment: PersonaSegment) -> SegmentGenerationResult:
        async with _pg_semaphore:
            return await _run_segment(seg_idx, segment)

    segment_results: list[SegmentGenerationResult] = list(
        await asyncio.gather(*[
            _run_segment_gated(seg_idx, segment)
            for seg_idx, segment in enumerate(segments)
        ])
    )

    all_personas: list[PersonaRecord] = []
    for sr in segment_results:
        all_personas.extend(sr.personas)

    completed_at = datetime.now(timezone.utc)

    result = CohortGenerationResult(
        run_id=run_id,
        spec=spec,
        segments=segments,
        segment_results=segment_results,
        personas=all_personas,
        total_requested=spec.n_personas,
        total_delivered=len(all_personas),
        total_cost_usd=sum(sr.cost_usd for sr in segment_results),
        started_at=started_at,
        completed_at=completed_at,
    )

    logger.info("run_calibrated_generation complete: %s", result.summary())
    return result


def run_calibrated_generation_sync(
    spec: PopulationSpec,
    **kwargs: Any,
) -> CohortGenerationResult:
    """Synchronous wrapper around run_calibrated_generation().

    Suitable for scripts and notebooks. Uses asyncio.run() internally.
    Do not call from inside an already-running event loop.
    """
    return asyncio.run(run_calibrated_generation(spec, **kwargs))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _split_count(total: int, max_per_batch: int) -> list[int]:
    """Split total into sub-batch sizes, each ≤ max_per_batch."""
    if total <= max_per_batch:
        return [total]
    batches: list[int] = []
    remaining = total
    while remaining > 0:
        batch = min(remaining, max_per_batch)
        batches.append(batch)
        remaining -= batch
    return batches


def _deserialise_personas(raw_dicts: list[dict]) -> list[PersonaRecord]:
    """Convert PG's list[dict] persona output into PersonaRecord objects."""
    records: list[PersonaRecord] = []
    for d in raw_dicts:
        try:
            adapted = adapt_persona_dict(d)
            records.append(PersonaRecord.model_validate(adapted))
        except Exception as e:
            logger.warning("Failed to deserialise persona dict: %s", e)
    return records
