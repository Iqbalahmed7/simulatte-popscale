# Disaster Recovery Runbook — Simulatte Engine Phase 2

**Version:** 1.0  
**Last updated:** 2026-04-26  
**Owner:** Haiku  
**Inviolable rule:** Every failure mode either auto-recovers or halts cleanly with a checkpoint. No silent retry loops. No silent budget burn.

---

## Overview

This runbook covers all 7 failure modes from CORE_SPEC.md §5. Each mode lists:
1. **Detection signal** — how to know it happened
2. **Immediate action** — what to do in the first 5 minutes
3. **Recovery procedure** — how to resume
4. **Post-mortem checklist** — what to verify after recovery

---

## Failure Mode 1: Credit Balance < $10

**Scenario:** Anthropic account balance falls below minimum operational threshold mid-run.

### Detection Signal
- Pre-call balance check (execute before every cluster start)
- Logs: `"credit_balance_check: balance_usd=8.50 status=halt"`
- Operator receives push notification: "Simulatte halted: credit balance $8.50"

### Immediate Action (First 5 minutes)
1. Check current balance in Anthropic console: https://console.anthropic.com/account/billing
2. Note the exact balance and time of check
3. **HALT all active clusters immediately** — do not start new ones
4. Log halt decision with checkpoint ID: `docker logs <engine-container> | grep "checkpoint_id"`

### Recovery Procedure
1. Top up account to minimum $50 (recommended: $100+)
2. Verify balance in console (may take 2-3 min to reflect)
3. Pull latest checkpoint: `gs://simulatte-checkpoints/run_{run_id}/latest`
4. Dry-run balance check again: `python -m popscale.observability.budget_check --dry-run`
5. Resume from checkpoint: `python -m popscale.orchestration.resume --checkpoint-id=<id>`

### Post-Mortem Checklist
- [ ] Final balance recorded in spreadsheet (Finance tracking)
- [ ] Reason for depletion identified (overspend vs. slow payer)
- [ ] Billing alert threshold updated in `anthropic_client.py` config
- [ ] Team notified of resume + ETA in #infrastructure Slack

---

## Failure Mode 2: HTTP 400 (Bad Request)

**Scenario:** Anthropic API rejects a request with malformed payload (e.g., invalid JSON in system prompt, unsupported model parameter).

### Detection Signal
- Single retry fired automatically with stricter validation
- Logs: `"http_400_bad_request: attempt=1/2 payload_hash=abc123"`
- If retry fails: `"http_400_bad_request: attempt=2/2 fallback_triggered model=claude-sonnet-4-6"`

### Immediate Action (First 5 minutes)
1. Check error logs for specific field that failed validation
2. Example: `"invalid_field: system_prompt length=2500 max_allowed=2000"`
3. Do **NOT** retry immediately — this is a code bug, not transient
4. Pull request from `latest_errors` queue

### Recovery Procedure
1. Locate the malformed request in logs
2. Identify which component generated it (e.g., `perceive()` system prompt generation)
3. Fix the code (e.g., truncate system prompt to <2000 chars)
4. Deploy fix: `git commit && git push && GHA deploys to Railway`
5. Resume failed cluster from last checkpoint
6. Monitor first 3 API calls post-deploy

### Post-Mortem Checklist
- [ ] Root cause recorded (code bug, config error, schema mismatch)
- [ ] Unit test added to prevent recurrence
- [ ] Fixed code deployed to prod
- [ ] Affected personas re-run successfully
- [ ] Cost of re-run logged and reconciled

---

## Failure Mode 3: HTTP 429 (Rate Limit)

**Scenario:** Anthropic rate limit hit (tokens/min or requests/min). Token bucket state shows exhaustion.

### Detection Signal
- Token bucket detects limit exhaustion: `"rate_limit_hit: bucket_remaining=0 reset_at=2026-04-26T14:35:00Z"`
- Logs: `"http_429_rate_limit: attempt=1/5 backoff_ms=500"`
- Dashboard shows API calls/min spike above quota

### Immediate Action (First 5 minutes)
1. Do **NOT** manually stop — exponential backoff is active (init: 500ms → 16s max)
2. Check Anthropic status dashboard: https://status.anthropic.com
3. Confirm no service incident; if yes, escalate (see Failure Mode 7)
4. Verify our rate isn't excessive: logs show `"api_calls_per_minute"` metric

### Recovery Procedure
1. Automatic: wait for exponential backoff to succeed (max 5 retries over ~1 minute total)
2. If still failing after 5 retries:
   - Pause cluster ensemble run temporarily (save checkpoint)
   - Wait 60 seconds
   - Resume from checkpoint
3. If rate limit persists, manually reduce parallelism:
   - Edit `ENSEMBLE_PARALLELISM=3` → `ENSEMBLE_PARALLELISM=1` in environment
   - Restart engine: `kubectl rollout restart deployment/simulatte-engine`

