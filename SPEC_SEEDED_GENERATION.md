# PopScale Seeded Generation — Technical Spec

**Status:** Approved for implementation  
**Author:** Tech Lead  
**Date:** 2026-04-16  

---

## 1. Problem Statement

PopScale currently generates every persona independently from scratch by calling PG
(`invoke_persona_generator`) for the full requested count. For a 10,000-persona Niobe
study this means 10,000 full Sonnet generation pipelines (~15–20 API calls each).

| Approach | Generation | Simulation | Total |
|---|---|---|---|
| Current (Sonnet, 10k) | $2,500 | $400 | **$2,900** |
| Tier-routing (Haiku, 10k) | $600 | $400 | **$1,000** |
| Seeded (target) | $50–150 | $400 | **$450–550** |

Beyond cost, independent generation means the 10,000 personas have no structural
relationship to each other. The population is a flat list of randomly sampled individuals,
not a coherent synthetic society with distinct but internally consistent archetypes.

---

## 2. Design Decision: Where Does Variant Generation Live?

**PopScale owns it entirely. PG is unchanged.**

PG's responsibility: generate a high-quality PersonaRecord when asked.  
PopScale's responsibility: decide how many to ask for and what to do with them.

PopScale already owns population calibration (how many personas per demographic segment).
Seeding is a natural extension of that responsibility — it decides:
- How many deep personas (seeds) to request from PG per segment
- How to expand each seed into N lightweight variants internally

PopScale calls PG for seeds exactly as it currently calls it. The variant generation
pipeline lives in `popscale/generation/variant_generator.py` and calls Haiku directly.
No new mode, flag, or concept is added to PG.

---

## 3. Architecture Overview

```
PopulationSpec(n_personas=10_000, seeding_mode=True, variants_per_seed=49)
    │
    ▼
SeedCalibrator.plan()
    → segments: [Hindu-low-rural (5500), Muslim-low-rural (2700), ...]
    → for each segment:
        seed_count  = ceil(segment.count / variants_per_seed)   ← how many to request from PG
        variant_count = segment.count - seed_count              ← how many PopScale generates

    ▼ (seeds)
invoke_persona_generator(count=seed_count, ...)   ← unchanged PG call, full Sonnet quality
    → list[PersonaRecord]  (seeds)

    ▼ (variants)
VariantGenerator.expand(seed, n=variants_per_seed, segment)
    → list[PersonaRecord]  (variants, generation_mode="variant")

    ▼
merge seeds + variants → full cohort
    → run_population_scenario(cohort)   ← unchanged PopScale simulation
```

---

## 4. New Components

### 4.1 `popscale/generation/variant_generator.py`

The core new file. A `VariantGenerator` class with a single public method:

```python
class VariantGenerator:
    def __init__(self, llm_client: AsyncAnthropic, model: str = "claude-haiku-4-5-20251001"):
        ...

    async def expand(
        self,
        seed: PersonaRecord,
        n: int,
        segment: PersonaSegment,
        domain: str,
    ) -> list[PersonaRecord]:
        """Generate n variants from a single seed persona."""
```

Internally calls `_generate_one_variant()` for each of the n variants, with a semaphore
limiting concurrency (reuses `PG_MAX_CONCURRENT_BUILDS` env var logic).

### 4.2 `popscale/generation/seed_calibrator.py`

Extends the calibration layer to produce a `SeedPlan` instead of raw `PersonaSegment` lists.

```python
@dataclass
class SegmentSeedPlan:
    segment: PersonaSegment
    seed_count: int         # how many to request from PG
    variant_count: int      # how many VariantGenerator will produce
    variants_per_seed: int  # derived from seed_count and variant_count

@dataclass
class SeedPlan:
    segments: list[SegmentSeedPlan]
    total_seeds: int
    total_variants: int
    estimated_cost_usd: float

def plan_seeds(spec: PopulationSpec) -> SeedPlan:
    ...
```

### 4.3 `popscale/generation/seeded_calibrated_generator.py`

Replaces `calibrated_generator.run_calibrated_generation` when `spec.seeding_mode=True`.
Orchestrates: calibrate → plan seeds → generate seeds via PG → expand variants via
VariantGenerator → merge → return `CohortGenerationResult`.

`calibrated_generator.run_calibrated_generation` gains a single check at the top:

```python
if spec.seeding_mode:
    from .seeded_calibrated_generator import run_seeded_generation
    return await run_seeded_generation(spec, run_id=run_id, ...)
```

