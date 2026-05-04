# WB 2026 — Post-Election Tracking

**Counting day:** 4 May 2026
**Constituencies counted today:** 293 of 294 (Falta re-poll on 21 May)
**Voter turnout:** 92.47%

---

## Our staked prediction (frozen — `The_Construct_WB2026_Study_Report.docx`)

| Party | Range | Staked number | Lean |
|---|---|---|---|
| **TMC** | 185 – 210 | **194 ± 10** | Most likely holder of majority |
| **BJP** | 25 – 55 | 45 ± 10 | Adjusted upward for org depth |
| **Left-Congress** | 50 – 75 | 50 ± 10 | Adjusted downward for conversion gap |
| **Others** | 2 – 8 | 5 ± 3 | AIMIM solo · GJM · independents |

**Total:** 294 seats. Majority: 148.

**Headline call:** TMC retains majority comfortably. BJP gains modestly off 2021 floor but stays below 60. Left-Congress recovers from 2021 wipeout into low double digits per cluster.

---

## Live trend snapshots

### Snapshot 1 — early counting (postal + early EVM rounds, ~9:30 AM IST)

Source: ECI live + multiple media outlets

| Party | ECI early lead | Notes |
|---|---|---|
| BJP | 109 → 140 → 148+ (rising) | Crossed majority mark in trends |
| TMC | 47 → 72 | Trailing significantly |
| Left-Congress | not yet specified | — |
| Others | — | — |

**Suvendu Adhikari (BJP) framing:** "Hindu consolidation"
**Turnout:** 92.47% — abnormally high, historically associated with anti-incumbency waves

### Snapshot 2 — [pending]

---

## Directional read (provisional, early)

If trends hold:
- **TMC majority call: WRONG** (we said 185–210; trend says ~70–85)
- **BJP scale: WRONG** (we said 25–55; trend says 140+)
- **Magnitude of miss:** ~100 seat gap between our TMC central estimate and trend
- **Sign of miss:** symmetric in opposite direction on TMC and BJP

This would be a directional-call failure (winner wrong) — the worst possible outcome metric.

---

## Caveats before declaring

1. Postal ballots counted first — historically skew BJP in Bengal (police, paramilitary, urban absentee voters). Postal share is ~3–4% of total.
2. Early EVM rounds favour urban/semi-urban polling stations — also BJP-favourable terrain.
3. Rural Muslim-belt and Jungle Mahal stations count later. These are TMC strongholds in our model.
4. 92.47% turnout is unusually high — this is the strongest prior-counting signal of a wave, but cuts in **either** direction.
5. Final tally not expected until 4–6 PM IST.

**Action:** continue tracking through every counting window. Lock final numbers only when ECI declares 290+ seats.

---

## Tracking cadence

- Pull updated trend every 30 minutes from 9:30 AM IST until counting completes
- Note: ECI live URL → `https://results.eci.gov.in/`
- Compare against frozen prediction above; do not edit prediction post-hoc

---

## Post-counting deliverables

1. Final actual seat tally — ECI (293 seats; Falta deferred to 21 May)
2. `backcast()` against actuals once GT loaded → MAE / Brier / directional accuracy
3. `decompose_bias()` → which clusters/demographics were most wrong
4. Prior adjustment recommendations for next study (calibration loop input)
5. Honest post-mortem report — `engineering/POST_ELECTION_POSTMORTEM_WB2026.md`
