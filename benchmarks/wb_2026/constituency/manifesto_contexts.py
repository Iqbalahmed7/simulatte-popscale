"""manifesto_contexts.py

WB 2026 party manifesto summaries for sensitivity injection.
These texts are injected appended to BASE_SCENARIO_CONTEXT
when --manifesto is set. They summarise key manifesto planks
that are electorally salient in the swing clusters.

Sources: BJP WB 2026 manifesto (released April 1, 2026),
         TMC 2026 manifesto (released March 28, 2026).
"""

TMC_MANIFESTO_CONTEXT = """\
[TMC 2026 MANIFESTO - INJECTED FOR SENSITIVITY TEST]
Trinamool Congress released its 2026 manifesto on March 28.
Key pledges voters are weighing:

WELFARE EXPANSION:
- Lakshmir Bhandar monthly stipend raised from Rs500 to Rs1,200 (SC/ST women) and Rs1,000 (general). Existing recipients get automatic upgrade.
- Krishak Bandhu farm support doubled to Rs10,000/year per acre, extended to sharecroppers and bargadars for the first time.
- Kanyashree scheme age ceiling raised from 18 to 45. Married women included.
- Swasthya Sathi health coverage extended to private hospital empanelment in all 23 districts; cashless for up to Rs5 lakh/year.

EMPLOYMENT:
- 5 lakh new factory jobs by 2028 under "Banglar Gorbo" industrial corridor (Durgapur-Haldia-Kharagpur axis).
- 2 lakh government recruitment drives within 18 months (Group C and D).
- Gig worker protection law: minimum wage guarantee for app-based workers.

GOVERNANCE / SIR:
- Commission to review and restore SIR-deleted voter names within 90 days.
- Duare Sarkar expanded to 12 new scheme categories.
- Anti-cut-money law: any TMC functionary caught extorting scheme beneficiaries faces expulsion + criminal case.

IDENTITY / COMMUNAL:
- NRC will NOT be implemented in West Bengal under any circumstances.
- CAA documents process: TMC will provide legal aid to Muslim families facing citizenship queries free of cost.
- Matua community: SIR deletions in Nadia and N24Pgs to be manually reviewed with Matua Mahasangha partnership.
"""

BJP_MANIFESTO_CONTEXT = """\
[BJP 2026 MANIFESTO - INJECTED FOR SENSITIVITY TEST]
BJP released its WB 2026 manifesto on April 1.
Key pledges voters are weighing:

CAA / CITIZENSHIP:
- CAA implementation within 60 days of BJP forming government. Citizenship certificates to be issued to all eligible Matua, Rajbanshi, and Hindu refugee families from Bangladesh.
- NRC: "Will be implemented in a phased, fair manner - no genuine Indian will be affected."
- Matua-specific: Dedicated Matua Welfare Board with Rs500 crore annual budget.

CENTRAL SCHEME DELIVERY:
- PM Awas Yojana: 10 lakh homes sanctioned but blocked by TMC government to be released within 100 days.
- PM Kisan Rs6,000/year extended to tenant farmers and sharecroppers (not just landowners).
- Rs500 LPG cylinder cap for BPL households under Ujjwala 2.0.
- One Nation One Ration Card: full portability across Bengal within 6 months.

EMPLOYMENT / ECONOMY:
- 10 lakh jobs via MSME Suraksha scheme (Rs5,000 crore fund for small enterprise lending in Bengal).
- IT/BPO corridor in New Town Kolkata: 50,000 tech jobs target by 2027.
- Tourism circuit: Sunderbans, Shantiniketan, Bishnupur. 20,000 hospitality jobs.

GOVERNANCE:
- Anti-corruption commission independent of state government.
- SIR transparent review: national Election Commission oversight.
- "Suraksha Kavach": 24x7 women's safety taskforce in all districts.

IDENTITY:
- "Sonar Bangla" Hindu cultural renaissance program.
- Ram Mandir yatra subsidy for BPL families from Bengal.
- Durga Puja: central funding for heritage puja committees blocked by TMC.
"""

BOTH_MANIFESTO_CONTEXT = (
    TMC_MANIFESTO_CONTEXT
    + "\n\n"
    + BJP_MANIFESTO_CONTEXT
)

MANIFESTO_CONTEXTS: dict[str, str] = {
    "tmc": TMC_MANIFESTO_CONTEXT,
    "bjp": BJP_MANIFESTO_CONTEXT,
    "both": BOTH_MANIFESTO_CONTEXT,
}
