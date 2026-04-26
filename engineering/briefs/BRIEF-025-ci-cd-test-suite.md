# BRIEF-025 — CI/CD + Disaster Recovery

| Field | Value |
|---|---|
| Sprint | Phase 4 |
| Owner | **Haiku** |
| Estimate | 1 day |
| Branch | `phase-4/brief-025-ci-cd` |

## What

Per `CONSTRUCT_PHASE_2.md` Phase 4 §"CI/CD test suite" + §"Disaster recovery runbook":

1. **GitHub Actions workflows** in both repos that:
   - Run all Phase 0/1/3 tests on every PR
   - Block merge if any regression
   - Mock Anthropic API responses (fixtures, no real calls in CI)

2. **Disaster recovery runbook** at `engineering/construct_phase_2/DR_RUNBOOK.md` covering every failure mode in CORE_SPEC.md §5 with: detection signal, immediate action, recovery procedure, post-mortem checklist.

3. **One full-pipeline integration test** that mocks Anthropic + runs a 1-cluster benchmark end-to-end, verifying:
   - Pre-flight passes
   - Cluster runs to completion
   - Partial JSON written correctly
   - Final result schema valid
   - Dashboard events emitted

## Files

```
.github/workflows/
├── tests.yml                # both repos
└── lint.yml
engineering/construct_phase_2/
└── DR_RUNBOOK.md            # NEW
benchmarks/wb_2026/constituency/tests/
└── test_e2e_mocked.py       # NEW — full pipeline with mocked client
```

## Acceptance

1. CI runs on every push. Green badge in repo README.
2. DR_RUNBOOK covers all 7 failure modes from CORE_SPEC.md §5.
3. Mocked e2e test runs in <30 seconds.

## Constraints

- Use `pytest-mock` or `unittest.mock` (one is already a transitive dep)
- No real API keys in CI — mock at the `client.messages.create` level
