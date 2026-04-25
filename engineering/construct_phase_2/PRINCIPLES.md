# Construct Principles

**Purpose:** What we believe and why. The bets that shape every engineering decision in Phase 2. If a contributor disagrees with a principle here, they raise it explicitly — they do not silently violate it in code.

---

## P1 — Reasoning depth is our moat, but only if it predicts

The Simulatte bet from day one: synthetic populations that *reason* — perceive, accumulate memory, reflect, decide — produce more accurate predictions than population-level statistical models or shallow LLM polling.

The WB 2026 study proved the reasoning is real. Ramesh Chamar weighs Lakshmir Bhandar against Sandeshkhali in code-mixed Hindi. Mohammad Iqbal reasons in Bengali about SIR voter deletions. Nobody else can produce this.

But reasoning depth is a means, not an end. **The end is calibrated point predictions and well-decomposed uncertainty.** If our depth doesn't translate to better numbers than Aaru's shallower approach, depth is a research artifact, not a product moat.

**Implication:** Phase 2 makes prediction quality the primary KPI. Reasoning depth is preserved as the *mechanism* but evaluated only by the predictions it produces.

---

## P2 — Calibrate before deployment

We do not ship predictions to customers without backcasting them first.

Every domain we enter — political, consumer, healthcare — must clear a backcast benchmark before it's customer-facing. No exceptions. "Synthetic population says X" is meaningless without "and on benchmark Y, our error was Z."

**Implication:** No new domain in Phase 2 until political prediction is calibrated. Phase 3 expands only after Phase 2 succeeds.

---

## P3 — Fail loud or recover silent. Never silent fail.

The seven Run 1–7 attempts on the WB study were all silent failures: 400 errors retried in a loop, JSON truncation went unnoticed for hours, baseline path was wrong but the table printed anyway. Each silent failure cost us money or scientific validity.

The system must either:
- **Recover silently** (rate limit backoff, single retry on transient failure, graceful checkpoint) — these are infrastructure
- **Fail loud** (push notification, halt, refuse to proceed) — when human judgment is needed

What it must not do is **proceed quietly with degraded behavior**. A study that completes with a corrupted baseline is worse than a study that didn't run.

**Implication:** Every failure mode in `CORE_SPEC.md` Section 5 has explicit detection + action + recovery. No catch-all `except: pass`.

---

## P4 — Cost is engineering, not a bill

A $430 disaster is not "API costs" — it is an engineering failure. Cost projections are a contract. Burn rate is a metric. Budget overruns are bugs.

**Implication:** Cost telemetry is first-class in observability (CORE_SPEC §6). The pre-flight validator covers all layers. Budget ceiling is not advisory.

---

## P5 — Keep the moat where the moat is

Persona reasoning depth is the moat. Everything else (orchestration, dashboards, parallel execution, calibration framework) is plumbing — necessary, but commoditised. We invest engineering effort proportional to where the moat is.

This means:
- **Don't** rewrite the cognitive loop until calibration data demands it
- **Don't** invent novel infrastructure when off-the-shelf works (use Anthropic structured outputs, not custom JSON parsing; use Datadog, not bespoke logging)
- **Do** invest deeply in calibration tooling, bias decomposition, persona attribute distributions — the things that compound

**Implication:** When prioritising, ask: does this strengthen the moat (reasoning quality, calibration) or just enable scale? Strengthen first.

---

## P6 — Quotability is product

A single Ramesh Chamar response — code-mixed, policy-grounded, emotionally specific — is more persuasive to a campaign strategist than 50,000 aggregate vote share predictions. The reasoning trace is not a debugging artifact; it is the deliverable.

**Implication:** Reasoning traces are first-class outputs, retained per persona, exposed in customer reports. Compression / summarization happens client-side, never at storage. We do not lose the *why* to save bytes.

---

## P7 — Speed is in service of iteration, not impatience

We don't optimize for fast studies because customers are impatient. We optimize because **fast studies enable more backcasts, more calibration cycles, more bias correction iterations**. A 2.5-hour 5-cluster study is valuable because it lets us run 30 backcasts in Phase 3 instead of 3.

**Implication:** Latency targets in CORE_SPEC §3.2 are not customer SLAs. They are research-cycle SLAs. We tune them when calibration iteration speed bottlenecks Phase 3.

---

## P8 — Document the bet so we can falsify it

Every claim Simulatte makes externally must be traceable to:
1. A predefined benchmark
2. A method documented in this directory
3. A measured error against ground truth

This is what separates research-grade prediction from vibes-based forecasting. It is what credibility looks like in 2026 when LLM-generated election forecasts are everywhere.

**Implication:** Every customer report has a methodology appendix. Every backcast result is published with confidence intervals. We never quote a single number without a band.

---

## P9 — Human-in-the-loop is a phase, not a feature

Right now, every study requires Iqbal to monitor logs, top up credits, restart crashed jobs, hand-fix bugs at 1am. That's acceptable when running 1 study. It is not acceptable at 10× scale.

**Implication:** Phase 4 acceptance is "50-cluster study with zero human intervention." Until that ships, Construct Phase 2 is not done.

---

## P10 — Leave artifacts, not dependencies

Construct Phase 2 must produce assets that outlive the people who built them: backcast harness, ground truth registry, bias decomposition reports, calibration training pipeline. These are durable. They compound. A new engineer should be able to read these documents in 6 months and run a backcast end-to-end.

What we explicitly avoid: bespoke scripts that only Iqbal/Cursor/Codex understand, code that lives in `/tmp/` and gets lost, decisions documented only in chat history.

**Implication:** All Phase 2 work ships with documentation. All scripts live in versioned directories. All decisions get a `decisions/` log entry with date and rationale.

---

## What's not a principle (yet)

- **Multi-vendor LLM** — defer to Phase 3 (one provider until cost + reliability owned)
- **Real-time predictions** — defer (research-cycle latency is enough)
- **Public-facing API** — defer (back-office orchestration through Phase 2)
- **Customer self-service** — defer (white-glove delivery is fine for 5–10 customers)

These are good ideas. They are not the right ideas now.

---

## Conflict resolution

If two principles conflict in a specific decision, the priority is:

```
P3 (no silent failures) > P1 (predict accurately) > P2 (calibrate first) >
P4 (cost is engineering) > P5 (moat first) > everything else
```

E.g. if a fast cost optimisation introduces a silent failure mode, the cost optimisation loses. If calibrating a new domain requires shipping uncalibrated to customers first, we don't ship.

---

**This document evolves.** When a principle is violated and the violation produces a good outcome, we add a principle. When a principle blocks the right answer twice, we remove it. Nothing here is sacred except P3 — silent failures kill trust, and trust is the prerequisite for everything else.