All downstream callers (`study_runner.py`, Niobe, etc.) are unchanged.

---

## 5. PopulationSpec Changes

Three new optional fields added to `PopulationSpec`:

```python
seeding_mode: bool = False
# When True, use seed+variant generation instead of full generation for all personas.
# Recommended for n_personas >= 500.

variants_per_seed: int = 49
# How many variants each seed persona spawns.
# Total seeds per segment = ceil(segment.count / (variants_per_seed + 1))
# Default 49 means 1 seed + 49 variants = clusters of 50.

seed_quality_threshold: float = 60.0
# Minimum consistency_score for a seed to be used for expansion.
# Seeds below this are regenerated (up to 2 retries) or skipped.
```

---

## 6. Variant Generation Pipeline

This is the heart of the spec. For each variant, the steps are:

### Step 1 — Demographic Variation (no LLM, deterministic)

Take the seed's `demographic_anchor`. Apply controlled shifts within segment constraints:

| Field | Variation rule |
|---|---|
| `age` | ±0–7 years, clamped to segment age_min/age_max |
| `name` | New name sampled from same gender + region pool |
| `household.income_bracket` | Stay within segment income band; allow adjacent band 20% of time |
| `location.city` | Different city within same urban_tier and region |
| `employment` | Adjacent category 30% of time (e.g., salaried → self-employed) |
| `education` | Stay same 70%; adjacent level 30% |
| `life_stage` | Derived from new age; override if needed |
| `household.size` | ±1 person, min 1, max 8 |
| `worldview` | Inherit from seed; apply small jitter (±0.03 per dimension) |

All variation is deterministic given `(seed.persona_id, variant_index)` as a seed for
the random state. This makes variants reproducible.

### Step 2 — Attribute Inheritance with Perturbation (no LLM, deterministic)

Take the seed's `attributes` dict. For each attribute:

| Attribute type | Variation rule |
|---|---|
| `continuous` (float 0–1) | Gaussian noise N(0, 0.08); clamp to [0, 1]; source → "inherited" |
| `categorical` | Inherit as-is 80% of time; adjacent category 20%; source → "inherited" |

Attributes with `source="anchored"` are never varied (they are locked by the ICP spec).

### Step 3 — Derive Insights (no LLM, deterministic)

Run `DerivedInsightsComputer.compute(new_attributes, new_demographic_anchor)`.
This is the same deterministic computation used in full generation.
No inheritance from seed — computed fresh from the new attributes.

### Step 4 — Estimate Tendencies (no LLM, deterministic)

Run `TendencyEstimator.estimate(new_attributes, new_derived_insights)`.
Same deterministic computation as full generation.
Source on all tendency fields set to `"inherited"` (not "grounded") unless domain_data
grounding runs later.

### Step 5 — Generate Narrative (1 Haiku call)

The only LLM call for most variants.

**Prompt structure:**
```
System: You are generating a persona narrative variant.

Seed persona style reference:
[seed.narrative.first_person — first 100 words only]

New demographic profile:
[new demographic_anchor fields]

Psychological profile:
- Decision style: {new_derived_insights.decision_style}
- Trust anchor: {new_derived_insights.trust_anchor}
- Risk appetite: {new_derived_insights.risk_appetite}
- Primary value: {new_derived_insights.primary_value_orientation}

Write a first-person narrative (80–120 words) in the same voice and cultural register
as the seed. Different life details, same psychological character.
Then write a third-person summary (40–60 words).
```

Output: `Narrative(first_person, third_person, display_name)`.  
`display_name` is derived deterministically from new name + employment.

### Step 6 — Life Stories (no LLM, derived)

Not regenerated per variant. Three lightweight life story entries are constructed
deterministically from the seed's life story *patterns* (not specific events) combined
with the new demographic anchor:

- Event types (career_pivot, relationship, health) are inherited from seed
- Specific details (city, employer, age) are updated to match new demographics
- `lasting_impact` is copied from seed with name/location substitution

This is a string-interpolation step, not an LLM call.

### Step 7 — Core Memory Assembly (no LLM, deterministic)

Same `assemble_core_memory()` call as full generation, using new narrative +
new life_stories + new derived_insights.

### Step 8 — Construct PersonaRecord

