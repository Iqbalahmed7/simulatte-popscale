# ADR-002: Seeded Generation — PopScale Owns Variant Expansion; PG Is Unchanged

**Status**: Accepted  
**Date**: 2026-04-16 (from SPEC_SEEDED_GENERATION.md)  
**Deciders**: Simulatte Tech Lead  

---

## Context

Generating 10,000 personas for a Niobe population study using the full Persona Generator (PG) pipeline costs approximately $2,500–$3,000 (Sonnet tier) or $1,000 (Haiku tier). This makes large-population studies economically impractical for exploratory research or hypothesis validation.

The underlying insight is that most personas in a population study do not need to be generated from scratch. A demographic segment (e.g., "Hindu, middle income, West Bengal") has a bounded psychological space. Once 5–10 high-quality seed personas are generated for that segment, additional personas can be produced more cheaply by *varying* the seeds rather than invoking the full PG pipeline.

The design question is: **where should variant generation live?**

---

## Decision

**PopScale owns variant generation entirely. PG is not modified.**

PopScale's `VariantGenerator` class in `popscale/generation/variant_generator.py` takes a seed `PersonaRecord` produced by PG and generates N variants by:
1. Varying demographics deterministically (age ±5, city rotation, household size ±1)
2. Perturbing continuous attributes with Gaussian noise (σ=0.08)
3. Recomputing `DerivedInsights` and `BehaviouralTendencies` deterministically from perturbed attributes (using PG's own `DerivedInsightsComputer` and `TendencyEstimator`)
4. Regenerating the narrative with a single Haiku call (~$0.0003 per variant)
5. Assembling `CoreMemory` deterministically

PG is called only for seeds, using the same `invoke_persona_generator()` call path as before. The `PersonaRecord` schema gains two new optional fields: `seed_persona_id` and `generation_mode`.

---

## Alternatives Considered

### Option A — Add a "variant" mode to PG
Add a `generation_mode: "variant"` flag to `PersonaGenerationBrief`. PG internally decides how to handle cheap variant generation.

**Rejected**: PG's responsibility is to generate a high-quality `PersonaRecord` when asked. Population-scale management (how many to ask for, whether to reuse seeds) belongs to the orchestration layer (PopScale). Adding variant logic to PG would couple PG to PopScale's cost-reduction concerns and would require PG to understand `seed_persona_id` linkage — a concept that only makes sense in a population context.

### Option B — Use PG's Haiku tier for all personas
Set `tier_override="volume"` with Haiku for all N personas. Cost drops from $2,500 to ~$600.

**Rejected**: This does not address the structural problem — independent generation still produces N personas with no relationship to each other. The seeded approach produces a coherent synthetic population where archetypes cluster around seeds, which is more representative of how real populations work (there are stable demographic and psychological types). Additionally, the cost target is $450, not $600.

### Option C — Pre-generate a persona registry; reuse across studies
Build a library of 10,000 pre-generated personas; for each study, sample from the library without any new PG calls.

**Rejected**: Registry maintenance is a separate concern addressed in a future spec. More importantly, re-using personas across studies biases results — the same "Rahul Kumar" appears in every West Bengal study. Fresh variants are needed to avoid systematic response bias from persona familiarity effects.

---

## Rationale for Chosen Design

1. **Separation of concerns**: PG generates quality personas. PopScale manages population composition. The seam remains clean.

2. **Backward compatibility**: `run_study()`, Niobe, and all downstream consumers receive a `list[PersonaRecord]`. Seeds and variants are indistinguishable from the consumer's perspective. No downstream changes required.

3. **Cost target achieved**: 200 seeds × $0.30 + 9,800 variants × $0.0003 + 10,000 simulations × $0.04 = $452.94 (vs. $2,900 full pipeline). ~84% cost reduction.

4. **Quality floor maintained**: Seeds are full-pipeline Sonnet/deep-tier personas. Variants inherit the seed's psychological profile (tension_seed, trust_anchor, decision_style, political_lean, religion) exactly. Only demographic surface features and continuous attribute values are varied. The parity validator (`parity_validator.py`) provides an automated check that variant demographics match seed demographics within 10pp.

5. **Reproducibility**: Variant generation is deterministic given the seed persona ID and variant index as the random seed. The same spec + same seeds → same variants.

---

## Consequences

### Positive
- Large population studies (500–50,000 personas) become economically viable.
- Variant personas maintain psychological coherence with their seeds (the population has archetypes).
- Full PG pipeline quality is preserved for seeds; variant quality is acceptable for population-level aggregate analysis.
- `CohortGenerationResult` shape is unchanged — no consumer updates needed.

### Negative
- **Variant city pool is India-only.** Non-India variants get incorrect city names (see Health Report M-2).
- **Variant decision_bullets are empty.** Seeds have rich decision bullets from PG's full pipeline; variants inherit none. For very deep single-persona analysis, variants are shallow.
- **Narrative quality is lower for variants.** One Haiku call vs. three Sonnet calls. Variant narratives are serviceable for population-level analysis but not appropriate for client-facing individual persona reports.
- **Parity check fires a warning, not an error.** Demographic drift above 10pp logs a warning but does not abort the study. A malformed variant generator could produce biased results silently.
- **`_seeded_metadata` is an untyped dict on the result.** (See Health Report M-1.)

### Acceptance criteria (from SPEC_SEEDED_GENERATION.md §13)
Before using seeded generation in a client study:
- Distribution parity test: <5% difference on `decision_style`, `trust_anchor`, `risk_appetite` distributions between full and seeded 200-persona cohorts.
- Simulation response parity: <8% difference on aggregate choice distributions.
- Distinctiveness score ≥ 0.30.
- Mean `consistency_score` within 10 points of seed cohort.
