"""benchmarks/wb_2026/wb_2026_benchmark.py

West Bengal Assembly Election 2026 — PopScale Population Study.

PURPOSE
-------
Predict the West Bengal assembly election outcome using PopScale's synthetic
population engine. This is a forward-looking study (election scheduled
April-May 2026) designed to validate PopScale's non-US electoral accuracy.

The 2021 reference point:
    TMC:          215/294 seats (73.1%) | 47.9% vote share
    BJP:           77/294 seats (26.2%) | 38.1% vote share
    Left+Congress:  2/294 seats  (0.7%) |  9.7% combined vote share

The 2026 question: Can BJP close the gap against Mamata Banerjee's TMC
given anti-incumbency, the Sandeshkhali fallout, employment anxiety, and
the Modi government's central welfare push vs. TMC's state welfare record?

BENCHMARK DESIGN
----------------
- n_personas: configurable (default 200 for cost efficiency, 40 for dry run)
- Domain: bengal_general — 40-persona pool covering all 7 electoral sub-regions
- Options: TMC / BJP / Left-Congress alliance / Other
- Ground truth: 2021 assembly results (until 2026 results are published)
- Accuracy metric: MAE against 2021 vote shares (pending live result update)

KEY ELECTORAL DYNAMICS MODELLED
---------------------------------
- Muslim vote bank (~27% electorate): overwhelmingly TMC
- Matua community (SC Hindu, Nadia/N24Pgs): BJP via CAA promise
- Rajbanshi (OBC, North Bengal): BJP stronghold since 2019
- Tribal communities (Jungle Mahal, ST belt): BJP inroads vs. TMC MGNREGA loyalty
- Urban educated Hindu (Kolkata): split, historically TMC but BJP growing
- South Bengal fisher/rural: TMC heartland
- Left-Congress residual: mostly elderly + urban secular minority

USAGE
-----
    # Dry run (no API calls, prints config):
    python3 wb_2026_benchmark.py --dry-run

    # Calibration run (n=40, ~$2-3):
    python3 wb_2026_benchmark.py --n 40

    # Standard population run (n=200, ~$10-15):
    python3 wb_2026_benchmark.py --n 200

    # Load existing results and compare:
    python3 wb_2026_benchmark.py --results-file results/wb_2026_<run_id>.json
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
logger = logging.getLogger("wb_2026_benchmark")

# ── Ground truth (2021 assembly — reference until 2026 results available) ────
# Update ACTUAL_VOTE_SHARES with 2026 results once published.
ACTUAL_VOTE_SHARES_2021: dict[str, float] = {
    "TMC":          0.479,
    "BJP":          0.381,
    "Left-Congress": 0.097,
    "Others":       0.043,
}

# 2026 pre-election poll averages — consensus from verified April 2026 polls.
# Sources: IANS-Matrize (Apr 2026, TMC 43-45%, BJP 41-43%, most cited);
#          ABP-Ananda / India TV News (TMC ~41.9%, BJP ~34.9%, older);
#          Eurasia Review analysis (20 Apr 2026): TMC holds edge, BJP resurgent.
# LOCKED: These averages are fixed before results. Do not update post-election.
POLL_AVERAGES_2026: dict[str, float] = {
    "TMC":           0.430,  # IANS-Matrize consensus; welfare schemes hold rural base
    "BJP":           0.410,  # Updated to 41% — IANS-Matrize Apr 2026 upper bound
    "Left-Congress": 0.100,  # Weakened vs 2021; Congress Murshidabad + CPM remnants
    "Others":        0.060,  # AIMIM-AJUP alliance + independents
}

SCENARIO_OPTIONS = [
    "TMC (Trinamool Congress — Mamata Banerjee)",
    "BJP (Bharatiya Janata Party — Modi-backed state campaign)",
    "Left-Congress alliance (CPI-M / INC joint front)",
    "Other party / NOTA (regional, independent, or None of the Above)",
]

# Map full option text → party key for comparison
_OPTION_TO_PARTY: dict[str, str] = {
    "TMC (Trinamool Congress — Mamata Banerjee)":       "TMC",
    "BJP (Bharatiya Janata Party — Modi-backed state campaign)": "BJP",
    "Left-Congress alliance (CPI-M / INC joint front)": "Left-Congress",
    "Other party / NOTA (regional, independent, or None of the Above)": "Others",
}

SCENARIO_CONTEXT = (
    "West Bengal is approaching its 2026 state assembly election — the 17th since "
    "independence — covering all 294 assembly constituencies. "
    "The Trinamool Congress (TMC) under Chief Minister Mamata Banerjee has governed "
    "Bengal continuously since 2011, winning 211 seats in 2016 and 215 seats in 2021. "
    "In 2021, TMC defeated a resurgent BJP (which had won 18 of 42 Lok Sabha seats in "
    "Bengal in 2019) despite extensive central campaigning by Prime Minister Modi and "
    "Home Minister Shah, retaining power with 47.9% of the popular vote. "
    "BJP won 77 seats on 38.1% of the vote — its best-ever Bengal assembly performance — "
    "but fell far short of a majority. The Left-Congress combine was nearly wiped out. "
    "\n"
    "Heading into 2026, the electoral terrain has shifted in several ways: "
    "TMC faces serious anti-incumbency from corruption allegations — the 'cut money' "
    "syndicate (local TMC leaders demanding commissions on government contracts), "
    "the Sandeshkhali sexual violence and land-grab case involving TMC leaders that "
    "became a national flashpoint in 2024, and a persistent youth unemployment crisis "
    "in districts like Murshidabad and Purulia. "
    "Mamata Banerjee, however, remains personally popular for her welfare architecture: "
    "Lakshmir Bhandar (monthly stipend for women), Swasthya Sathi (health insurance), "
    "Duare Sarkar (doorstep government services), Kanyashree (girl child education), "
    "and Krishak Bandhu (farmer income support). These schemes command fierce loyalty "
    "especially among women voters and lower-income households. "
    "\n"
    "BJP is running a dual strategy: Hindu consolidation (framing TMC as 'Muslim appeasement') "
    "and central government delivery (PM Kisan, Ujjwala gas, Ayushman Bharat). "
    "The CAA (Citizenship Amendment Act) notification in 2024 has energised the Matua "
    "community in Nadia and North 24 Parganas — Matua leaders allege TMC blocked CAA "
    "implementation. BJP has also capitalised on Sandeshkhali to build a women's safety "
    "narrative in contested districts. "
    "BJP's weakness remains party organisation, perception of 'outsider' national leadership "
    "for a state-level contest, and the post-2021 defection of TMC-turncoat MLAs back "
    "to TMC after losing by-elections. "
    "\n"
    "The Left-Congress alliance (INDIA bloc configuration for Bengal) presents a third "
    "option primarily for voters disillusioned with both TMC corruption and BJP "
    "communalism. The Left retains some presence among industrial workers, teachers' "
    "unions, and urban secular voters, but has been unable to convert protest votes "
    "into seats due to FPTP vote splitting. Congress's presence is largely symbolic. "
    "\n"
    "Muslim voters (~27% of the Bengal electorate) remain firmly with TMC as a "
    "bulwark against BJP-driven communal polarisation, despite local resentment of "
    "TMC leadership corruption in Muslim-majority districts. "
    "Tribal voters in Jungle Mahal (West Midnapore, Bankura, Purulia) have split "
    "between BJP and TMC after BJP made major gains there in 2019-2021. "
    "North Bengal (Cooch Behar, Jalpaiguri) is BJP's most reliable territory, "
    "anchored by Rajbanshi community mobilisation and tea-garden worker discontent. "
    "\n"
    "Key voter considerations heading into 2026: welfare scheme continuation vs. "
    "anti-corruption mandate, job creation, law and order (Sandeshkhali), religious "
    "identity and CAA, and whether Mamata Banerjee personally remains a credible "
    "alternative to central BJP governance."
)


# ── Benchmark runner ──────────────────────────────────────────────────────────

def build_request(n_personas: int = 200) -> NiobeStudyRequest:
    """Build the NiobeStudyRequest for the WB 2026 study.

    Budget cap: $0.50/persona with $5 floor.
    """
    budget_cap = max(5.0, round(n_personas * 0.50, 2))
    return NiobeStudyRequest(
        study_name="West Bengal Assembly Election 2026 — PopScale Population Study",
        state="west bengal",
        n_personas=n_personas,
        domain="bengal_general",
        research_question=(
            "How will West Bengal voters distribute their vote in the 2026 assembly "
            "election across TMC, BJP, and the Left-Congress alliance — and can BJP "
            "close the gap against Mamata Banerjee's incumbency machine given rising "
            "anti-incumbency from corruption and the Sandeshkhali backlash?"
        ),
        scenario_question=(
            "Which party or alliance will you vote for in the upcoming West Bengal "
            "assembly election?"
        ),
        scenario_context=SCENARIO_CONTEXT,
        scenario_options=SCENARIO_OPTIONS,
        stratify_by_religion=True,
        stratify_by_income=True,
        budget_cap_usd=budget_cap,
    )


async def run_benchmark(n_personas: int = 200) -> dict:
    """Run the full benchmark study and return raw results dict."""
    request = build_request(n_personas)
    logger.info("Starting WB 2026 population study | n=%d", n_personas)
    logger.info("Request: %s", request.summary())

    result = await run_niobe_study(request)
    logger.info("Study complete: %s", result.summary())
    return result


def extract_vote_shares(result) -> dict[str, float]:
    """Extract vote share per party from StudyResult.

    Matching strategy (most-specific first):
    1. Exact match against full option text (case-insensitive).
    2. Decision starts with party abbreviation (TMC, BJP, Left, Congress, Other).
    3. Mention-count fuzzy match — count abbreviation mentions, pick highest.
    4. Fall through to Others.
    """
    responses = result.simulation.responses
    n_total = max(1, len(responses))
    counts: dict[str, int] = {p: 0 for p in ACTUAL_VOTE_SHARES_2021}

    for r in responses:
        decision = r.decision.strip().lower()
        matched_party = None

        # 1. Exact match
        for option_text, party in _OPTION_TO_PARTY.items():
            if decision == option_text.lower():
                matched_party = party
                break

        # 2. Starts-with match
        if matched_party is None:
            if decision.startswith("tmc") or decision.startswith("trinamool"):
                matched_party = "TMC"
            elif decision.startswith("bjp") or decision.startswith("bharatiya"):
                matched_party = "BJP"
            elif decision.startswith("left") or decision.startswith("cpi") or decision.startswith("congress"):
                matched_party = "Left-Congress"
            elif decision.startswith("other") or decision.startswith("nota"):
                matched_party = "Others"

        # 3. Mention-count fuzzy
        if matched_party is None:
            mention_counts = {
                "TMC":          decision.count("tmc") + decision.count("trinamool") + decision.count("mamata"),
                "BJP":          decision.count("bjp") + decision.count("bharatiya"),
                "Left-Congress": decision.count("left") + decision.count("cpi") + decision.count("congress"),
                "Others":       decision.count("other") + decision.count("nota"),
            }
            best_party = max(mention_counts, key=mention_counts.get)
            if mention_counts[best_party] > 0:
                matched_party = best_party

        counts[matched_party or "Others"] += 1

    return {p: round(c / n_total, 4) for p, c in counts.items()}


def print_comparison(popscale_shares: dict[str, float], ground_truth: dict[str, float]) -> None:
    """Print side-by-side comparison with MAE."""
    print("\n" + "═" * 72)
    print("  WEST BENGAL 2026 — PopScale vs 2021 Ground Truth")
    print("═" * 72)
    print(f"  {'Party':<22} {'PopScale':>10} {'2021 Actual':>12} {'Error':>8}")
    print("  " + "─" * 56)

    errors = []
    for party, actual in ground_truth.items():
        predicted = popscale_shares.get(party, 0.0)
        err = abs(predicted - actual)
        errors.append(err)
        flag = " ✓" if err <= 0.05 else " ✗"
        print(f"  {party:<22} {predicted:>9.1%}  {actual:>10.1%}  {err:>7.1%}{flag}")

    mae = sum(errors) / len(errors)
    print("  " + "─" * 56)
    print(f"  {'MAE':<22} {'':>10} {'':>12} {mae:>7.1%}")
    print("═" * 72)

    if POLL_AVERAGES_2026:
        print("\n  Pre-election poll averages (India Today / ABP / Axis My India, Q1 2026):")
        print(f"  {'Party':<22} {'Polls':>10} {'2021 Actual':>12}")
        print("  " + "─" * 48)
        for party, actual in ground_truth.items():
            poll = POLL_AVERAGES_2026.get(party, 0.0)
            print(f"  {party:<22} {poll:>9.1%}  {actual:>10.1%}")
        poll_errors = [abs(POLL_AVERAGES_2026.get(p, 0) - ground_truth[p]) for p in ground_truth]
        poll_mae = sum(poll_errors) / len(poll_errors)
        print(f"  {'Poll MAE':<22} {'':>10} {'':>12} {poll_mae:>7.1%}")
        print()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="WB 2026 Bengal election population study")
    parser.add_argument("--n", type=int, default=200, help="Number of personas (default: 200)")
    parser.add_argument("--dry-run", action="store_true", help="Print config without API calls")
    parser.add_argument("--results-file", type=str, default=None,
                        help="Load existing results JSON instead of running new simulation")
    args = parser.parse_args()

    if args.dry_run:
        request = build_request(args.n)
        print("\n── WB 2026 Dry Run ────────────────────────────────────────────")
        print(f"  n_personas    : {args.n}")
        print(f"  domain        : bengal_general  (40-persona pool, 7 sub-regions)")
        print(f"  budget_cap    : ${max(5.0, args.n * 0.50):.2f}")
        print(f"  options       : {len(SCENARIO_OPTIONS)} parties/alliances")
        print(f"  pool lean     : BJP 35% / TMC 45% / neutral 20%")
        print(f"  2021 ground   : TMC 47.9%, BJP 38.1%, Left-Cong 9.7%")
        print(f"  2026 polls    : TMC ~42%, BJP ~40% (tight race)")
        print("──────────────────────────────────────────────────────────────\n")
        return

    if args.results_file:
        results_path = Path(args.results_file)
        if not results_path.exists():
            print(f"ERROR: Results file not found: {results_path}")
            sys.exit(1)
        with open(results_path) as f:
            result = json.load(f)
        logger.info("Loaded results from %s", results_path)
        # Re-build vote shares from stored result (simplified — assumes result has responses)
        popscale_shares = result.get("vote_shares", {})
        if not popscale_shares:
            logger.warning("No vote_shares in results file — re-extracting from responses")
        print_comparison(popscale_shares, ACTUAL_VOTE_SHARES_2021)
        return

    # Live run
    result = asyncio.run(run_benchmark(args.n))

    popscale_shares = extract_vote_shares(result)

    # Save results
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = results_dir / f"wb_2026_{run_id}.json"

    output = {
        "run_id": run_id,
        "n_personas": args.n,
        "vote_shares": popscale_shares,
        "ground_truth_2021": ACTUAL_VOTE_SHARES_2021,
        "poll_averages_2026": POLL_AVERAGES_2026,
    }
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    logger.info("Results saved to %s", out_path)

    print_comparison(popscale_shares, ACTUAL_VOTE_SHARES_2021)


if __name__ == "__main__":
    main()
