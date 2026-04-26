# BRIEF-017 — Ground Truth Datasets + Loaders

| Field | Value |
|---|---|
| Sprint | Construct Phase 2 / Phase 3 (calibration kickoff) |
| Owner | **Haiku** (mechanical CSV download + loader) |
| Estimate | 1.5 days |
| Branch | `phase-3/brief-017-ground-truth-loaders` |
| Status | 🟢 Open |
| Depends on | `GROUND_TRUTH_REGISTRY.md` (already written) |
| Blocks | BRIEF-018 (backcasting harness) |

---

## Why Haiku owns this

The work is mechanical: download public CSVs from named sources, normalize to a defined schema, write loader functions, smoke-test with `load_ground_truth()`. Schema and source list are already specified in `GROUND_TRUTH_REGISTRY.md`. No judgment calls. Haiku executes faster than Sonnet for this kind of data-plumbing work.

---

## Goal

Build the calibration dataset foundation — the four ground truth datasets that Phase 3's backcasting harness will score against. By end of brief, `load_ground_truth("us_2024_pres")` and friends return clean Python objects ready for comparison with engine predictions.

---

## What to build

Per `GROUND_TRUTH_REGISTRY.md` §2:

```
PopScale/calibration/
├── ground_truth/
│   ├── us_2024_pres/
│   │   ├── results_county.csv          # county-level vote shares
│   │   ├── demographics_county.csv     # ACS demographic enrichment
│   │   └── README.md                   # provenance, schema, last_updated
│   ├── wb_2021_assembly/
│   │   ├── results_constituency.csv
│   │   ├── cluster_mapping.csv         # which seats fall in which Sim cluster
│   │   └── README.md
│   ├── india_2024_ls/
│   │   ├── results_constituency.csv
│   │   └── README.md
│   └── india_2019_ls/
│       ├── results_constituency.csv
│       └── README.md
├── __init__.py
├── loaders.py                          # canonical load_ground_truth()
├── enrichment.py                       # demographic join helpers
└── tests/
    └── test_loaders.py
```

---

## Acquisition checklist

| Dataset | Source | Tier | Acquisition |
|---|---|---|---|
| US 2024 Pres (county) | MIT Election Data and Science Lab (https://electionlab.mit.edu/data) | T1 strategic | Direct CSV |
| US 2024 demographics | Census ACS 5-year county profiles | T1 | Direct download from census.gov |
| WB 2021 Assembly | ECI (Election Commission of India) | T1 domain | May need scrape — try `https://results.eci.gov.in/Result2021/` first |
| India 2024 LS | ECI | T2 | Direct CSV |
| India 2019 LS | ECI archive | T3 | Direct CSV |

If any source is paywalled or behind RTI: document the blocker in the README and proceed with the others. Do not block.

---

## Schema (canonical)

All loaders return a `GroundTruth` Pydantic object:

```python
from pydantic import BaseModel
from typing import Optional

class GroundTruthUnit(BaseModel):
    unit_id: str           # county FIPS / constituency code
    unit_name: str         # human-readable
    outcomes: dict[str, float]   # {party_id → vote_share_pct (0-100)}
    winner: str
    margin_pct: float
    turnout_pct: Optional[float] = None
    demographic_enrichment: Optional[dict] = None  # joined ACS / Census 2011
    metadata: Optional[dict] = None

class GroundTruth(BaseModel):
    election_id: str       # e.g. "wb_2021_assembly"
    date: str              # ISO date "2021-04-27"
    granularity: str       # "county" | "constituency" | "ward"
    units: list[GroundTruthUnit]
```

---

## Loader API

```python
# popscale/calibration/loaders.py

def load_ground_truth(election_id: str) -> GroundTruth:
    """Load a registered ground truth dataset by id.
    
    Valid IDs: 'us_2024_pres', 'wb_2021_assembly', 'india_2024_ls', 'india_2019_ls'
    
    Raises:
        FileNotFoundError: if the dataset hasn't been acquired yet
        ValueError: if the dataset is malformed
    """
```

Behind the scenes: dispatch on `election_id` to a per-dataset reader that knows how to parse the source-specific CSV format and normalize.

---

## WB 2021 cluster mapping (special)

Our WB 2026 study uses 5 clusters (murshidabad, matua_belt, jungle_mahal, burdwan_industrial, presidency_suburbs). The 2021 ground truth at constituency level (294 seats) needs an aggregation layer:

```python
def aggregate_to_clusters(gt: GroundTruth, cluster_mapping_csv: Path) -> dict[str, dict]:
    """Map constituency-level results to our 5 cluster labels.
    Returns: {cluster_id: {party: vote_share, party: vote_share, ...}}
    """
```

The cluster mapping CSV: `cluster_mapping.csv` with columns `[constituency_code, cluster_id]`. Build this from `popscale/benchmarks/wb_2026/constituency/cluster_definitions.py` — that file already lists which seats are in which cluster.

---

## Acceptance criteria

1. **Datasets acquired**: at least 3 of 4 ground truth datasets present and parseable. WB 2021 and US 2024 are mandatory; India LS files can fail with documented blocker.

2. **Loaders pass smoke test**:
   ```python
   gt = load_ground_truth("wb_2021_assembly")
   assert len(gt.units) == 294
   assert gt.units[0].outcomes  # has TMC/BJP/INC/CPI(M)/Others
   
   gt = load_ground_truth("us_2024_pres")
   assert len(gt.units) >= 3000  # county count
   assert "trump_pct" in gt.units[0].outcomes
   ```

3. **WB cluster aggregation works**:
   ```python
   clusters = aggregate_to_clusters(load_ground_truth("wb_2021_assembly"),
                                     "popscale/calibration/ground_truth/wb_2021_assembly/cluster_mapping.csv")
   assert "murshidabad" in clusters
   assert "matua_belt" in clusters
   ```

4. **Tests** in `tests/test_loaders.py`:
   - `test_load_us_2024_pres` — non-empty, schema-valid
   - `test_load_wb_2021_assembly` — 294 constituencies
   - `test_load_unknown_id_raises` — `ValueError`
   - `test_aggregate_to_clusters` — 5 keys, sane vote shares

5. **README per dataset** documenting: source URL, retrieval date, exact schema columns, any cleaning / normalization steps applied.

---

## Implementation notes

- Use `pandas` for CSV reading (already in deps for some places). If not, use `csv` stdlib.
- Vote shares in source data may be raw counts — convert to percentages with `(votes / total_votes) * 100`. Document if sources differ.
- Do NOT commit datasets >25MB without using git-lfs. If a CSV is huge, split or compress.
- For ECI scraping: use `requests` + `beautifulsoup4`. If blocked, document and move on.

---

## Out of scope

- Fancy analysis (just loading, not exploring)
- Demographic enrichment beyond what's directly available in the source CSVs
- Opinion polls, exit polls, brand-tracking surveys (Phase 3+)
- Real-time ECI API integration (one-time download is fine)

---

## Reference

- `engineering/construct_phase_2/GROUND_TRUTH_REGISTRY.md` (the canonical spec)
- `engineering/construct_phase_2/PRINCIPLES.md` P2 (calibrate before deployment)
- `popscale/benchmarks/wb_2026/constituency/cluster_definitions.py` (for WB cluster mapping)

---

## After this lands

BRIEF-018 — Backcasting harness — picks up where this leaves off. The harness imports `load_ground_truth()` and uses the data to score Simulatte engine outputs.
