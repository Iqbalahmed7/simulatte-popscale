"""benchmarks/delhi_2025/delhi_2025_benchmark.py

Delhi Assembly Election 2025 — PopScale Benchmark Run.

PURPOSE
-------
Validate PopScale's predictive accuracy against a known real-world electoral
outcome. Most major polling houses predicted a close race or AAP advantage
ahead of the February 2025 Delhi assembly elections. The actual result was
a decisive BJP victory.

If PopScale's synthetic population correctly signals BJP plurality while
human pollsters missed it, that is strong evidence for the engine's
predictive value.

ACTUAL RESULTS (Feb 5, 2025 — Election Commission of India):
    BJP:      48 seats / ~47.5% vote share  ← decisive winner
    AAP:      22 seats / ~29.0% vote share  ← collapsed from 54% in 2020
    Congress: 0 seats  / ~6.3%  vote share
    Others:   0 seats  / ~17.2% vote share

BENCHMARK DESIGN
----------------
- 500 personas, Delhi profile (97.5% urban, income + religion stratified)
- Single-round scenario: vote intention question, 4 options
- Context anchored to facts available before election day
- We compare PopScale's option distribution against actual vote shares
- Accuracy metric: Mean Absolute Error across 4 parties

USAGE
-----
    # Dry run (no API calls, prints config and cost estimate):
    python delhi_2025_benchmark.py --dry-run

    # Live run (makes API calls, saves results):
    python delhi_2025_benchmark.py

    # Smaller cohort for faster iteration:
    python delhi_2025_benchmark.py --n 100

    # Load existing results and compare (no new API calls):
    python delhi_2025_benchmark.py --results-file results/delhi_2025_<run_id>.json
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
logger = logging.getLogger("delhi_2025_benchmark")

# ── Ground truth ──────────────────────────────────────────────────────────────

ACTUAL_VOTE_SHARES: dict[str, float] = {
    "BJP":      0.475,
    "AAP":      0.290,
    "Congress": 0.063,
    "Others":   0.172,
}

# Pre-election poll averages (Jan 2025 — the baseline we're trying to beat)
POLL_AVERAGES: dict[str, float] = {
    "BJP":      0.380,   # polls severely underestimated BJP
    "AAP":      0.380,   # polls overestimated AAP
    "Congress": 0.080,
    "Others":   0.160,
}

SCENARIO_OPTIONS = [
    "BJP (Bharatiya Janata Party)",
    "AAP (Aam Aadmi Party)",
    "Congress (INC)",
    "Other party / NOTA (smaller regional party, independent candidate, or None of the Above)",
]

# Map option text → party key for comparison
_OPTION_TO_PARTY: dict[str, str] = {
    "BJP (Bharatiya Janata Party)": "BJP",
    "AAP (Aam Aadmi Party)":        "AAP",
    "Congress (INC)":                "Congress",
    "Other / NOTA":                  "Others",
}


# ── Benchmark runner ──────────────────────────────────────────────────────────

def build_request(n_personas: int = 200) -> NiobeStudyRequest:
    """Build the NiobeStudyRequest for the Delhi 2025 benchmark.

    Budget cap scales with n_personas: $0.50/persona with a $5 floor.
    This prevents small calibration runs (--n 10) from being blocked by
    the fixed $20 cap while still guarding against runaway costs.
    """
    budget_cap = max(5.0, round(n_personas * 0.50, 2))
    return NiobeStudyRequest(
        study_name="Delhi Assembly Election 2025 — PopScale Benchmark",
        state="delhi",
        n_personas=n_personas,
        domain="india_general",
        research_question=(
            "How will Delhi voters distribute their vote in the February 2025 "
            "assembly election, and does BJP's national momentum overcome "
            "AAP's incumbency advantage?"
        ),
        scenario_question=(
            "Which party will you vote for in the upcoming Delhi assembly election?"
        ),
        scenario_context=(
            "Delhi assembly elections are scheduled for February 5, 2025. "
            "The incumbent AAP government — which has governed Delhi since 2015 and "
            "delivered free electricity (up to 200 units/month), free water (20 kL/month), "
            "450+ Mohalla Clinics, and improved government school infrastructure — is "
            "seeking a third consecutive term, led by Chief Minister Atishi after "
            "Arvind Kejriwal stepped down following his arrest in the liquor policy case. "
            "The party faces serious anti-incumbency: Kejriwal's credibility is under "
            "question due to the excise policy corruption case, and voters cite unresolved "
            "Yamuna pollution, water supply disruptions, and governance gaps. "
            "BJP, in national power since 2014 under Prime Minister Modi, is running on "
            "central scheme delivery, infrastructure investment, and the Ram Mandir "
            "consecration as a cultural touchstone, though the party has held no Delhi "
            "state office for 27 years and has governed the city last under Sushma Swaraj. "
            "Congress is contesting independently after the INDIA bloc failed to form a "
            "seat-sharing alliance for Delhi, though the party has been largely irrelevant "
            "in Delhi since 2015, winning 0 seats and less than 5% vote share in 2020. "
            "Many Delhi voters who lean neither BJP nor AAP are considering NOTA or "
            "smaller regional candidates. "
            "Key voter considerations: welfare scheme continuity vs. clean governance, "
            "Yamuna pollution remediation, law and order, rising cost of living, and "
            "Kejriwal's trustworthiness in light of the ongoing corruption case."
        ),
        scenario_options=SCENARIO_OPTIONS,
        stratify_by_religion=True,
        stratify_by_income=True,
        budget_cap_usd=budget_cap,
    )


async def run_benchmark(n_personas: int = 200) -> dict:
    """Run the full benchmark study and return raw results dict."""
    request = build_request(n_personas)
    logger.info("Starting Delhi 2025 benchmark | n=%d", n_personas)
    logger.info("Request: %s", request.summary())

    result = await run_niobe_study(request)

    logger.info("Study complete: %s", result.summary())
    return result


def extract_vote_shares(result) -> dict[str, float]:
    """Extract vote share per party from StudyResult.

    Matching strategy (most-specific first):
    1. Exact match against full option text (case-insensitive).
    2. Decision starts with the party abbreviation (e.g. "BJP", "AAP").
    3. Best-count fuzzy match: count mentions of EACH party abbreviation in the
       decision text and pick the one with the most mentions.  This avoids the
       original bug where BJP appeared as a comparison ("not BJP, but AAP") and
       was counted as a BJP vote because it was first in the dict.
    4. Fall through to Others.
    """
    responses = result.simulation.responses
    n_total = max(1, len(responses))
    counts: dict[str, int] = {p: 0 for p in ACTUAL_VOTE_SHARES}

    for r in responses:
        decision = r.decision.strip().lower()
        matched_party = None

        # 1. Exact full-option match
        for option_text, party in _OPTION_TO_PARTY.items():
            if decision == option_text.lower():
                matched_party = party
                break

        # 2. Starts with abbreviation (e.g. "bjp", "aap", "congress", "other")
        if matched_party is None:
            for option_text, party in _OPTION_TO_PARTY.items():
                abbr = option_text.split()[0].lower()
                if decision.startswith(abbr):
                    matched_party = party
                    break

        # 3. Best-count fuzzy: pick the party abbreviation that appears MOST
        #    often in the decision text.  Resolves "BJP vs AAP" ambiguity.
        if matched_party is None:
            mention_counts: dict[str, int] = {}
            for option_text, party in _OPTION_TO_PARTY.items():
                abbr = option_text.split()[0].lower()
                mention_counts[party] = decision.count(abbr)
            best_party = max(mention_counts, key=mention_counts.__getitem__)
            if mention_counts[best_party] > 0:
                matched_party = best_party

        counts[matched_party if matched_party else "Others"] += 1

    return {party: round(count / n_total, 4) for party, count in counts.items()}


def compute_mae(predicted: dict[str, float], actual: dict[str, float]) -> float:
    """Mean Absolute Error across all parties."""
    parties = list(actual.keys())
    total = sum(abs(predicted.get(p, 0.0) - actual[p]) for p in parties)
    return round(total / len(parties), 4)


def build_comparison_report(
    result,
    popscale_shares: dict[str, float],
    run_id: str,
    n_personas: int,
    cost_usd: float,
) -> dict:
    """Assemble the full benchmark comparison dict."""
    popscale_mae = compute_mae(popscale_shares, ACTUAL_VOTE_SHARES)
    poll_mae     = compute_mae(POLL_AVERAGES,   ACTUAL_VOTE_SHARES)

    parties = list(ACTUAL_VOTE_SHARES.keys())

    rows = []
    for party in parties:
        ps  = popscale_shares.get(party, 0.0)
        act = ACTUAL_VOTE_SHARES[party]
        poll = POLL_AVERAGES[party]
        rows.append({
            "party":            party,
            "popscale_pct":     round(ps * 100, 1),
            "actual_pct":       round(act * 100, 1),
            "poll_avg_pct":     round(poll * 100, 1),
            "popscale_error":   round(abs(ps - act) * 100, 1),
            "poll_error":       round(abs(poll - act) * 100, 1),
        })

    winner_popscale = max(popscale_shares, key=popscale_shares.__getitem__)
    winner_actual   = max(ACTUAL_VOTE_SHARES, key=ACTUAL_VOTE_SHARES.__getitem__)
    winner_correct  = winner_popscale == winner_actual

    return {
        "benchmark":          "Delhi Assembly Election 2025",
        "run_id":             run_id,
        "timestamp":          datetime.now(timezone.utc).isoformat(),
        "n_personas":         n_personas,
        "cost_usd":           round(cost_usd, 4),

        "verdict": {
            "winner_predicted":     winner_popscale,
            "winner_actual":        winner_actual,
            "winner_correct":       winner_correct,
            "popscale_mae_pct":     round(popscale_mae * 100, 2),
            "poll_avg_mae_pct":     round(poll_mae * 100, 2),
            "beats_polls":          popscale_mae < poll_mae,
        },

        "party_breakdown":    rows,
        "popscale_shares":    {p: round(v * 100, 1) for p, v in popscale_shares.items()},
        "actual_shares":      {p: round(v * 100, 1) for p, v in ACTUAL_VOTE_SHARES.items()},
        "poll_avg_shares":    {p: round(v * 100, 1) for p, v in POLL_AVERAGES.items()},
    }


def print_report(report: dict) -> None:
    """Print a formatted benchmark report to stdout."""
    v = report["verdict"]

    print("\n" + "═" * 65)
    print("  DELHI 2025 ELECTION BENCHMARK — POPSCALE VALIDATION REPORT")
    print("═" * 65)
    print(f"  Run ID   : {report['run_id']}")
    print(f"  Personas : {report['n_personas']}")
    print(f"  Cost     : ${report['cost_usd']:.4f}")
    print()

    # Party breakdown table
    print(f"  {'Party':<12} {'PopScale':>10} {'Actual':>10} {'Polls':>10} {'PS Err':>8} {'Poll Err':>9}")
    print("  " + "-" * 61)
    for row in report["party_breakdown"]:
        print(
            f"  {row['party']:<12} "
            f"{row['popscale_pct']:>9.1f}% "
            f"{row['actual_pct']:>9.1f}% "
            f"{row['poll_avg_pct']:>9.1f}% "
            f"{row['popscale_error']:>7.1f}pp "
            f"{row['poll_error']:>8.1f}pp"
        )
    print()

    # Verdict
    winner_icon = "✓" if v["winner_correct"] else "✗"
    beats_icon  = "✓" if v["beats_polls"]    else "✗"
    print(f"  [{winner_icon}] Winner predicted correctly : {v['winner_predicted']} (actual: {v['winner_actual']})")
    print(f"  [{beats_icon}] Beats pre-election polls   : PopScale MAE {v['popscale_mae_pct']:.1f}pp vs Polls MAE {v['poll_avg_mae_pct']:.1f}pp")
    print()

    if v["winner_correct"] and v["beats_polls"]:
        print("  RESULT: PASS — PopScale predicted the winner AND beat the polls.")
    elif v["winner_correct"]:
        print("  RESULT: PARTIAL PASS — Correct winner, but MAE above poll baseline.")
    else:
        print("  RESULT: FAIL — Wrong winner predicted.")

    print("═" * 65 + "\n")


def save_results(report: dict, results_dir: Path) -> Path:
    """Save report JSON to results directory."""
    results_dir.mkdir(parents=True, exist_ok=True)
    run_id = report["run_id"]
    out_path = results_dir / f"delhi_2025_{run_id}.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    logger.info("Results saved → %s", out_path)
    return out_path


def load_and_compare(results_file: Path) -> None:
    """Load an existing results file and re-print the comparison report."""
    with open(results_file) as f:
        report = json.load(f)
    print_report(report)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Delhi 2025 Assembly Election — PopScale benchmark run"
    )
    parser.add_argument(
        "--n", type=int, default=200,
        help="Number of personas (default: 200). Use --n 10 for a cost calibration run (~$1-3).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print config and cost estimate without making API calls",
    )
    parser.add_argument(
        "--calibrate", action="store_true",
        help=(
            "Cost calibration mode: run with --n personas, report actual cost-per-persona "
            "and cost-per-delivered-persona. Use --n 10 to measure real API cost before "
            "committing to a full run. Does not validate against ground truth."
        ),
    )
    parser.add_argument(
        "--results-file", type=Path, default=None,
        help="Load and compare an existing results JSON (skips live run)",
    )
    parser.add_argument(
        "--results-dir", type=Path,
        default=Path(__file__).parent / "results",
        help="Directory to save results JSON (default: ./results/)",
    )
    args = parser.parse_args()

    # ── Load existing results ─────────────────────────────────────────────
    if args.results_file:
        load_and_compare(args.results_file)
        return

    # ── Dry run ───────────────────────────────────────────────────────────
    request = build_request(args.n)
    if args.dry_run:
        from popscale.study.study_runner import StudyConfig, estimate_study_cost
        from popscale.calibration.population_spec import PopulationSpec
        from popscale.scenario.model import Scenario, SimulationDomain
        _spec = PopulationSpec(
            state=request.state, n_personas=request.n_personas,
            domain=request.domain, business_problem=request.research_question,
            stratify_by_religion=request.stratify_by_religion,
            stratify_by_income=request.stratify_by_income,
        )
        _scenario = Scenario(
            question=request.scenario_question,
            context=request.scenario_context,
            options=request.scenario_options,
            domain=SimulationDomain.POLITICAL,
        )
        _config = StudyConfig(spec=_spec, scenario=_scenario)
        est_cost = estimate_study_cost(_config)
        print("\n── Delhi 2025 Benchmark — DRY RUN ──────────────────────────")
        print(f"  Request  : {request.summary()}")
        print(f"  State    : {request.state}")
        print(f"  Personas : {request.n_personas}")
        print(f"  Domain   : {request.domain}")
        print(f"  Religion : stratified={request.stratify_by_religion}")
        print(f"  Income   : stratified={request.stratify_by_income}")
        print(f"  Est cost : ${est_cost:.2f}")
        print(f"  Budget   : ${request.budget_cap_usd}")
        print("\n  Scenario options:")
        for i, opt in enumerate(SCENARIO_OPTIONS, 1):
            print(f"    {i}. {opt}")
        print("\n  Ground truth to validate against:")
        for party, share in ACTUAL_VOTE_SHARES.items():
            print(f"    {party:<12} {share*100:.1f}%")
        print("─" * 60 + "\n")
        return

    # ── Calibrate run ─────────────────────────────────────────────────────
    if args.calibrate:
        print(f"\n── Delhi 2025 Benchmark — CALIBRATION RUN (n={args.n}) ────────")
        print(f"  This run measures real API cost-per-persona.")
        print(f"  Budget cap: ${max(5.0, round(args.n * 0.50, 2)):.2f}\n")
        result = asyncio.run(run_benchmark(args.n))
        n_delivered = result.cohort.total_delivered
        n_requested = args.n
        cost_total = result.total_cost_usd
        cost_gen = result.cohort.total_cost_usd
        cost_sim = result.simulation.cost_actual_usd
        print("\n── Cost Calibration Results ────────────────────────────────────")
        print(f"  Personas requested:     {n_requested}")
        print(f"  Personas delivered:     {n_delivered}")
        print(f"  Delivery rate:          {n_delivered/max(n_requested,1):.0%}")
        print(f"")
        print(f"  Generation cost:        ${cost_gen:.4f}")
        print(f"  Simulation cost:        ${cost_sim:.4f}")
        print(f"  Total cost:             ${cost_total:.4f}")
        print(f"")
        if n_delivered > 0:
            print(f"  Cost per persona:       ${cost_total/n_delivered:.4f}")
            print(f"  Gen cost per persona:   ${cost_gen/n_delivered:.4f}")
            print(f"  Sim cost per persona:   ${cost_sim/n_delivered:.4f}")
            print(f"")
            print(f"  Projected cost @ 200p:  ${cost_total/n_delivered*200:.2f}")
            print(f"  Projected cost @ 500p:  ${cost_total/n_delivered*500:.2f}")
        else:
            print(f"  ⚠ No personas delivered — cannot compute per-persona cost.")
            print(f"  Check API credits and PG configuration.")
        print("─" * 60 + "\n")
        return

    # ── Live run ──────────────────────────────────────────────────────────
    result = asyncio.run(run_benchmark(args.n))

    popscale_shares = extract_vote_shares(result)
    report = build_comparison_report(
        result=result,
        popscale_shares=popscale_shares,
        run_id=result.run_id,
        n_personas=result.n_personas,
        cost_usd=result.total_cost_usd,
    )

    print_report(report)
    out_path = save_results(report, args.results_dir)
    print(f"Full results → {out_path}")


if __name__ == "__main__":
    main()
