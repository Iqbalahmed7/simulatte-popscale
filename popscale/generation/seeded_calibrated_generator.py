"""seeded_calibrated_generator — two-pass cohort generation using seed + variant expansion.

Pass 1 (seeds):   Generates `seed_count` deep personas via the full PG pipeline.
                  Segments are proportional to the full population distribution.
                  Uses `run_calibrated_generation()` with reduced counts.

Pass 2 (variants): Expands each seed into N variants using `VariantGenerator`.
                   1 Haiku call per variant. Runs in parallel across seeds.

Returns a `CohortGenerationResult` identical in shape to `calibrated_generator.py`,
so downstream consumers (study_runner, Niobe) need no changes.

Cost example (10,000 personas, 200 seeds, deep tier):
  Pass 1: 200 × $0.30 = $60.00
  Pass 2: 9,800 × $0.004 = $39.20
  Total: $99.20  vs  $3,000 standard mode  (~97% reduction)

Usage::

    import asyncio
    from popscale.generation.seeded_calibrated_generator import run_seeded_generation
    from popscale.calibration.population_spec import PopulationSpec

    spec = PopulationSpec(
        state="west_bengal", n_personas=10_000, domain="policy",
        business_problem="Electoral sentiment study.", stratify_by_religion=True,
    )
    result = asyncio.run(run_seeded_generation(spec, seed_count=200))
    print(f"Seeds: {result.metadata['seed_count_actual']} | "
          f"Variants: {result.metadata['variant_count_actual']} | "
          f"Total: {result.total_delivered} | ${result.total_cost_usd:.2f}")
"""

from __future__ import annotations

import asyncio
import logging
import sys
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
from .calibrated_generator import (                                # noqa: E402
    CohortGenerationResult,
    SegmentGenerationResult,
    _split_count,
    _deserialise_personas,
)
from .parity_validator import validate_parity                      # noqa: E402
from .seed_calibrator import SeedSegment, distribute_seeds         # noqa: E402
from .variant_generator import VariantGenerator                    # noqa: E402

_PG_MAX_PER_BRIEF = 500


# ── Public API ────────────────────────────────────────────────────────────────

