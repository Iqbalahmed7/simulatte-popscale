# India 2019 Lok Sabha Election (National Parliament)

## Metadata

- **Election Date:** May 23, 2019 (final count)
- **Granularity:** Constituency (543 seats)
- **Data Retrieved:** April 26, 2026
- **Source:** Election Commission of India (ECI) Archive - https://results.eci.gov.in/

## Dataset Status

**STUB DATASET** — Placeholder with representative sample data (10 constituencies from Madhya Pradesh and Rajasthan).

Real data should be retrieved from ECI official results archive. This stub includes test data only.

## Schema

```
constituency_code  : ECI constituency code (e.g., LS201)
constituency_name  : Human-readable constituency name
state              : State or union territory abbreviation
bjp_pct            : Bharatiya Janata Party vote share (0-100)
congress_pct       : Indian National Congress vote share (0-100)
regional_pct       : Regional parties combined vote share (0-100)
others_pct         : Other parties/independent vote share (0-100)
total_votes        : Total votes cast
winner             : Winning party (BJP, Congress, Regional, Others)
```

## Normalization

Vote shares are already normalized to 0-100 scale. Winner determined by highest vote share.

## Purpose

This dataset enables calibration stability analysis: comparing 2024 predictions against both 2019 and 2024 ground truth allows us to test whether the engine overfits to recent elections or generalizes across time.

## Known Limitations

1. Stub data: Only 10 sample constituencies for testing
2. Real dataset must include all 543 constituencies
3. Regional parties are combined; breakdown not available
4. No demographic enrichment included (Census 2011 + post-poll surveys available separately)
5. Vote share differences between 2019 and 2024 expected due to realignment and regional dynamics

## Expected Use Cases

- Trend stability testing across election cycles
- Calibration overfitting detection
- Validation of regional party dynamics models
- State-level aggregation and comparison

## Files

- `results_constituency.csv` — Constituency-level results (543 seats)
- `README.md` — This file

## Next Steps

1. Acquire full ECI constituency data for all 543 seats from 2019 archive
2. Validate against official 2019 state-level results
3. Compare with 2024 data to identify key shifts in regional bases