### Post-Mortem Checklist
- [ ] Retry loop succeeded? Count total retries and backoff time
- [ ] Rate limit frequency tracked (once/day vs. recurring)
- [ ] Persona throughput adjusted if needed
- [ ] Anthropic rate limit quota reviewed (may need account upgrade)
- [ ] Cost impact of retries calculated and logged

---

## Failure Mode 4: HTTP 500 (Server Error)

**Scenario:** Anthropic server error (5xx status). Transient issue on their side.

### Detection Signal
- Per-call exception caught: `"http_500_server_error: attempt=1/3 model=claude-haiku-4-5"`
- Logs: `"exponential_backoff: attempt=2/3 backoff_ms=1000"`
- Dashboard shows error rate spike (>5% of calls in rolling 5-min window)

### Immediate Action (First 5 minutes)
1. **Do NOT pause the entire run** — only affected call retries
2. Check Anthropic status: https://status.anthropic.com
3. Note time of first 500 error for correlation
4. Monitor error frequency (are they happening in bursts?)

### Recovery Procedure
1. Automatic: exponential backoff retries (init: 1s → 8s → 16s) up to 3 times
2. If all 3 retries fail:
   - Fallback response emitted (uses persona priors, no reasoning)
   - Persona marked for re-run post-study
   - Cluster continues to next persona
3. After study: re-run failed personas only (partial re-run mode)

### Post-Mortem Checklist
- [ ] Anthropic incident timeline recorded (from status.anthropic.com)
- [ ] Fallback response count logged (how many personas affected)
- [ ] Failed personas list exported: `gs://simulatte-checkpoints/run_{run_id}/failed_personas.json`
- [ ] Partial re-run executed post-incident
- [ ] Cost reconciliation: original + retry + re-run tokens
- [ ] Error pattern analyzed (was it specific to a model or call type?)

---

## Failure Mode 5: JSON Parse Failure

**Scenario:** LLM response doesn't parse as valid JSON after decoding. Schema validation fails.

### Detection Signal
- Post-decode validation fails: `"json_parse_failure: model=claude-sonnet-4-6 response_len=1250 error=missing_required_field"`
- Logs show exact field: `"missing_field: 'reasoning' in schema 'PopulationResponse'"`
- Schema validator rejects response with detailed diff

### Immediate Action (First 5 minutes)
1. Examine the raw LLM response in logs
2. Determine if the issue is:
   - **Truncation** (response too long, cut mid-JSON) → retry with smaller max_tokens
   - **Hallucination** (invalid field type) → stricter prompt retry
   - **Schema mismatch** (code expects different shape) → code bug
3. Do NOT re-run without investigation

### Recovery Procedure
1. **First retry:** Stricter prompt version (tighter constraints, examples)
2. If still fails:
   - **Fallback response** triggered
   - Fallback uses persona priors (confidence=0.1) and no reasoning field
   - Persona marked for manual review post-study
3. If this is systematic (>5% failure rate on a call type):
   - Rollback recent prompt changes: `git revert <commit>`
   - Redeploy and resume

### Post-Mortem Checklist
- [ ] Raw response saved to: `gs://simulatte-debug/run_{run_id}/failed_response_{persona_id}.json`
- [ ] Root cause identified: truncation, hallucination, or schema mismatch
- [ ] If truncation: `max_tokens` increased appropriately
- [ ] If hallucination: prompt tightened and test case added
- [ ] If schema: code fix deployed, unit test added
- [ ] Fallback usage tracked and reviewed by domain expert
- [ ] Personas flagged for manual review post-study

---

## Failure Mode 6: Process Crash

**Scenario:** Engine process dies unexpectedly (OOM, segfault, unhandled exception). Heartbeat absent >5 minutes.

### Detection Signal
- Kubernetes liveness probe fails: `"heartbeat_timeout: expected_at=2026-04-26T14:30:00Z actual=none last_seen=14:25:00Z"`
- Container status: `CrashLoopBackOff` or `OOMKilled`
- Dashboard shows gap in per-persona progress (last update >5 min ago)
- Operator receives alert: "Simulatte engine unresponsive (last heartbeat 5+ min ago)"

### Immediate Action (First 5 minutes)
1. SSH to pod: `kubectl exec -it simulatte-engine-xxx /bin/bash`
2. Check logs: `tail -100 /var/log/simulatte/engine.log | tail -20`
3. Identify crash reason: check for OOM, stack trace, or unhandled exception
4. Note exact time of crash and last completed operation
5. **DO NOT manually restart** — Kubernetes will restart; let it stabilize first

### Recovery Procedure
1. Kubernetes auto-restarts pod (init wait 10s → 20s → 40s → cap 5m)
2. Upon restart, engine reads last checkpoint from GCS: `gs://simulatte-checkpoints/run_{run_id}/latest`
3. Checkpoint includes:
   - Last completed ensemble run ID
   - Last completed persona index
   - Cost spent so far
   - Exact timestamp