```python
PersonaRecord(
    persona_id=f"{seed.persona_id}-v{variant_index:03d}",
    generated_at=datetime.now(utc),
    generator_version="2.1.0",
    domain=seed.domain,
    mode=seed.mode,
    demographic_anchor=new_demographic_anchor,
    life_stories=new_life_stories,
    attributes=new_attributes,
    derived_insights=new_derived_insights,
    behavioural_tendencies=new_tendencies,
    narrative=new_narrative,
    decision_bullets=[],          # not generated for variants
    memory=Memory(core=new_core, working=WorkingMemory()),
    # New field:
    seed_persona_id=seed.persona_id,
    generation_mode="variant",
)
```

**Total LLM calls per variant: 1 Haiku call** (narrative only).  
For comparison, full generation: 3 Sonnet calls (attributes, life stories, narrative).

---

## 7. Seed Selection and Quality

### How many seeds per segment

```
seed_count = ceil(segment.count / (variants_per_seed + 1))
```

With `variants_per_seed=49` and a segment of 5,500 personas:
```
seed_count = ceil(5500 / 50) = 110 seeds
variant_count = 5500 - 110 = 5,390 variants
```

### Seed placement

Seeds are requested from PG exactly as today: `invoke_persona_generator(count=seed_count,
anchor_overrides=segment.anchor_overrides)`. PG's round-robin demographic sampler
naturally distributes seeds across age/city/income within the segment.

No additional placement logic is needed — the calibrator already handles segment
stratification (religion × income), and PG's sampler handles within-segment diversity.

### Seed quality gate

After PG returns seeds, any seed with `consistency_score < seed_quality_threshold`
(default 60) is flagged. If flagged seeds exceed 20% of `seed_count` for a segment,
one retry is triggered for that segment only. If retry fails, flagged seeds are still
used (a weak seed is better than a missing cluster).

---

## 8. PersonaRecord Schema Addition

One new optional field added to `PersonaRecord`:

```python
seed_persona_id: str | None = None
# ID of the seed persona this variant was generated from.
# None for seeds and all non-variant personas.

generation_mode: Literal["full", "variant"] = "full"
# "full" = generated by PG's complete pipeline (default, backward compatible)
# "variant" = generated by PopScale's VariantGenerator
```

Downstream consumers (simulation, social runner, analytics) treat variant PersonaRecords
identically to full PersonaRecords. The field is metadata only — no behaviour changes.

---

## 9. Cost Model

### Per-variant cost

| Step | Model | Tokens (est.) | Cost |
|---|---|---|---|
| Narrative generation | Haiku | 400 in / 150 out | ~$0.0003 |
| All other steps | None (deterministic) | — | $0 |
| **Total per variant** | | | **~$0.0003** |

### Per-seed cost (unchanged from current)

Full PG generation: ~$0.25 per persona (Sonnet, existing estimate).

### Full cost for 10,000-persona study

```
seeds:    ceil(10,000 / 50) = 200 seeds × $0.25       =   $50.00
variants: 9,800 variants × $0.0003                    =    $2.94
simulation: 10,000 × $0.04                            =  $400.00
─────────────────────────────────────────────────────────────────
Total first run:                                        $452.94

With registry (seeds reused on repeat runs):
variants: 9,800 × $0.0003                             =    $2.94
simulation: 10,000 × $0.04                            =  $400.00
─────────────────────────────────────────────────────────────────
Total repeat run:                                       $402.94
```

### Comparison

| Approach | First run | Repeat run |
|---|---|---|
| Current (Sonnet, 10k) | $2,900 | $2,900 |
| Tier-routing (Haiku, 10k) | $1,000 | $1,000 |
| **Seeded (this spec)** | **$453** | **$403** |

**Savings vs current: 84% on first run, 86% on repeat runs.**

---

## 10. Integration Points

### `StudyConfig` (study_runner.py)

No change needed. `run_study()` calls `run_calibrated_generation(spec)` which internally
routes to seeded generation when `spec.seeding_mode=True`.

### `NiobeStudyRequest` / `_build_study_config`

Add one line to `_build_study_config` in both Niobe runners:

```python
spec = PopulationSpec(
    ...
    seeding_mode=request.n_personas >= 500,   # auto-enable for population-scale runs
    variants_per_seed=49,
)
```

### Simulation and social runner

Unchanged. They receive a flat `list[PersonaRecord]`. Seeds and variants are
indistinguishable from their perspective.

### Analytics and reporting

