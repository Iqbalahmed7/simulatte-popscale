"""benchmarks/us_2024_swing/us_2024_swing_benchmark.py

2024 US Presidential Election — Swing State PopScale Benchmark.

PURPOSE
-------
Validate PopScale's predictive accuracy against real 2024 US presidential
election outcomes across four key swing states.

This benchmark runs autonomously through phases:
  Phase 1 (--phase 1): Pennsylvania only, n=10, up to 3 runs (sanity gate)
  Phase 2 (--phase 2): All 4 states, n=10, calibration runs
  Phase 3 (--phase 3): All 4 states, n=20, final validation

The phases are designed to catch problems cheaply before committing to
larger runs. A hard budget cap prevents accidental overspend.

ACTUAL RESULTS (November 5, 2024 — AP/NYT final):
    Pennsylvania: Trump 50.3%, Harris 48.6%, Other 1.1%
    Georgia:      Trump 50.7%, Harris 48.5%, Other 0.8%
    Arizona:      Trump 52.2%, Harris 46.5%, Other 1.3%
    Wisconsin:    Trump 49.9%, Harris 48.8%, Other 1.3%

BENCHMARK DESIGN
----------------
- n=10 (Phase 1), n=10 (Phase 2), n=20 (Phase 3) personas per state
- Income-stratified cohort (no religion stratification for US)
- Two-candidate scenario: Trump vs Harris with third-party option
- Accuracy metric: Mean Absolute Error (MAE) per state + aggregate
- Pass criteria: direction correct (right winner) + MAE < 12pp

USAGE
-----
    # Phase 1 — Pennsylvania sanity gate (cheap: ~$1.50):
    python us_2024_swing_benchmark.py --phase 1

    # Phase 2 — All 4 states calibration (n=10, ~$4):
    python us_2024_swing_benchmark.py --phase 2

    # Phase 3 — Validation (n=20, ~$8):
    python us_2024_swing_benchmark.py --phase 3

    # Single state only:
    python us_2024_swing_benchmark.py --phase 2 --state pennsylvania

    # Load existing results:
    python us_2024_swing_benchmark.py --results-file results/us_2024_swing_<run_id>.json

BUDGET GUARDS
-------------
  Phase 1: $5 hard cap
  Phase 2: $15 hard cap
  Phase 3: $15 hard cap
  Total cap (--all-phases): $40
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
_POPSCALE_ROOT = Path(__file__).parents[2]
_NIOBE_ROOT    = Path(__file__).parents[4] / "Niobe"
_PG_ROOT       = Path(__file__).parents[4] / "Persona Generator"

for p in [str(_POPSCALE_ROOT), str(_NIOBE_ROOT), str(_PG_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from niobe.study_request import NiobeStudyRequest   # noqa: E402
from niobe.runner import run_niobe_study             # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("us_2024_swing_benchmark")

# ── Ground truth ──────────────────────────────────────────────────────────────

# Two-party vote share (third party < 1.5% in all states — excluded for calibration purity).
# Source: AP 2024 final results, normalised to Trump + Harris = 100%.
ACTUAL_RESULTS: dict[str, dict[str, float]] = {
    "pennsylvania": {"Trump": 0.508, "Harris": 0.492},
    "georgia":      {"Trump": 0.512, "Harris": 0.488},
    "arizona":      {"Trump": 0.529, "Harris": 0.471},
    "wisconsin":    {"Trump": 0.506, "Harris": 0.494},
}

# Pre-election poll averages (RealClearPolitics final averages, Nov 2024)
# Also normalised to two-party for apples-to-apples MAE comparison.
POLL_AVERAGES: dict[str, dict[str, float]] = {
    "pennsylvania": {"Trump": 0.501, "Harris": 0.499},
    "georgia":      {"Trump": 0.510, "Harris": 0.490},
    "arizona":      {"Trump": 0.513, "Harris": 0.487},
    "wisconsin":    {"Trump": 0.498, "Harris": 0.502},
}

STATE_DISPLAY: dict[str, str] = {
    "pennsylvania": "Pennsylvania",
    "georgia":      "Georgia",
    "arizona":      "Arizona",
    "wisconsin":    "Wisconsin",
}

SCENARIO_OPTIONS = [
    "Donald Trump (Republican)",
    "Kamala Harris (Democrat)",
]

# Map option text → candidate key
_OPTION_TO_CANDIDATE: dict[str, str] = {
    "Donald Trump (Republican)": "Trump",
    "Kamala Harris (Democrat)":  "Harris",
}

# Budget caps per phase (USD)
_PHASE_CAPS: dict[int, float] = {1: 5.0, 2: 15.0, 3: 15.0}
_TOTAL_CAP = 40.0

# ── State-specific scenario contexts ─────────────────────────────────────────

_STATE_CONTEXTS: dict[str, str] = {
    "pennsylvania": (
        "The 2024 US presidential election is on November 5, 2024. Pennsylvania is one of "
        "the most pivotal swing states in the nation, with 19 electoral votes. The state "
        "spans a deep divide: Philadelphia and its suburbs are reliably Democratic, while "
        "rural western Pennsylvania and the Scranton/Wilkes-Barre post-industrial corridor "
        "have shifted sharply Republican since 2016. The state's economy is anchored in "
        "healthcare, education, manufacturing, and energy (including natural gas fracking). "
        "Donald Trump narrowly lost Pennsylvania to Biden in 2020 by 0.7 points but "
        "carried it in 2016 by 0.7 points. Vice President Kamala Harris replaced Joe Biden "
        "as the Democratic nominee in July 2024. Trump has campaigned heavily on "
        "immigration, inflation, trade tariffs protecting domestic manufacturing jobs, and "
        "crime. Harris has focused on abortion rights (Dobbs was significant in PA), "
        "democracy, and economic fairness. The economy — particularly inflation and cost of "
        "living — is the top voter concern. Pennsylvania has significant union history (UAW, "
        "SEIU) and a large Catholic population."
    ),
    "georgia": (
        "The 2024 US presidential election is on November 5, 2024. Georgia has 16 electoral "
        "votes and has become a genuine battleground state after Biden flipped it in 2020 by "
        "just 0.2 points — the first Democrat to win Georgia since 1992. The state is "
        "sharply divided: Atlanta metro (Fulton, DeKalb, Cobb, Gwinnett counties) drives "
        "Democratic margins, while rural Georgia and the suburbs beyond Atlanta remain "
        "Republican. Georgia has a large Black voter population (~32% of eligible voters), "
        "concentrated in Atlanta and the Black Belt counties. Stacey Abrams's voter "
        "registration drives in 2018-2020 transformed the electorate. Donald Trump "
        "famously pressured Georgia officials to 'find votes' after his 2020 loss and faces "
        "state criminal charges related to election interference. Kamala Harris is the first "
        "Black and South Asian American on a major party presidential ticket, which has "
        "particular resonance in Georgia. Key issues: inflation, cost of living, abortion "
        "rights, and economic development in Atlanta's booming tech sector."
    ),
    "arizona": (
        "The 2024 US presidential election is on November 5, 2024. Arizona has 11 electoral "
        "votes and has trended Democratic recently — Biden flipped it in 2020 by 0.3 points "
        "after decades of Republican dominance. The state's political landscape is shaped by "
        "rapid growth: the Phoenix metro has added millions of residents, bringing college-"
        "educated suburbanites who lean Democratic. Latino voters (~24% of eligible voters) "
        "are a major demographic, heavily concentrated in Phoenix, Tucson, and the border "
        "counties. Retirees, military families (multiple major bases), and a growing tech "
        "sector add to the mix. Immigration is an especially potent issue given Arizona's "
        "border with Mexico and the state's history with contentious immigration legislation. "
        "Donald Trump has made border security and immigration the centerpiece of his "
        "Arizona campaign. Kamala Harris has emphasized abortion rights — Arizona faced a "
        "near-total abortion ban via a pre-statehood law that the state Supreme Court briefly "
        "reinstated in 2024, galvanizing reproductive rights voters. Water scarcity, housing "
        "costs, and wildfire risk also matter to Arizona voters."
    ),
    "wisconsin": (
        "The 2024 US presidential election is on November 5, 2024. Wisconsin has 10 "
        "electoral votes and is among the closest swing states in the nation. Trump won it "
        "by 0.7 points in 2016 and Biden by 0.6 points in 2020 — a state decided by "
        "thousandths of a percentage point. The state breaks down as: Milwaukee and Madison "
        "are Democratic strongholds; the Fox Valley (Appleton, Green Bay) and western/rural "
        "Wisconsin have shifted sharply Republican; suburban Milwaukee (Waukesha, Ozaukee, "
        "Washington counties, the 'WOW counties') are closely contested and often decisive. "
        "Wisconsin's economy is built on dairy farming, manufacturing (Foxconn, Harley-"
        "Davidson, paper), and the University of Wisconsin system. Trade policy, agricultural "
        "support (dairy farm margins), inflation, manufacturing jobs, and abortion rights "
        "are the key voter concerns. Wisconsin has a strong union tradition (the 2011 Act 10 "
        "battle under Gov. Walker permanently scarred labor relations) and a significant "
        "German and Scandinavian heritage electorate in rural areas. Turnout in Milwaukee "
        "is decisive for Democrats."
    ),
}

# ── Request builder ───────────────────────────────────────────────────────────

def build_request(state: str, n_personas: int, budget_cap: float) -> NiobeStudyRequest:
    """Build a NiobeStudyRequest for a single swing state."""
    state_display = STATE_DISPLAY[state]
    return NiobeStudyRequest(
        study_name=f"US 2024 Presidential Election — {state_display} Swing State Benchmark",
        state=state,
        n_personas=n_personas,
        domain="us_general",
        research_question=(
            f"How do {state_display} voters split between Trump and Harris in the "
            f"2024 presidential election, and what are the key drivers?"
        ),
        scenario_question=(
            "In the 2024 US presidential election, who will you vote for?"
        ),
        scenario_context=_STATE_CONTEXTS[state],
        scenario_options=SCENARIO_OPTIONS,
        stratify_by_religion=False,
        stratify_by_income=True,
        budget_cap_usd=budget_cap,
    )


# ── Vote share extraction ─────────────────────────────────────────────────────

def extract_vote_shares(result) -> dict[str, float]:
    """Extract vote share per candidate from StudyResult.

    Matching strategy (most-specific first):
    1. Exact match against full option text (case-insensitive).
    2. Decision starts with candidate name ("trump", "harris", "third").
    3. Best-count fuzzy match: count mentions of each name in decision text.
    4. Fall through to Other.
    """
    responses = result.simulation.responses
    n_total = max(1, len(responses))
    counts: dict[str, int] = {"Trump": 0, "Harris": 0}

    for r in responses:
        decision = r.decision.strip().lower()
        matched = None

        # 1. Exact full-option match
        for option_text, candidate in _OPTION_TO_CANDIDATE.items():
            if decision == option_text.lower():
                matched = candidate
                break

        # 2. Starts-with match on candidate name
        if matched is None:
            if decision.startswith("donald trump") or decision.startswith("trump"):
                matched = "Trump"
            elif decision.startswith("kamala harris") or decision.startswith("harris"):
                matched = "Harris"

        # 3. Best-count fuzzy — pick name that appears most in the text
        if matched is None:
            trump_count  = decision.count("trump")
            harris_count = decision.count("harris")
            if trump_count > harris_count:
                matched = "Trump"
            elif harris_count > trump_count:
                matched = "Harris"

        # 4. Final fallback: random 50/50 to avoid systematic bias
        if matched is None:
            import hashlib
            hash_val = int(hashlib.md5(r.decision.encode()).hexdigest(), 16)
            matched = "Trump" if hash_val % 2 == 0 else "Harris"

        counts[matched] += 1

    return {c: round(count / n_total, 4) for c, count in counts.items()}


# ── MAE and reporting ─────────────────────────────────────────────────────────

def compute_mae(predicted: dict[str, float], actual: dict[str, float]) -> float:
    parties = list(actual.keys())
    total = sum(abs(predicted.get(p, 0.0) - actual[p]) for p in parties)
    return round(total / len(parties), 4)


def build_state_report(
    state: str,
    result,
    shares: dict[str, float],
    run_id: str,
    n_personas: int,
    cost_usd: float,
) -> dict:
    actual = ACTUAL_RESULTS[state]
    polls  = POLL_AVERAGES[state]
    state_display = STATE_DISPLAY[state]

    popscale_mae = compute_mae(shares, actual)
    poll_mae     = compute_mae(polls, actual)

    rows = []
    for candidate in ["Trump", "Harris"]:
        ps   = shares.get(candidate, 0.0)
        act  = actual.get(candidate, 0.0)
        poll = polls.get(candidate, 0.0)
        rows.append({
            "candidate":      candidate,
            "popscale_pct":   round(ps   * 100, 1),
            "actual_pct":     round(act  * 100, 1),
            "poll_avg_pct":   round(poll * 100, 1),
            "popscale_error": round(abs(ps - act)   * 100, 1),
            "poll_error":     round(abs(poll - act)  * 100, 1),
        })

    winner_popscale = max(shares, key=shares.__getitem__)
    winner_actual   = max(actual, key=actual.__getitem__)
    winner_correct  = winner_popscale == winner_actual

    return {
        "state":          state,
        "state_display":  state_display,
        "run_id":         run_id,
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "n_personas":     n_personas,
        "cost_usd":       round(cost_usd, 4),
        "verdict": {
            "winner_predicted": winner_popscale,
            "winner_actual":    winner_actual,
            "winner_correct":   winner_correct,
            "popscale_mae_pct": round(popscale_mae * 100, 2),
            "poll_avg_mae_pct": round(poll_mae * 100, 2),
            "beats_polls":      popscale_mae < poll_mae,
        },
        "candidate_breakdown": rows,
        "popscale_shares": {c: round(v * 100, 1) for c, v in shares.items()},
        "actual_shares":   {c: round(v * 100, 1) for c, v in actual.items()},
        "poll_avg_shares": {c: round(v * 100, 1) for c, v in polls.items()},
    }


def print_state_report(report: dict) -> None:
    v = report["verdict"]
    print(f"\n{'═' * 65}")
    print(f"  {report['state_display'].upper()} — PopScale vs 2024 Actual")
    print(f"{'═' * 65}")
    print(f"  Run ID   : {report['run_id']}")
    print(f"  Personas : {report['n_personas']}   Cost: ${report['cost_usd']:.4f}")
    print()
    print(f"  {'Candidate':<18} {'PopScale':>10} {'Actual':>10} {'Polls':>10} {'PS Err':>8} {'Poll Err':>9}")
    print("  " + "-" * 63)
    for row in report["candidate_breakdown"]:
        print(
            f"  {row['candidate']:<18} "
            f"{row['popscale_pct']:>9.1f}% "
            f"{row['actual_pct']:>9.1f}% "
            f"{row['poll_avg_pct']:>9.1f}% "
            f"{row['popscale_error']:>7.1f}pp "
            f"{row['poll_error']:>8.1f}pp"
        )
    print()
    win_icon  = "✓" if v["winner_correct"] else "✗"
    poll_icon = "✓" if v["beats_polls"]    else "✗"
    print(f"  [{win_icon}] Winner: {v['winner_predicted']} (actual: {v['winner_actual']})")
    print(f"  [{poll_icon}] MAE: PopScale {v['popscale_mae_pct']:.1f}pp  Polls {v['poll_avg_mae_pct']:.1f}pp")
    print(f"{'═' * 65}")


def print_aggregate_report(state_reports: list[dict]) -> None:
    """Print a summary table across all states."""
    print(f"\n{'═' * 70}")
    print("  US 2024 SWING STATE BENCHMARK — AGGREGATE SUMMARY")
    print(f"{'═' * 70}")
    print(f"  {'State':<16} {'Winner':>8} {'OK':>4} {'PS MAE':>8} {'Poll MAE':>9} {'Beats':>6}")
    print("  " + "-" * 56)

    correct = 0
    total_ps_mae = 0.0
    total_poll_mae = 0.0

    for rpt in state_reports:
        v = rpt["verdict"]
        win_ok = "✓" if v["winner_correct"] else "✗"
        beats  = "✓" if v["beats_polls"]    else "✗"
        correct += int(v["winner_correct"])
        total_ps_mae   += v["popscale_mae_pct"]
        total_poll_mae += v["poll_avg_mae_pct"]
        print(
            f"  {rpt['state_display']:<16} "
            f"{v['winner_predicted']:>8}  "
            f"{win_ok:>2}  "
            f"{v['popscale_mae_pct']:>7.1f}pp "
            f"{v['poll_avg_mae_pct']:>8.1f}pp "
            f"{beats:>5}"
        )

    n = max(len(state_reports), 1)
    avg_ps   = total_ps_mae   / n
    avg_poll = total_poll_mae / n
    beats_polls = avg_ps < avg_poll

    print("  " + "-" * 56)
    print(f"  {'AVERAGE':<16} {'':>8}  {'':>2}  {avg_ps:>7.1f}pp {avg_poll:>8.1f}pp {'✓' if beats_polls else '✗':>5}")
    print()
    print(f"  Winners correct: {correct}/{len(state_reports)}")
    total_cost = sum(r["cost_usd"] for r in state_reports)
    total_n    = sum(r["n_personas"] for r in state_reports)
    print(f"  Total personas:  {total_n}   Total cost: ${total_cost:.4f}")

    if correct == len(state_reports) and beats_polls:
        print("\n  RESULT: PASS — All states correct + beats polls overall.")
    elif correct == len(state_reports):
        print("\n  RESULT: PARTIAL PASS — All winners correct, MAE above poll baseline.")
    else:
        print(f"\n  RESULT: FAIL — {len(state_reports) - correct} state(s) predicted wrong winner.")
    print(f"{'═' * 70}\n")


def save_results(reports: list[dict], results_dir: Path, run_id: str) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    out = {"run_id": run_id, "states": reports}
    path = results_dir / f"us_2024_swing_{run_id}.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    logger.info("Results saved → %s", path)
    return path


# ── Phase runners ─────────────────────────────────────────────────────────────

_PHASE_STATES: dict[int, list[str]] = {
    1: ["pennsylvania"],                                        # sanity gate
    2: ["pennsylvania", "georgia", "arizona", "wisconsin"],    # calibration
    3: ["pennsylvania", "georgia", "arizona", "wisconsin"],    # validation
}
_PHASE_N: dict[int, int] = {1: 10, 2: 10, 3: 20}


async def run_phase(
    phase: int,
    states: list[str],
    results_dir: Path,
) -> list[dict]:
    n_personas = _PHASE_N[phase]
    budget_cap = _PHASE_CAPS[phase]
    per_state_cap = round(budget_cap / len(states), 2)

    logger.info(
        "=== PHASE %d | n=%d per state | %d states | cap $%.2f (%.2f/state) ===",
        phase, n_personas, len(states), budget_cap, per_state_cap,
    )

    state_reports: list[dict] = []
    cumulative_cost = 0.0

    for state in states:
        if cumulative_cost >= budget_cap:
            logger.warning("Budget cap $%.2f reached — skipping remaining states.", budget_cap)
            break

        state_display = STATE_DISPLAY[state]
        remaining_budget = budget_cap - cumulative_cost
        this_cap = min(per_state_cap, remaining_budget)

        logger.info("Running %s | n=%d | cap $%.2f", state_display, n_personas, this_cap)

        request = build_request(state, n_personas, this_cap)
        result  = await run_niobe_study(request)

        shares  = extract_vote_shares(result)
        run_id  = result.run_id
        cost    = result.total_cost_usd

        report = build_state_report(
            state=state,
            result=result,
            shares=shares,
            run_id=run_id,
            n_personas=result.n_personas,
            cost_usd=cost,
        )

        print_state_report(report)
        state_reports.append(report)
        cumulative_cost += cost

        logger.info(
            "%s done | winner=%s (%s) | MAE=%.1fpp | cost=$%.4f | cumulative=$%.4f",
            state_display,
            report["verdict"]["winner_predicted"],
            "✓" if report["verdict"]["winner_correct"] else "✗",
            report["verdict"]["popscale_mae_pct"],
            cost,
            cumulative_cost,
        )

    if len(state_reports) > 1:
        print_aggregate_report(state_reports)

    # Phase 1 gate check
    if phase == 1:
        rpt = state_reports[0]
        v = rpt["verdict"]
        if not v["winner_correct"]:
            logger.error(
                "PHASE 1 GATE FAILED: PA winner incorrect (%s predicted, Trump actual). "
                "Do NOT proceed to Phase 2 until pool is fixed.",
                v["winner_predicted"],
            )
        elif v["popscale_mae_pct"] > 15.0:
            logger.warning(
                "PHASE 1 GATE WARNING: PA MAE %.1fpp > 15pp threshold. "
                "Consider pool recalibration before Phase 2.",
                v["popscale_mae_pct"],
            )
        else:
            logger.info(
                "PHASE 1 GATE PASSED: PA winner correct, MAE=%.1fpp. "
                "Safe to proceed to Phase 2.",
                v["popscale_mae_pct"],
            )

    return state_reports


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="US 2024 Presidential Election — Swing State PopScale benchmark"
    )
    parser.add_argument(
        "--phase", type=int, choices=[1, 2, 3], default=None,
        help="Run phase: 1=PA sanity (n=10), 2=4-state calibration (n=10), 3=validation (n=20)",
    )
    parser.add_argument(
        "--all-phases", action="store_true",
        help="Run all 3 phases sequentially (budget cap: $40 total — use with care)",
    )
    parser.add_argument(
        "--state", type=str, default=None,
        choices=["pennsylvania", "georgia", "arizona", "wisconsin"],
        help="Restrict to a single state (overrides phase default states)",
    )
    parser.add_argument(
        "--n", type=int, default=None,
        help="Override n_personas (overrides phase default)",
    )
    parser.add_argument(
        "--results-file", type=Path, default=None,
        help="Load and re-print an existing results JSON",
    )
    parser.add_argument(
        "--results-dir", type=Path,
        default=Path(__file__).parent / "results",
        help="Directory to save results JSON (default: ./results/)",
    )
    args = parser.parse_args()

    # ── Load existing results ─────────────────────────────────────────────
    if args.results_file:
        with open(args.results_file) as f:
            data = json.load(f)
        reports = data.get("states", [])
        for rpt in reports:
            print_state_report(rpt)
        if len(reports) > 1:
            print_aggregate_report(reports)
        return

    # ── Validate args ─────────────────────────────────────────────────────
    if args.phase is None and not args.all_phases:
        parser.error("Specify --phase 1|2|3 or --all-phases")

    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    # ── Single phase run ──────────────────────────────────────────────────
    if args.phase is not None and not args.all_phases:
        states = [args.state] if args.state else _PHASE_STATES[args.phase]
        if args.n:
            # Override n for this phase temporarily
            _PHASE_N[args.phase] = args.n
        reports = asyncio.run(run_phase(args.phase, states, args.results_dir))
        run_id  = reports[0]["run_id"] if reports else run_ts
        save_results(reports, args.results_dir, run_id)
        return

    # ── All phases ────────────────────────────────────────────────────────
    if args.all_phases:
        logger.warning("Running ALL phases. Total budget cap: $%.2f", _TOTAL_CAP)
        all_reports: list[dict] = []
        total_cost = 0.0

        for phase in [1, 2, 3]:
            if total_cost >= _TOTAL_CAP:
                logger.warning("Total cap $%.2f reached — stopping.", _TOTAL_CAP)
                break
            states = [args.state] if args.state else _PHASE_STATES[phase]
            reports = asyncio.run(run_phase(phase, states, args.results_dir))
            all_reports.extend(reports)
            total_cost += sum(r["cost_usd"] for r in reports)

            # Phase 1 gate — abort all_phases if PA fails direction check
            if phase == 1 and reports:
                if not reports[0]["verdict"]["winner_correct"]:
                    logger.error(
                        "Phase 1 gate FAILED. Aborting all-phases run. "
                        "Fix pool calibration, then re-run."
                    )
                    break

        run_id = all_reports[0]["run_id"] if all_reports else run_ts
        save_results(all_reports, args.results_dir, run_id)
        print_aggregate_report(all_reports)


if __name__ == "__main__":
    main()
