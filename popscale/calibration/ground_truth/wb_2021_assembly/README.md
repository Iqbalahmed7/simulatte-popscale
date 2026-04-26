# West Bengal 2021 Assembly Election

## Metadata

- **Election Date:** April 27, 2021
- **Granularity:** Constituency (294 seats)
- **Data Retrieved:** April 26, 2026
- **Source:** Election Commission of India (ECI) - https://results.eci.gov.in/Result2021/

## Dataset Status

**STUB DATASET** — Placeholder with representative sample data (10 constituencies from North Bengal and other clusters).

Real data should be retrieved from ECI official results portal. This stub includes test data only.

## Schema

### results_constituency.csv

```
constituency_code  : ECI constituency code (e.g., WB001)
constituency_name  : Human-readable constituency name
tmc_pct            : Trinamool Congress vote share (0-100)
bjp_pct            : Bharatiya Janata Party vote share (0-100)
left_pct           : Left Front (CPI+CPM) combined vote share (0-100)
congress_pct       : Indian National Congress vote share (0-100)
others_pct         : Other parties/independent vote share (0-100)
total_votes        : Total votes cast
winner             : Winning party (TMC, BJP, Left, Congress, Others)
```

### cluster_mapping.csv

Maps each constituency to one of 5 Simulatte study clusters:
- `murshidabad`: 22 seats
- `matua_belt`: 40 seats (Nadia + North 24 Parganas)
- `jungle_mahal`: 50 seats (tribal belt)
- `burdwan_industrial`: 25 seats
- `presidency_suburbs`: 40 seats

Format:
```
constituency_code,constituency_name,cluster_id
```

## Normalization

Vote shares are already normalized to 0-100 scale. Winner is determined by highest vote share.

## Cluster Aggregation

Use `popscale.calibration.enrichment.aggregate_to_clusters()` to map constituency results to cluster level:

```python
from popscale.calibration.loaders import load_ground_truth
from popscale.calibration.enrichment import aggregate_to_clusters
from pathlib import Path

gt = load_ground_truth("wb_2021_assembly")
clusters = aggregate_to_clusters(
    gt,
    Path("popscale/calibration/ground_truth/wb_2021_assembly/cluster_mapping.csv")
)
# Returns: {cluster_id: {party: vote_share, ...}}
```

## Known Limitations

1. Stub data: Only 10 sample constituencies included for testing
2. Real dataset must include all 294 constituencies
3. No demographic enrichment included (can be joined from Census 2011)
4. cluster_mapping.csv is placeholder; must be built from cluster_definitions.py

## Expected Parties

- `tmc_pct`: Trinamool Congress (dominant)
- `bjp_pct`: Bharatiya Janata Party
- `left_pct`: Left Front (CPI, CPM, etc.)
- `congress_pct`: Indian National Congress
- `others_pct`: AIMIM, ISF, AJUP, independent candidates, etc.

## Files

- `results_constituency.csv` — Constituency-level results (294 seats)
- `cluster_mapping.csv` — Mapping constituencies to 5 study clusters
- `README.md` — This file

## Next Steps

1. Acquire real ECI constituency data for all 294 seats
2. Build cluster_mapping.csv from `benchmarks/wb_2026/constituency/cluster_definitions.py`
3. Enrich with Census 2011 demographic data where available
