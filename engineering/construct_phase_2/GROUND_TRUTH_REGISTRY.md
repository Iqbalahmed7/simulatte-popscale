# Ground Truth Registry

**Purpose:** This is the catalog of real-world outcomes Simulatte will be calibrated and scored against. Without these, prediction quality is unmeasurable. With them, every backcast becomes a unit test for the engine.

**Status:** Acquisition begins Week 1 (parallel to Phase 0). Full registry needed by Week 6 (start of Phase 3).

---

## 1. Why this exists

Aaru's strategic moat is not architecture — it is having **calibrated their engine against known election outcomes** and being able to demonstrate it. We have not done this. Until we do, "deeper reasoning" is an unfalsified claim.

This registry is the foundation of the prediction-quality bet. Treat acquiring these datasets as P0.

---

## 2. The four target benchmarks

### 2.1 US Presidential 2024 (Tier 1 — strategic)

**Why:** This is Aaru's home turf. Beating their published benchmark is the single most credible proof of the depth-of-reasoning hypothesis.

| Field | Value |
|---|---|
| Election | 2024 US Presidential |
| Date | November 5, 2024 |
| Granularity needed | County-level (3,143 counties) |
| Outcome columns | Trump %, Harris %, Other %, Total turnout |
| Key demographic crosstabs | Race, age, education, urban/rural, religion (where available) |
| Source | MIT Election Data and Science Lab; Cook Political Report |
| Acquisition | Public CSV — direct download |
| Lead time | 1 day |
| Owner | Cursor |
| Storage path | `popscale/calibration/ground_truth/us_2024_pres/` |

**Acceptance:** A Python loader that returns `{county_fips → {trump_pct, harris_pct, other_pct, turnout}}` plus a county-level demographic enrichment join.

### 2.2 West Bengal Assembly 2021 (Tier 1 — domain validation)

**Why:** Validates the WB engine specifically. We have a 2026 forecast in production; calibrating against 2021 is the most direct test.

| Field | Value |
|---|---|
| Election | WB Vidhan Sabha 2021 |
| Date | March–April 2021 |
| Granularity needed | Constituency (294 seats) |
| Outcome columns | TMC %, BJP %, Left %, INC %, Others %, Winner, Margin |
| Key crosstabs | Cluster-level (map our 5 clusters to actual 2021 results) |
| Source | Election Commission of India (ECI) |
| Acquisition | Public CSV via ECI portal; manual scrape if needed |
| Lead time | 3–5 days (may need scraping) |
| Owner | Codex |
| Storage path | `popscale/calibration/ground_truth/wb_2021_assembly/` |

**Acceptance:** Constituency-level CSV plus a cluster-aggregation function that maps each of our 5 clusters (Murshidabad, Matua Belt, Jungle Mahal, Burdwan Industrial, Presidency Suburbs) to its constituent 2021 seats and aggregates results.

### 2.3 Indian Lok Sabha 2024 (Tier 2 — breadth check)

**Why:** Tests the engine on a national-scale election with 28 states' worth of regional variation. Mid-difficulty calibration target.

| Field | Value |
|---|---|
| Election | Lok Sabha 2024 |
| Date | April–June 2024 |
| Granularity needed | Constituency (543 seats); state aggregates |
| Outcome columns | INC %, BJP %, Regional party %, Vote share, Seat winners |
| Key crosstabs | State-level, urban/rural |
| Source | ECI; Lokniti-CSDS post-poll survey |
| Acquisition | Public CSV |
| Lead time | 2–3 days |
| Owner | Codex |
| Storage path | `popscale/calibration/ground_truth/india_2024_ls/` |

**Acceptance:** Constituency-level results + state aggregation.

### 2.4 Indian Lok Sabha 2019 (Tier 3 — trend stability)

**Why:** Allows us to test whether the engine's calibration is stable across time, or whether it overfits to recent elections.

| Field | Value |
|---|---|
| Election | Lok Sabha 2019 |
| Date | April–May 2019 |
| Granularity needed | Constituency (543 seats) |
| Outcome columns | Same as 2024 LS |
| Source | ECI archive |
| Acquisition | Public CSV |
| Lead time | 2–3 days |
| Owner | Codex |
| Storage path | `popscale/calibration/ground_truth/india_2019_ls/` |

**Acceptance:** Same loader interface as 2024 LS.

---

## 3. Schema (all benchmarks)

Every ground truth dataset must conform to:

```python
GroundTruth:
  election_id: str          # canonical id, e.g. "wb_2021_assembly"
  date: str                 # ISO date
  granularity: str          # "county" | "constituency" | "ward"
  units: list[GroundTruthUnit]

GroundTruthUnit:
  unit_id: str              # county FIPS / constituency code
  unit_name: str            # human-readable
  outcomes: dict[str, float]   # {party_id → vote_share_pct}
  winner: str
  margin_pct: float
  turnout_pct: float | None
  demographic_enrichment: dict | None   # joined demographics if available
  metadata: dict | None
```

A loader function `load_ground_truth(election_id) → GroundTruth` lives in `popscale/calibration/loaders.py`. Backcast harness (Phase 3) only ever calls this loader, never reads files directly.

---

## 4. Demographic enrichment

For each ground truth unit, where available, attach demographic context that matches Simulatte's persona attribute schema:

| Attribute | Required for backcast? |
|---|---|
| Age distribution | Yes |
| Income/economic class distribution | Yes |
| Education distribution | Yes |
| Religion / caste distribution | Yes (India), Religion only (US) |
| Urban/rural classification | Yes |
| Linguistic / ethnic majority | Optional |

**Why this matters:** The persona generator needs to produce a synthetic population whose demographic distribution matches the actual unit, otherwise comparison is meaningless. Bias decomposition (Phase 3C) reads this enrichment to attribute errors to specific demographic cells.

---

## 5. Calibration cadence

| Phase | What happens with ground truth |
|---|---|
| Phase 3A (Week 6) | Build harness; 1 backcast per benchmark to validate plumbing |
| Phase 3B (Week 7) | Compute baseline metrics; document baseline error |
| Phase 3C (Weeks 7–8) | Run 5 backcasts per benchmark with stratified persona seeds; build bias decomposition |
| Phase 3D (Weeks 8–9) | Each calibration iteration runs all 4 benchmarks; track delta vs baseline |
| Phase 3E (Week 10) | Final scored run; publish results |
| Phase 4+ | New benchmarks added as available (state elections, opinion polls, brand-tracking surveys) |

---

## 6. Acquisition plan (Week 1)

| Day | Task | Owner |
|---|---|---|
| Day 1 | Download US 2024 county-level results from MIT EDSL | Cursor |
| Day 1 | File RTI / scrape ECI for WB 2021 constituency CSV | Codex |
| Day 2 | Download India 2024 LS from ECI | Codex |
| Day 2 | Download India 2019 LS from ECI archive | Codex |
| Day 3 | Acquire US 2024 demographic enrichment (Census 5-year ACS county profiles) | Cursor |
| Day 3-4 | Acquire India demographic enrichment (Census 2011 + post-poll surveys for behavioral) | Codex |
| Day 5 | Implement `load_ground_truth()` for all 4 benchmarks; test loaders | Both |

**Gate (end of Week 1):** All 4 loaders pass a smoke test (`load_ground_truth("wb_2021_assembly").units[0]` returns valid object with all required fields).

---

## 7. Caveats and known limitations

- **India election demographic enrichment is weak.** Census 2011 is 15 years old; behavioral data comes from CSDS/Lokniti post-poll surveys which are sample-based. We treat these as approximate priors, not ground truth.
- **US county-level demographics are stable but coarse.** ACS 5-year is reliable for population profile but says nothing about turnout drivers. Where possible, supplement with Catalist or L2 voter file aggregates (paid; deferred until budget allows).
- **Margin of measurement error in vote shares is ~0.1pp at constituency level (rounding).** We treat anything within 1pp of ground truth as "matched" in scoring.
- **2024 US is the politically hottest benchmark.** Aaru claims have been disputed by analysts (e.g., Nate Silver). Our calibration must be defensible — we publish methodology and confidence intervals, not just point estimates.

---

## 8. Storage and access

```
PopScale/
└── calibration/
    ├── ground_truth/
    │   ├── us_2024_pres/
    │   │   ├── results_county.csv
    │   │   ├── demographics_county.csv
    │   │   └── README.md (provenance, last_updated, schema notes)
    │   ├── wb_2021_assembly/
    │   ├── india_2024_ls/
    │   └── india_2019_ls/
    ├── loaders.py             # canonical load_ground_truth()
    ├── enrichment.py          # demographic join helpers
    └── tests/
        └── test_loaders.py
```

Ground truth files are version-controlled. Updates require a PR with provenance notes in the README.

---

## 9. What we are NOT calibrating against in Phase 2

- Opinion polls (different signal — beliefs vs revealed votes; saved for later)
- Brand purchase / consumer survey data (out of scope until Phase 3 expands domains)
- Local elections / municipal results (insufficient demographic enrichment)
- Exit polls (sampled; treat as prior, not ground truth)

These all become useful in Phase 3+ when we generalise beyond political prediction.
