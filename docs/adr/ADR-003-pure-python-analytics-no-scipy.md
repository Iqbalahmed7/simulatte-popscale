# ADR-003: Implement Analytics in Pure Python — No NumPy/SciPy Dependency

**Status**: Accepted  
**Date**: 2026-04-18 (reconstructed from codebase)  
**Deciders**: Simulatte Tech Lead  

---

## Context

The analytics layer (`popscale/analytics/`) computes:
- **Wilson score confidence intervals** for option proportions (choice scenarios)
- **Cramér's V** for categorical predictor × categorical outcome association
- **Eta²** (one-way ANOVA effect size) for continuous predictor × categorical outcome
- **Sentiment distribution** bucketing from emotional valence values
- **Surprise detection** comparing actual distributions against behavioural priors
- **Trajectory analysis** across multiple simulation waves

These are standard statistical computations. The natural implementation would use `scipy.stats` (Wilson CI, chi-squared), `numpy` (array operations), and possibly `pandas` (groupby aggregations).

The decision was made to implement all analytics in pure Python using only the standard library (`math`, `statistics`, `collections`).

---

## Decision

**All analytics are implemented in pure Python with no numpy or scipy dependency.**

- Wilson CI: implemented with `math.sqrt` (see `distributions.py:_wilson_ci`)
- Cramér's V: implemented with manual contingency table construction and chi-squared (see `drivers.py:_cramers_v`)
- Eta²: implemented with group mean/variance decomposition (see `drivers.py`)
- Distributions and aggregations: implemented with `collections.Counter`, `collections.defaultdict`, and `statistics.median`

`numpy>=2.0.0` appears in `requirements.txt` but is not imported anywhere in the `popscale/` package. It is a transitive requirement that came from early prototyping or from the PG dependency chain.

---

## Rationale

### 1. Zero-dependency analytics layer
The analytics layer processes lists of `PopulationResponse` dataclasses. These are Python dicts at heart. Converting them to numpy arrays would add overhead for the typical population sizes (100–10,000 personas) without meaningful performance benefit.

### 2. Portability
A pure-Python analytics module can run in any Python environment without native library compilation. This is important for deployment in environments where binary wheels are not available (e.g., serverless Lambda layers, some Railway container sizes).

### 3. Testability
Pure Python functions are easy to test without fixtures. `_wilson_ci(10, 100)` can be unit-tested inline. A numpy-based implementation would require array setup and numpy-specific assertions.

### 4. Correctness at small N
`scipy.stats.proportion_confint` uses the normal approximation by default, which is invalid at small N (breaks at N < 30). The Wilson score interval is valid at any N ≥ 1. Implementing it manually ensures the correct formula is used without relying on the right `method=` parameter being passed.

### 5. Effect size implementations are short
Cramér's V and Eta² are 20-30 lines of pure Python each. There is no meaningful complexity that scipy would abstract away.

---

## Consequences

### Positive
- No native dependency compilation; `pip install -r requirements.txt` always works.
- Analytics code is readable and auditable — no scipy internals to debug.
- Wilson CI is guaranteed to be the correct formula (not the normal approximation fallback).
- All statistical code is directly testable and can be reviewed against textbook formulas.

### Negative
- **Performance ceiling**: For cohorts > 100,000 personas, Python list iteration over `PopulationResponse` objects will be slow. At the expected scale (100–10,000 personas), this is not a problem.
- **Missing distributions**: No t-tests, regression, bootstrap CIs, or other statistical procedures. Adding them requires manual implementation rather than calling `scipy.stats`.
- **No vectorised operations**: Groupby aggregations use `defaultdict` loops rather than pandas `groupby`. This is readable but verbose.
- **`numpy` is still in `requirements.txt`**: Redundant unless PG's own CostEstimator imports it transitively. Should be audited and removed if not needed.

### Future considerations
If PopScale is used for cohorts above 50,000 personas or if more sophisticated analytics (regression, bootstrap CIs, cluster analysis) are needed, introducing `numpy` and `scipy` as optional dependencies (with a fallback pure-Python path) would be a clean upgrade path.