async def run_seeded_generation(
    spec: PopulationSpec,
    *,
    seed_count: int = 200,
    seed_tier: str = "deep",
    run_id: Optional[str] = None,
    llm_client: Any = None,
    on_segment_complete: Optional[Callable[[SegmentGenerationResult], None]] = None,
) -> CohortGenerationResult:
    """Generate a seeded cohort: `seed_count` deep personas + variant expansion.

    Args:
        spec:                PopulationSpec describing the target population.
        seed_count:          Number of deep seed personas to generate (via full PG).
        seed_tier:           PG tier for seed generation ("deep", "signal", "volume").
        run_id:              Optional identifier. Auto-generated if None.
        llm_client:          Optional Anthropic client. PG creates one if None.
        on_segment_complete: Optional callback fired after each segment finishes.

    Returns:
        CohortGenerationResult with seeds + variants, identical shape to
        run_calibrated_generation() output.

    Raises:
        ValueError: If seed_count ≥ spec.n_personas (no variants to generate).
        ValueError: If no personas are delivered.
    """
    if seed_count >= spec.n_personas:
        raise ValueError(
            f"seed_count ({seed_count}) must be < n_personas ({spec.n_personas}). "
            "Use run_calibrated_generation() when all personas are seeds."
        )

    run_id    = run_id or f"sg-{uuid.uuid4().hex[:8]}"
    started_at = datetime.now(timezone.utc)

    logger.info(
        "run_seeded_generation | run=%s | state=%s | n=%d | seeds=%d | tier=%s",
        run_id, spec.state, spec.n_personas, seed_count, seed_tier,
    )

    # ── Calibrate + distribute seeds ──────────────────────────────────────────
    segments  = calibrate(spec)
    seed_segs = distribute_seeds(segments, seed_count=seed_count)

    logger.info(
        "  Segments: %d | Seeds per segment: %s",
        len(seed_segs),
        ", ".join(f"{ss.label}={ss.seed_count}" for ss in seed_segs),
    )

    # ── Pass 1: generate seeds in parallel across segments ────────────────────
    logger.info("  Pass 1: generating %d deep seeds…", seed_count)

    async def _generate_seeds(ss: SeedSegment, seg_idx: int) -> list[PersonaRecord]:
        """Full PG pipeline for seed personas in one segment."""
        seeds: list[PersonaRecord] = []
        warnings: list[str] = []

        sub_batches = _split_count(ss.seed_count, _PG_MAX_PER_BRIEF)
        for batch_idx, batch_count in enumerate(sub_batches):
            prefix = f"{spec.persona_id_prefix}-seed-s{seg_idx}-b{batch_idx}"
            brief = PersonaGenerationBrief(
                client=spec.client,
                domain=spec.domain,
                business_problem=spec.business_problem,
                count=batch_count,
                anchor_overrides=ss.segment.anchor_overrides,
                persona_id_prefix=prefix,
                sarvam_enabled=spec.sarvam_enabled,
                auto_confirm=True,
                tier_override=seed_tier,
            )
            try:
                pg_result = await asyncio.wait_for(
                    invoke_persona_generator(brief),
                    timeout=300.0,
                )
                seeds.extend(_deserialise_personas(pg_result.personas))
                logger.debug(
                    "    Seed batch s%d-b%d: %d/%d delivered",
                    seg_idx, batch_idx, len(_deserialise_personas(pg_result.personas)), batch_count,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "  Seed generation timed out after 300s (s%d b%d) — skipping",
                    seg_idx, batch_idx,
                )
                warnings.append(f"Seed s{seg_idx} b{batch_idx}: timed out after 300s")
            except Exception as exc:
                logger.error(
                    "  Seed generation failed (s%d b%d): %s: %s",
                    seg_idx, batch_idx, type(exc).__name__, exc,
                )
                warnings.append(f"Seed s{seg_idx} b{batch_idx}: {type(exc).__name__}: {exc}")

        logger.info("  Segment %d/%d seeds done: %d/%d delivered",
                    seg_idx + 1, len(seed_segs), len(seeds), ss.seed_count)
        return seeds

    seed_lists: list[list[PersonaRecord]] = list(await asyncio.gather(
        *[_generate_seeds(ss, i) for i, ss in enumerate(seed_segs)]
    ))

    total_seeds_delivered = sum(len(sl) for sl in seed_lists)
    logger.info("  Pass 1 complete: %d/%d seeds delivered.", total_seeds_delivered, seed_count)

    # ── Pass 2: expand variants in parallel across segments ───────────────────
    logger.info("  Pass 2: expanding %d variants from %d seeds…",
                spec.n_personas - seed_count, total_seeds_delivered)

    variant_generator = VariantGenerator(llm_client=llm_client)

    async def _expand_variants(
        ss: SeedSegment,
        seg_idx: int,
        seeds: list[PersonaRecord],
        seed_cost: float,
    ) -> SegmentGenerationResult:
        """Expand variants for all seeds in one segment, then assemble result."""
        if not seeds:
            logger.warning("  Segment %d has no seeds — skipping variants.", seg_idx)
            return SegmentGenerationResult(
                segment=ss.segment,
                count_requested=ss.segment.count,
                count_delivered=0,
                cost_usd=0.0,
                personas=[],
                warnings=["No seeds delivered — variants skipped."],
            )

        all_personas: list[PersonaRecord] = list(seeds)  # seeds first
        variant_cost = 0.0
        warnings: list[str] = []

        for seed_idx, seed in enumerate(seeds):
            n_variants = ss.variant_count_for_seed(seed_idx)
            if n_variants == 0:
                continue

            prefix = f"{spec.persona_id_prefix}-var-s{seg_idx}-seed{seed_idx}"

            try:
                variants = await asyncio.wait_for(
                    variant_generator.expand(
                        seed=seed,
                        n=n_variants,
                        segment=ss.segment,
                        domain=spec.domain,
                        persona_id_prefix=prefix,
                        random_seed=hash(f"{run_id}-{seg_idx}-{seed_idx}") & 0xFFFFFF,
                    ),
                    timeout=120.0,
                )
                all_personas.extend(variants)
                # Haiku cost: ~$0.004 per variant (approx)
                variant_cost += n_variants * 0.004
            except asyncio.TimeoutError:
                logger.error(
                    "  Variant expansion timed out after 120s (s%d seed%d) — skipping",
                    seg_idx, seed_idx,
                )
                warnings.append(
                    f"Variant expansion s{seg_idx} seed{seed_idx}: timed out after 120s"
                )
            except Exception as exc:
                logger.error(
                    "  Variant expansion failed (s%d seed%d): %s: %s",
                    seg_idx, seed_idx, type(exc).__name__, exc,
                )
                warnings.append(
                    f"Variant expansion s{seg_idx} seed{seed_idx}: {type(exc).__name__}: {exc}"
                )

        total_cost = seed_cost + variant_cost
        delivered = len(all_personas)
        requested = ss.segment.count

        if delivered < requested:
            warnings.append(f"Segment {ss.label}: requested {requested}, delivered {delivered}")

        logger.info(
            "  Segment %d/%d done: %d/%d personas (seeds=%d variants=%d) $%.4f",
            seg_idx + 1, len(seed_segs), delivered, requested,
            len(seeds), delivered - len(seeds), total_cost,
        )

        sr = SegmentGenerationResult(
            segment=ss.segment,
            count_requested=requested,
            count_delivered=delivered,
            cost_usd=total_cost,
            personas=all_personas,
            warnings=warnings,
        )

        if on_segment_complete is not None:
            if asyncio.iscoroutinefunction(on_segment_complete):
                await on_segment_complete(sr)
            else:
                on_segment_complete(sr)

        return sr

    # Compute approximate seed cost per segment for attribution
    # (actual cost from PG not easily extractable per-segment; use estimate)
    seed_cost_per_persona = {"deep": 0.30, "signal": 0.15, "volume": 0.08}.get(seed_tier, 0.25)

    segment_results: list[SegmentGenerationResult] = list(await asyncio.gather(
        *[
            _expand_variants(
                ss=ss,
                seg_idx=i,
                seeds=seed_lists[i],
                seed_cost=len(seed_lists[i]) * seed_cost_per_persona,
            )
            for i, ss in enumerate(seed_segs)
        ]
    ))

    # ── Assemble cohort ───────────────────────────────────────────────────────
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

    # Store seeded-generation metadata in a way callers can access
    # CohortGenerationResult doesn't have a metadata dict — annotate the
    # result object directly (extra attribute on the dataclass).
    object.__setattr__(result, "_seeded_metadata", {
        "seed_count_requested": seed_count,
        "seed_count_actual":    total_seeds_delivered,
        "variant_count_actual": len(all_personas) - total_seeds_delivered,
        "seed_tier":            seed_tier,
    })

    logger.info("run_seeded_generation complete: %s", result.summary())

    # ── Parity check ──────────────────────────────────────────────────────────
    try:
        parity = validate_parity(all_personas)
        if parity.passed:
            logger.info("  Parity check PASSED (seeds=%d variants=%d)",
                        parity.n_seeds, parity.n_variants)
        else:
            logger.warning("  Parity check FAILED — demographic drift detected:\n%s",
                           parity.summary())
    except Exception as exc:
        logger.warning("  Parity check skipped: %s: %s", type(exc).__name__, exc)

    return result


def run_seeded_generation_sync(
    spec: PopulationSpec,
    **kwargs: Any,
) -> CohortGenerationResult:
    """Synchronous wrapper. Do not call from an active event loop."""
    return asyncio.run(run_seeded_generation(spec, **kwargs))
