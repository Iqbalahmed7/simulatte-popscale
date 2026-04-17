"""parity_validator — demographic parity check between seed and variant personas.

After seeded generation, this module verifies that the variant population's
demographic distribution matches the seed population within acceptable thresholds.
A large divergence indicates a bug in variant generation (e.g. age drift, urban
tier concentration).

Also checks that every variant has a valid seed_persona_id pointing to a known
seed in the cohort.

Usage::

    from popscale.generation.parity_validator import validate_parity, ParityReport

    report = validate_parity(cohort.personas, threshold=0.10)
    if not report.passed:
        for dim, dp in report.dimensions.items():
            if not dp.passed:
                print(f"FAIL {dim}: max_deviation={dp.max_abs_deviation:.3f}")
    print(report.summary())
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

_PG_ROOT = Path(__file__).parents[4] / "Persona Generator"
if str(_PG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PG_ROOT))

from src.schema.persona import PersonaRecord  # noqa: E402


# ── Age banding ───────────────────────────────────────────────────────────────

def _age_band(age: int) -> str:
    if age <= 25:
        return "18-25"
    elif age <= 35:
        return "26-35"
    elif age <= 50:
        return "36-50"
    elif age <= 65:
        return "51-65"
    return "65+"


# ── DimensionParity ───────────────────────────────────────────────────────────

@dataclass
class DimensionParity:
    """Parity result for one demographic dimension.

    Attributes:
        dimension:         Name of the dimension (e.g. "age_band").
        seed_dist:         Fractional distribution over categories (seeds only).
        variant_dist:      Fractional distribution over categories (variants only).
        max_abs_deviation: Max |seed_fraction - variant_fraction| across categories.
        threshold:         The pass/fail threshold (default 0.10 = 10pp).
        passed:            True if max_abs_deviation <= threshold.
        n_seeds:           Number of seed personas used in this dimension.
        n_variants:        Number of variant personas used.
    """
    dimension: str
    seed_dist: dict[str, float]
    variant_dist: dict[str, float]
    max_abs_deviation: float
    threshold: float
    passed: bool
    n_seeds: int
    n_variants: int

    def worst_category(self) -> tuple[str, float]:
        """Return (category, deviation) for the worst-diverging category."""
        all_cats = set(self.seed_dist) | set(self.variant_dist)
        worst = max(
            all_cats,
            key=lambda c: abs(self.seed_dist.get(c, 0.0) - self.variant_dist.get(c, 0.0)),
        )
        return worst, abs(self.seed_dist.get(worst, 0.0) - self.variant_dist.get(worst, 0.0))

    def to_dict(self) -> dict:
        return {
            "dimension":         self.dimension,
            "seed_dist":         self.seed_dist,
            "variant_dist":      self.variant_dist,
            "max_abs_deviation": round(self.max_abs_deviation, 4),
            "threshold":         self.threshold,
            "passed":            self.passed,
            "n_seeds":           self.n_seeds,
            "n_variants":        self.n_variants,
        }


# ── LinkageCheck ──────────────────────────────────────────────────────────────

@dataclass
class LinkageCheck:
    """Result of verifying seed_persona_id linkage for all variants.

    Attributes:
        n_variants:         Total variant personas checked.
        n_missing_id:       Variants with seed_persona_id is None.
        n_broken_links:     Variants whose seed_persona_id doesn't match any seed.
        broken_persona_ids: Persona IDs with broken links (up to 20).
        passed:             True if n_missing_id == 0 and n_broken_links == 0.
    """
    n_variants: int
    n_missing_id: int
    n_broken_links: int
    broken_persona_ids: list[str]
    passed: bool

    def to_dict(self) -> dict:
        return {
            "n_variants":        self.n_variants,
            "n_missing_id":      self.n_missing_id,
            "n_broken_links":    self.n_broken_links,
            "broken_persona_ids": self.broken_persona_ids,
            "passed":            self.passed,
        }


# ── ParityReport ──────────────────────────────────────────────────────────────

@dataclass
class ParityReport:
    """Full parity report for a seeded cohort.

    Attributes:
        n_seeds:     Number of seed personas.
        n_variants:  Number of variant personas.
        threshold:   The deviation threshold used.
        dimensions:  DimensionParity per checked dimension.
        linkage:     Seed linkage check result.
        passed:      True if all dimensions pass AND linkage passes.
    """
    n_seeds: int
    n_variants: int
    threshold: float
    dimensions: dict[str, DimensionParity]
    linkage: LinkageCheck
    passed: bool

    def summary(self) -> str:
        lines = [
            f"ParityReport: {self.n_seeds} seeds / {self.n_variants} variants "
            f"| threshold={self.threshold:.0%} | {'PASS' if self.passed else 'FAIL'}"
        ]
        for name, dp in self.dimensions.items():
            cat, dev = dp.worst_category()
            status = "PASS" if dp.passed else "FAIL"
            lines.append(
                f"  [{status}] {name}: max_dev={dp.max_abs_deviation:.3f} "
                f"(worst: {cat} seed={dp.seed_dist.get(cat, 0):.2f} "
                f"variant={dp.variant_dist.get(cat, 0):.2f})"
            )
        link_status = "PASS" if self.linkage.passed else "FAIL"
        lines.append(
            f"  [{link_status}] linkage: missing={self.linkage.n_missing_id} "
            f"broken={self.linkage.n_broken_links}"
        )
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "n_seeds":    self.n_seeds,
            "n_variants": self.n_variants,
            "threshold":  self.threshold,
            "passed":     self.passed,
            "dimensions": {k: v.to_dict() for k, v in self.dimensions.items()},
            "linkage":    self.linkage.to_dict(),
        }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _fractional_dist(values: list[str]) -> dict[str, float]:
    """Convert a list of category values to a fractional distribution dict."""
    if not values:
        return {}
    counts: dict[str, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    n = len(values)
    return {k: round(c / n, 6) for k, c in sorted(counts.items())}


def _max_deviation(d1: dict[str, float], d2: dict[str, float]) -> float:
    """Max absolute difference across all categories present in either dist."""
    all_cats = set(d1) | set(d2)
    if not all_cats:
        return 0.0
    return max(abs(d1.get(c, 0.0) - d2.get(c, 0.0)) for c in all_cats)


def _check_dimension(
    name: str,
    seed_values: list[str],
    variant_values: list[str],
    threshold: float,
) -> DimensionParity:
    seed_dist    = _fractional_dist(seed_values)
    variant_dist = _fractional_dist(variant_values)
    dev          = _max_deviation(seed_dist, variant_dist)
    return DimensionParity(
        dimension=name,
        seed_dist=seed_dist,
        variant_dist=variant_dist,
        max_abs_deviation=dev,
        threshold=threshold,
        passed=dev <= threshold,
        n_seeds=len(seed_values),
        n_variants=len(variant_values),
    )


def _check_linkage(
    seeds: list[PersonaRecord],
    variants: list[PersonaRecord],
) -> LinkageCheck:
    seed_ids = {p.persona_id for p in seeds}
    n_missing   = 0
    n_broken    = 0
    broken_ids: list[str] = []

    for v in variants:
        if v.seed_persona_id is None:
            n_missing += 1
            if len(broken_ids) < 20:
                broken_ids.append(v.persona_id)
        elif v.seed_persona_id not in seed_ids:
            n_broken += 1
            if len(broken_ids) < 20:
                broken_ids.append(v.persona_id)

    return LinkageCheck(
        n_variants=len(variants),
        n_missing_id=n_missing,
        n_broken_links=n_broken,
        broken_persona_ids=broken_ids,
        passed=(n_missing == 0 and n_broken == 0),
    )


# ── Public API ────────────────────────────────────────────────────────────────

def validate_parity(
    personas: list[PersonaRecord],
    *,
    threshold: float = 0.10,
) -> ParityReport:
    """Run demographic parity and linkage checks on a seeded cohort.

    Splits personas into seeds (generation_mode=="full") and variants
    (generation_mode=="variant"), then compares distributions across:
      - age_band  (18-25 / 26-35 / 36-50 / 51-65 / 65+)
      - gender
      - urban_tier
      - income_bracket
      - life_stage

    Also checks that every variant's seed_persona_id references a real seed.

    Args:
        personas:   Full cohort (seeds + variants combined).
        threshold:  Max acceptable absolute deviation per dimension (default 10pp).

    Returns:
        ParityReport with per-dimension results and overall pass/fail.

    Raises:
        ValueError: If personas list is empty.
        ValueError: If no variants found (cohort looks non-seeded).
    """
    if not personas:
        raise ValueError("personas list must be non-empty")

    seeds    = [p for p in personas if p.generation_mode == "full"]
    variants = [p for p in personas if p.generation_mode == "variant"]

    if not variants:
        raise ValueError(
            "No variant personas found (generation_mode='variant'). "
            "validate_parity() requires a seeded cohort."
        )
    if not seeds:
        raise ValueError("No seed personas found (generation_mode='full').")

    # ── Dimension extractors ──────────────────────────────────────────────────
    def _extract(personas: list[PersonaRecord], dim: str) -> list[str]:
        da = [p.demographic_anchor for p in personas]
        if dim == "age_band":
            return [_age_band(a.age) for a in da]
        elif dim == "gender":
            return [str(a.gender) for a in da]
        elif dim == "urban_tier":
            return [str(a.location.urban_tier) for a in da]
        elif dim == "income_bracket":
            return [a.household.income_bracket for a in da]
        elif dim == "life_stage":
            return [a.life_stage for a in da]
        raise ValueError(f"Unknown dimension: {dim}")

    _DIMS = ["age_band", "gender", "urban_tier", "income_bracket", "life_stage"]

    dimensions: dict[str, DimensionParity] = {}
    for dim in _DIMS:
        dimensions[dim] = _check_dimension(
            name=dim,
            seed_values=_extract(seeds, dim),
            variant_values=_extract(variants, dim),
            threshold=threshold,
        )

    linkage = _check_linkage(seeds, variants)

    all_passed = all(dp.passed for dp in dimensions.values()) and linkage.passed

    return ParityReport(
        n_seeds=len(seeds),
        n_variants=len(variants),
        threshold=threshold,
        dimensions=dimensions,
        linkage=linkage,
        passed=all_passed,
    )