`StudyResult.cohort.segment_breakdown()` gains two new fields per segment:
`seeds_generated` and `variants_generated`. `CohortGenerationResult` gains
`seeding_mode: bool` and `total_seeds: int`.

---

## 11. What Variants Inherit vs Regenerate

| Field | Seeds | Variants |
|---|---|---|
| `demographic_anchor` | PG generates | Deterministically varied |
| `attributes` | PG generates (Sonnet) | Perturbed with Gaussian noise |
| `derived_insights` | Deterministic from attrs | Deterministic from new attrs |
| `life_stories` | PG generates (Sonnet) | Interpolated from seed pattern |
| `behavioural_tendencies` | Deterministic from attrs | Deterministic from new attrs |
| `narrative` | PG generates (Sonnet) | Haiku regenerates (1 call) |
| `core_memory` | Deterministic from above | Deterministic from above |
| `decision_bullets` | PG generates | Empty (not needed for pop. studies) |
| `worldview` | PG generates | Jittered from seed |
| `generation_mode` | "full" | "variant" |
| `seed_persona_id` | None | seed.persona_id |

---

## 12. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Variants cluster too tightly around seeds | Medium | Distributions narrow | Increase demographic variance; ensure seed_count covers full segment space |
| Narrative Haiku quality inconsistent | Low | Individual persona shallow | Narrative is used for simulation context, not client deliverable; acceptable |
| Attribute perturbation produces incoherent combos | Low | Gate failures | Existing G1/G7 gates catch incoherence; seed quality gate provides floor |
| Seed quality below threshold on first run | Low | Segment retry cost | Capped at 1 retry per segment; worst case falls back to using low-score seeds |
| distribution-level simulation accuracy | Medium | Wrong population signals | Validate against known benchmarks (Pew India 2023) before using in client studies |

---

## 13. Validation Plan

Before using seeded generation for any client study, run this validation:

1. **Distribution parity test** — Generate 200 personas with current approach (full Sonnet)
   and 200 with seeded approach (4 seeds × 49 variants each). Compare
   `decision_style_distribution`, `trust_anchor_distribution`, `risk_appetite_distribution`.
   Target: <5% difference on any bucket.

2. **Simulation response parity test** — Run the same scenario against both cohorts (200
   full vs 200 seeded). Compare response distributions. Target: <8% difference on
   aggregate choice distribution.

3. **Distinctiveness check** — Seeded cohort must achieve `distinctiveness_score >= 0.30`
   (same gate as full generation). If seeds are too similar, variants will also be similar.

4. **Consistency score floor** — Mean `consistency_score` across variant cohort should be
   within 10 points of seed cohort mean.

---

## 14. Build Sequence

### Phase 1 — VariantGenerator (standalone, 2–3 days)

- `popscale/generation/variant_generator.py` — full implementation
- Deterministic demographic variation
- Attribute perturbation
- Narrative generation (Haiku)
- Life story interpolation
- Core memory assembly
- Unit tests: `tests/test_variant_generator.py`

### Phase 2 — SeedCalibrator + seeded pipeline (1–2 days)

- `popscale/generation/seed_calibrator.py` — `plan_seeds()`
- `popscale/generation/seeded_calibrated_generator.py` — full pipeline
- `PopulationSpec` new fields: `seeding_mode`, `variants_per_seed`, `seed_quality_threshold`
- Router in `calibrated_generator.run_calibrated_generation`
- Unit tests: seed plan math, segment routing

### Phase 3 — Integration and Niobe wiring (1 day)

- `PersonaRecord` schema addition: `seed_persona_id`, `generation_mode`
- `CohortGenerationResult` additions: `total_seeds`, `seeding_mode`
- Both Niobe runners: auto-enable seeding for `n_personas >= 500`
- `StudyConfig`: optional `seeding_mode` pass-through
- Integration test: full 50-persona seeded run (1 seed × 49 variants per segment)

### Phase 4 — Validation (1–2 days)

- Run distribution parity test
- Run simulation response parity test
- Run distinctiveness and consistency checks
- Adjust variance parameters if needed
- Sign off for production use on Niobe

---

## 15. Out of Scope

- Seeded generation for PG CLI direct usage — PopScale only
- Variant generation for `deep` tier runs — seeds are always Sonnet, variants are Haiku
- Using variants as seeds for further expansion (no recursive seeding)
- Changing PG's internal generation pipeline in any way
- Cross-study seed sharing (that's the registry spec, a separate document)
