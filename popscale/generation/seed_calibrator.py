"""seed_calibrator — distribute seed personas proportionally across demographic segments.

Given a list of calibrated PersonaSegments and a desired seed_count, produces a
list of SeedSegments that describe:
  - How many deep seed personas to generate per segment
  - How many variant personas to expand from those seeds
  - The per-seed variant assignment (floor + overflow distribution)

Design constraints:
  - seeds + variants = segment.count for every segment  →  sum = spec.n_personas
  - sum(seed_counts) = seed_count  (exact, after rounding correction)
  - Every segment gets ≥ 1 seed (regardless of proportion)
  - The first `extra_seeds` seeds in a segment each get one extra variant

Usage::

    from popscale.generation.seed_calibrator import distribute_seeds
    from popscale.calibration.calibrator import calibrate
    from popscale.calibration.population_spec import PopulationSpec

    spec = PopulationSpec(
        state="west_bengal", n_personas=10_000, domain="policy",
        business_problem="Electoral sentiment study.", stratify_by_religion=True,
    )
    segments = calibrate(spec)
    seed_segments = distribute_seeds(segments, seed_count=200)
    for ss in seed_segments:
        print(f"{ss.label}: {ss.seed_count} seeds → {ss.variant_count} variants "
              f"({ss.variants_per_seed}+{ss.extra_seeds})")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

from ..calibration.calibrator import PersonaSegment  # noqa: E402


# ── SeedSegment ───────────────────────────────────────────────────────────────

@dataclass
class SeedSegment:
    """Seed + variant assignment for one demographic segment.

    Attributes:
        segment:          The original PersonaSegment from calibrate().
        seed_count:       Deep personas to generate via full PG pipeline.
        variant_count:    Total variants to expand from the segment's seeds.
        variants_per_seed:Base variants per seed (floor division).
        extra_seeds:      First N seeds get `variants_per_seed + 1` variants.
                          (seed indices 0 .. extra_seeds-1)
        label:            Human-readable label (mirrors segment.label).
        proportion:       Segment proportion of total population.
    """
    segment: PersonaSegment
    seed_count: int
    variant_count: int
    variants_per_seed: int
    extra_seeds: int
    label: str
    proportion: float

    @property
    def total_count(self) -> int:
        """seeds + variants = segment.count (sanity check)."""
        return self.seed_count + self.variant_count

    def variant_count_for_seed(self, seed_index: int) -> int:
        """Return the number of variants to generate for seed at index i."""
        if seed_index < self.extra_seeds:
            return self.variants_per_seed + 1
        return self.variants_per_seed


# ── Public API ────────────────────────────────────────────────────────────────

def distribute_seeds(
    segments: list[PersonaSegment],
    seed_count: int,
) -> list[SeedSegment]:
    """Distribute seed_count seeds proportionally across calibrated segments.

    For each segment:
      - seed_count_i = max(1, round(seed_count × proportion_i))
      - variant_count_i = segment.count - seed_count_i
      - variants_per_seed = variant_count_i // seed_count_i
      - extra_seeds = variant_count_i % seed_count_i

    After proportional assignment, the total seed count is adjusted to equal
    exactly `seed_count` by scaling the largest segment.

    Args:
        segments:    Calibrated segments from calibrate(). Must be non-empty.
        seed_count:  Total number of deep seed personas to generate.

    Returns:
        List of SeedSegment objects in the same order as segments.

    Raises:
        ValueError: If seed_count < len(segments) (can't give each segment ≥1 seed).
        ValueError: If seed_count > total personas across all segments.
    """
    if not segments:
        raise ValueError("segments must be non-empty")

    n_personas = sum(s.count for s in segments)

    if seed_count < len(segments):
        raise ValueError(
            f"seed_count ({seed_count}) must be ≥ number of segments ({len(segments)}) "
            "so each segment can have at least 1 seed."
        )
    if seed_count > n_personas:
        raise ValueError(
            f"seed_count ({seed_count}) cannot exceed n_personas ({n_personas})."
        )

    # ── Step 1: proportional assignment (floor, ≥1 per segment) ──────────────
    raw_seeds = [max(1, round(seed_count * s.proportion)) for s in segments]

    # ── Step 2: correction to hit exact seed_count ────────────────────────────
    raw_seeds = _correct_total(raw_seeds, seed_count, segments)

    # ── Step 3: clamp each segment's seeds to [1, segment.count] ─────────────
    for i, s in enumerate(segments):
        raw_seeds[i] = max(1, min(s.count, raw_seeds[i]))

    # After clamping, re-correct (clamping may have shifted total again)
    raw_seeds = _correct_total(raw_seeds, seed_count, segments)

    # ── Step 4: build SeedSegments ────────────────────────────────────────────
    result: list[SeedSegment] = []
    for i, (s, n_seeds) in enumerate(zip(segments, raw_seeds)):
        n_variants = s.count - n_seeds
        if n_seeds == 0:
            n_seeds = 1
            n_variants = max(0, s.count - 1)

        if n_seeds > 0:
            vps = n_variants // n_seeds
            extra = n_variants % n_seeds
        else:
            vps = 0
            extra = 0

        result.append(SeedSegment(
            segment=s,
            seed_count=n_seeds,
            variant_count=n_variants,
            variants_per_seed=vps,
            extra_seeds=extra,
            label=s.label,
            proportion=s.proportion,
        ))

    logger.info(
        "distribute_seeds | total_personas=%d | seed_count=%d | segments=%d",
        n_personas, sum(ss.seed_count for ss in result), len(result),
    )
    for ss in result:
        logger.debug(
            "  %-35s seeds=%d  variants=%d  vps=%d+%d",
            ss.label, ss.seed_count, ss.variant_count, ss.variants_per_seed, ss.extra_seeds,
        )

    return result


# ── Internal helpers ──────────────────────────────────────────────────────────

def _correct_total(
    raw_seeds: list[int],
    target: int,
    segments: list[PersonaSegment],
) -> list[int]:
    """Adjust raw_seeds so they sum to exactly target.

    Strategy: repeatedly increment/decrement the segment with the largest count
    that still has headroom (won't go below 1 or above segment.count).
    """
    current = sum(raw_seeds)
    if current == target:
        return raw_seeds

    seeds = list(raw_seeds)
    delta = 1 if current < target else -1
    steps = abs(target - current)

    for _ in range(steps):
        # Find the segment with most headroom in the direction we need
        if delta == 1:
            # Need to increment: pick segment furthest below its segment.count
            candidates = [
                (i, segments[i].count - seeds[i])
                for i in range(len(seeds))
                if seeds[i] < segments[i].count
            ]
        else:
            # Need to decrement: pick segment with most seeds above 1
            candidates = [
                (i, seeds[i] - 1)
                for i in range(len(seeds))
                if seeds[i] > 1
            ]

        if not candidates:
            break  # nowhere to go — leave as-is

        # Pick the candidate with the most headroom (largest segment first)
        best_i = max(candidates, key=lambda x: x[1])[0]
        seeds[best_i] += delta

    return seeds
