# US 2024 Presidential Election (County-level)

## Metadata

- **Election Date:** November 5, 2024
- **Granularity:** County (3,143 counties)
- **Data Retrieved:** April 26, 2026
- **Source:** MIT Election Data and Science Lab (electionlab.mit.edu)

## Dataset Status

**STUB DATASET** — Placeholder with representative sample data (10 Alabama counties).

The actual MIT EDSL CSV endpoint appears to be behind a redirect or changed. Real data acquisition will require:
1. Direct download from electionlab.mit.edu archive
2. Alternative source: Cook Political Report county-level 2024 data
3. Census Bureau county-level turnout estimates

## Schema

```
county_fips        : 5-digit FIPS code (e.g., 1001 for Autauga County, AL)
county_name        : Human-readable county name
state_abbr         : 2-letter state abbreviation (AL, AK, etc.)
trump_pct          : Trump vote share (0-100)
harris_pct         : Harris vote share (0-100)
other_pct          : Other/write-in vote share (0-100)
total_votes        : Total votes cast in county
turnout_pct        : Voter turnout as percentage of registered voters
```

## Normalization

Vote percentages are already in 0-100 scale from source. No additional normalization applied.

## Known Limitations

1. Stub dataset includes only 10 sample counties from Alabama for testing
2. Real dataset should include all 3,143 US counties
3. Turnout data is estimated; actual county-level data varies by state
4. No demographic enrichment attached (Census ACS available separately)

## Files

- `results_county.csv` — County-level vote shares and turnout

## Usage

```python
from popscale.calibration.loaders import load_ground_truth
gt = load_ground_truth("us_2024_pres")
print(f"Loaded {len(gt.units)} counties")
```

## Next Steps

Replace stub CSV with real 2024 data from MIT EDSL or Cook Political Report.
