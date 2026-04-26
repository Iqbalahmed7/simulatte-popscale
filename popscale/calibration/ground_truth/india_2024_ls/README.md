# India 2024 Lok Sabha Election (National Parliament)

## Metadata

- **Election Date:** June 4, 2024 (final count)
- **Granularity:** Constituency (543 seats)
- **Data Retrieved:** April 26, 2026
- **Source:** Election Commission of India (ECI) - https://results.eci.gov.in/

## Dataset Status

**STUB DATASET** — Placeholder with representative sample data (10 constituencies from Madhya Pradesh and Rajasthan).

Real data should be retrieved from ECI official results portal. This stub includes test data only.

## Schema

```
constituency_code  : ECI constituency code (e.g., LS001)
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

## Regional Parties Aggregation

The `regional_pct` field aggregates vote shares from regional parties:
- DMK (Tamil Nadu)
- BJD (Odisha)
- TMC (West Bengal)
- Shiv Sena variants (Maharashtra)
- JDU (Bihar)
- SAD (Punjab)
- NCP (Maharashtra)
- And other state-level parties

## Known Limitations

1. Stub data: Only 10 sample constituencies for testing
2. Real dataset must include all 543 constituencies
3. Regional parties are combined; breakdown not available in this schema
4. No demographic enrichment included (can be joined from post-poll surveys)
5. Vote share aggregation may differ slightly from official counts due to rounding

## Expected Use Cases

- Calibration of national-level Lok Sabha predictions
- State-level aggregation for regional comparison
- Benchmarking regional party performance vs national parties

## Files

- `results_constituency.csv` — Constituency-level results (543 seats)
- `README.md` — This file

## Next Steps

1. Acquire full ECI constituency data for all 543 seats
2. Optionally enrich with post-poll survey (CSDS/Lokniti) demographic data
3. Validate against official state-level aggregates