4. Engine resumes from checkpoint (skips already-completed work)
5. Monitor logs for successful recovery: `kubectl logs -f simulatte-engine-xxx`

### Post-Mortem Checklist
- [ ] Crash log analyzed and saved: `engineering/construct_phase_2/crashes/{date}_{pod_id}.log`
- [ ] Root cause identified:
  - [ ] OOM: memory limit increased in `deployment.yaml`
  - [ ] Unhandled exception: code fix + test added
  - [ ] Segfault: dependency update or native lib issue investigated
- [ ] Checkpoint fidelity verified (did recovery resume at correct place?)
- [ ] Time-to-recovery measured (from crash to first post-recovery persona)
- [ ] Cost reconciliation: tokens used before crash + after restart
- [ ] Deployment config updated if needed (memory, restart policy, etc.)

---

## Failure Mode 7: Anthropic Outage

**Scenario:** Anthropic service is down (all models unreachable). Health check fails for >15 minutes.

### Detection Signal
- Pre-study health check fails: `"anthropic_health_check: status=unavailable all_models_down=true"`
- Every API call fails with same error (not rate limit, not 500): `"connection_timeout"` or `"service_unavailable"`
- Anthropic status page shows: https://status.anthropic.com (active incident)
- Operator receives alert: "Simulatte halted: Anthropic service unavailable"

### Immediate Action (First 5 minutes)
1. **HALT all clusters immediately**
2. Check Anthropic status dashboard: https://status.anthropic.com
3. Note incident timeline, affected models, ETA for recovery
4. Post in #infrastructure: "Simulatte halted due to Anthropic outage. ETA recovery: [time from status page]"
5. Trigger checkpoint to GCS for all active runs

### Recovery Procedure
1. **Do NOT resume until Anthropic status shows "Operational"**
2. Once status is green:
   - Run health check: `python -m popscale.observability.health_check --all-models`
   - Confirm all models responsive (wait 2-3 min for their edge caches to warm)
3. Resume from last checkpoint: `python -m popscale.orchestration.resume --checkpoint-id=<id>`
4. Monitor first 10 API calls for any anomalies (lingering caching issues)

### Post-Mortem Checklist
- [ ] Outage timeline recorded (detected at / resolved at)
- [ ] Impact quantified: how many personas failed, cost of re-run
- [ ] Anthropic incident link archived: incident-XXXX URL
- [ ] Team retrospective scheduled to discuss SLA expectations
- [ ] On-call escalation process reviewed (was timing correct?)
- [ ] Resume testing plan added to test suite (rare but critical)
- [ ] Cost impact reconciled and reported to Finance

---

## Cross-Failure Checkpointing Strategy

Every failure mode that halts must checkpoint to GCS:

```python
checkpoint = {
    "run_id": run_id,
    "timestamp": datetime.utcnow().isoformat(),
    "failure_mode": "http_429_rate_limit",
    "last_completed_ensemble_id": ensemble_id,
    "last_completed_persona_index": persona_idx,
    "cost_spent_usd": total_cost,
    "personas_remaining": personas_total - persona_idx,
    "cluster_id": cluster_id,
    "model_versions": {...},
}
client.upload_to_gcs(checkpoint, f"gs://simulatte-checkpoints/run_{run_id}/checkpoint_{timestamp}.json")
```

Resume reads the latest checkpoint and validates:
- [ ] Checkpoint file exists and is valid JSON
- [ ] Timestamp is recent (<1 hour old)
- [ ] `personas_remaining > 0` (don't resume if done)
- [ ] Cost estimate is realistic (no NaN, no negative values)

---

## Runbook Updates

This document is version-controlled in Git. Update process:

1. Incident occurs in production
2. Post-mortem completed (within 48 hours)
3. Findings added to this runbook with:
   - What went wrong
   - What we did right / wrong
   - What changed to prevent recurrence
4. New test case added to test suite for regression prevention
5. Document version bumped: `1.0 → 1.1`
6. Commit: `git commit -m "Update DR_RUNBOOK: add section on [failure mode]"`

---

## On-Call Decision Tree

```
Failure detected
├─ Can it auto-recover? (rate limit, transient 500)
│  └─ YES: Let exponential backoff run, monitor logs
├─ Can we fallback? (JSON parse, single persona failure)
│  └─ YES: Emit fallback, mark for re-run, continue
├─ Must we halt? (credit, outage)
│  └─ YES: Checkpoint + halt immediately
│  └─ Notify team in #infrastructure
│  └─ Escalate if on-call didn't create incident within 5 min
```

---

## Contacts + Escalation

| Severity | First Contact | Escalation | Response Time |
|----------|---|---|---|
| Auto-recovery (rate limit, transient) | On-call (monitoring) | None | None |
| Halt (credit, outage) | On-call | Eng lead | 5 min |
| Recovery stalled >30 min | Eng lead | CTO | 15 min |
| Multiple failures in 1 hour | CTO | Re-architecture review | 24 hr |
