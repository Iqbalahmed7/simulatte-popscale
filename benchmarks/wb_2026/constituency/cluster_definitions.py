"""cluster_definitions.py — B-WB-7

Constituency cluster metadata for West Bengal 2026 assembly election.
10 clusters covering all 294 seats.

B-WB-7 changes vs B-WB-6:
  - Swing clusters (Presidency, Jungle Mahal, Matua Belt, Burdwan) upgraded to
    60 personas + 3-run ensemble averaging for tighter confidence bounds.
  - Stable clusters upgraded to 30-40 personas.
  - marginal_seats_2021 added from ECI 2021 data for accurate uncertainty modelling.
  - Cube-law FPTP seat model enabled in seat_model.py.

Each cluster dict contains:
  domain              : PG domain key (maps to cluster persona pool)
  n_seats             : Number of assembly seats in this cluster
  tmc_2021            : TMC vote share 2021 (baseline)
  bjp_2021            : BJP vote share 2021 (baseline)
  left_2021           : Left-Congress vote share 2021 (baseline)
  others_2021         : Others vote share 2021 (baseline)
  n_personas          : Personas to run per cluster (per ensemble run)
  marginal_seats_2021 : Seats decided by <5pp margin in 2021 (ECI-informed)
  context_note        : District-specific 2026 context injected into scenario
  swing_notes         : Key 2026 dynamics affecting this cluster
"""
from __future__ import annotations

CLUSTERS: list[dict] = [
    {
        "id": "murshidabad",
        "name": "Murshidabad Muslim Heartland",
        "domain": "bengal_murshidabad",
        "n_seats": 22,
        "tmc_2021": 0.90,
        "bjp_2021": 0.10,
        "left_2021": 0.00,
        "others_2021": 0.00,
        "n_personas": 40,
        "marginal_seats_2021": 5,
        "context_note": (
            "Murshidabad district, 66% Muslim. TMC won 20 of 22 seats in 2021. "
            "In 2026: 4.6 lakh voter-roll deletions, predominantly Muslim names (SIR process). "
            "TMC welfare schemes (Lakshmir Bhandar, Swasthya Sathi) remain active. "
            "Cut-money corruption and Sandeshkhali are live grievances against TMC. "
            "\n"
            "KEY EVENT — 10 April 2026: AIMIM-AJUP alliance collapsed. "
            "TMC released a sting video alleging Humayun Kabir (AJUP founder, ex-TMC MLA) "
            "discussed a Rs 1,000 crore deal with BJP for a Deputy CM post. "
            "AIMIM (Owaisi) immediately withdrew, citing integrity concerns; now contesting "
            "11 Bengal seats independently. Humayun Kabir called the video an AI deepfake "
            "and declared AJUP would contest 182 seats solo. BJP denied any connection. "
            "\n"
            "Four vote destinations now exist: "
            "(1) TMC — defensive, welfare-based, hold-your-nose anti-BJP consolidation. "
            "(2) AIMIM solo — Owaisi's principled exit, 11 focused seats. "
            "(3) AJUP solo — Humayun's local credibility vs deepfake doubt, 182-seat scatter. "
            "(4) INDI Alliance (Congress-Left) — Adhir Ranjan's residual Murshidabad base, "
            "secular channel, doesn't split Muslim vote the way AJUP does. "
            "BJP benefits only via Hindu consolidation (28-32%) if Muslim vote fragments. "
            "\n"
            "2026 MANIFESTO WRINKLE: BJP Sankalp Patra (April 10, same day as coalition break) "
            "promises Uniform Civil Code within 6 months of forming govt — widely read as "
            "targeting Muslim personal law (marriage, inheritance, adoption). This sharpens "
            "the defensive consolidation question: among the four destinations (TMC/AIMIM/AJUP/"
            "INDI), which can actually stop a BJP government that would implement UCC? "
            "TMC has the strongest organisational capacity to win seats and block BJP. "
            "AIMIM/AJUP split the Muslim vote at the seat level. INDI (Congress-Left) "
            "is a secular channel without fragmentation risk. UCC threat adds weight to the "
            "'who can actually stop BJP' criterion over 'who best represents us'."
        ),
        "swing_notes": "SIR 460k deletions; April 10 AIMIM-AJUP coalition break via sting video; four-way Muslim vote fragmentation (TMC/AIMIM/AJUP/INDI); BJP UCC promise sharpens defensive consolidation; BJP upside via fragmentation pluralities",
        "key_seats": ["Bhagabangola", "Jalangi", "Farakka", "Domkal", "Kandi"],
    },
    {
        "id": "malda",
        "name": "Malda Muslim Plurality Belt",
        "domain": "bengal_malda",
        "n_seats": 12,
        "tmc_2021": 0.67,
        "bjp_2021": 0.33,
        "left_2021": 0.00,
        "others_2021": 0.00,
        "n_personas": 40,
        "marginal_seats_2021": 5,
        "context_note": (
            "You are voting in the Malda district — Muslim-plurality (51%) with significant "
            "Hindu population. TMC won 8 of 12 seats in 2021 but BJP has a real base here. "
            "2026 adds complexity: 2.4 lakh voter deletions under SIR; AIMIM, ISF, and AJUP "
            "are all fielding candidates, creating a potential three-way Muslim vote split. "
            "The mango-farming and border-trading economy depends on state welfare schemes. "
            "Hindu voters have historically been a BJP reservoir since 2019."
        ),
        "swing_notes": "SIR 240k deletions; AIMIM-ISF-AJUP three-way Muslim split; BJP Hindu base",
        "key_seats": ["Englishbazar", "Mothabari", "Ratua", "Harishchandrapur"],
    },
    {
        "id": "matua_belt",
        "name": "Matua Refugee Belt (Nadia + N24Pgs)",
        "domain": "bengal_matua_belt",
        "n_seats": 40,
        "tmc_2021": 0.65,
        "bjp_2021": 0.30,
        "left_2021": 0.05,
        "others_2021": 0.00,
        "n_personas": 25,
        "marginal_seats_2021": 18,
        "context_note": (
            "You are voting in the Matua belt — Nadia and North 24 Parganas — home to "
            "1.3 crore Matua (Namasudra) voters, Hindu SC refugees from Bangladesh. "
            "BJP won this belt in 2021 on the CAA promise of fast-track citizenship. "
            "But in 2026, the SIR voter roll process deleted 77% of reviewed voters in Nadia "
            "— including many Matua families whose documentation was incomplete. "
            "Matua leaders are protesting BJP's failure to deliver citizenship plus the SIR "
            "disaster hitting their own community. "
            "\n"
            "2026 MANIFESTO CROSS-PRESSURE: "
            "TMC (top 3): (1) Lakshmir Bhandar hiked to Rs 1,500 general / Rs 1,700 SC-ST, "
            "delivered to accounts before polling (not a promise). "
            "(2) Duare Chikitsa doorstep healthcare. "
            "(3) Continued scheme delivery (Swasthya Sathi, Krishak Bandhu). "
            "BJP Sankalp Patra (top 3): (1) Rs 3,000/month women's DBT, conditional on forming govt. "
            "(2) CAA delivery commitment — renewed Matua citizenship pledge. "
            "(3) Uniform Civil Code within 6 months — cross-cutting identity pressure. "
            "Core question: does the Rs 1,500 delivered today + SIR rage at BJP outweigh "
            "the Rs 3,000 promise + renewed CAA pledge? "
            "\n"
            "NATIONALISM STRESS-TEST: Assume Modi is actively pitching Bengal as a national "
            "pride test; Hindu SC consolidation is near its 2019 peak; Matua Mahasangha leaders "
            "are publicly realigning toward BJP in the final week; the CAA 'only Modi can deliver "
            "your citizenship' framing is landing hard. Weigh this against the lived SIR rage."
        ),
        "swing_notes": "SIR 77.86% deletion; Matua CAA-SIR paradox; manifesto cross-pressure; Modi-wave stress-test (max Hindu SC consolidation)",
        "key_seats": ["Gaighata", "Krishnaganj", "Karimpur", "Nakashipara", "Bangaon", "Ashokenagar"],
    },
    {
        "id": "jungle_mahal",
        "name": "Jungle Mahal Tribal Belt",
        "domain": "bengal_jungle_mahal",
        "n_seats": 50,
        "tmc_2021": 0.78,
        "bjp_2021": 0.18,
        "left_2021": 0.04,
        "others_2021": 0.00,
        "n_personas": 60,
        "marginal_seats_2021": 20,
        "context_note": (
            "You are voting in the Jungle Mahal — the tribal belt of West Midnapore, "
            "Bankura, Purulia, and Jhargram. Scheduled Tribe (ST) communities — Santali, "
            "Oraon, Munda, Khond — form the majority in most seats. "
            "TMC recovered this belt strongly in 2021 after BJP made gains in 2019. "
            "TMC's MGNREGA implementation and direct welfare (Lakshmir Bhandar, "
            "Krishak Bandhu) are the core loyalty anchors. "
            "BJP is running on Hindu consolidation and Modi government's tribal welfare "
            "claims, but the 'anti-tribal' rhetoric controversy has created backlash. "
            "Several seats had margins under 1,500 votes in 2021 — "
            "Ghatal (966), Bankura (1,468), Balarampur (423)."
        ),
        "swing_notes": "Ultra-marginal seats; welfare vs BJP tribal programs; TMC MGNREGA base",
        "key_seats": ["Ghatal", "Bankura", "Balarampur", "Dantan", "Kulti"],
    },
    {
        "id": "north_bengal",
        "name": "North Bengal Koch-Rajbongshi",
        "domain": "bengal_north_bengal",
        "n_seats": 30,
        "tmc_2021": 0.32,
        "bjp_2021": 0.60,
        "left_2021": 0.08,
        "others_2021": 0.00,
        "n_personas": 30,
        "marginal_seats_2021": 10,
        "context_note": (
            "You are voting in North Bengal — Cooch Behar, Alipurduar, and Jalpaiguri. "
            "BJP has dominated this region since 2019 through Koch-Rajbongshi OBC mobilisation "
            "and two powerful Union Ministers: Nisith Pramanik (Cooch Behar) and John Barla "
            "(Alipurduar). BJP won over 60% of seats here in 2021. "
            "Dinhata was decided by just 57 votes in 2021. Jalpaiguri by 941 votes. "
            "Tea garden workers (ST community) form a significant bloc in Jalpaiguri/Alipurduar "
            "— they have some TMC loyalty from MGNREGA. "
            "TMC is trying to break BJP's North Bengal fortress in 2026. "
            "The Gorkha hills (Darjeeling 3 seats) are a separate ethnic contest."
        ),
        "swing_notes": "BJP stronghold; Koch-Rajbongshi OBC base; Dinhata (57-vote margin); tea garden swing",
        "key_seats": ["Dinhata", "Jalpaiguri", "Mathabhanga", "Tufanganj", "Alipurduar"],
    },
    {
        "id": "kolkata_urban",
        "name": "Urban Kolkata",
        "domain": "bengal_kolkata_urban",
        "n_seats": 11,
        "tmc_2021": 0.90,
        "bjp_2021": 0.08,
        "left_2021": 0.02,
        "others_2021": 0.00,
        "n_personas": 30,
        "marginal_seats_2021": 2,
        "context_note": (
            "You are voting in urban Kolkata — the 11 assembly seats within the Kolkata "
            "Municipal Corporation boundary. TMC is dominant here; Ballygunge saw TMC win "
            "by 75,000 votes in 2021. The electorate is educated, professional, urban. "
            "Bhabanipur is the prestige contest: Mamata Banerjee vs Suvendu Adhikari "
            "is the symbolic face-off of the entire election. "
            "Urban voters care about livability, corruption, anti-incumbency, and welfare. "
            "BJP has negligible organisation in core Kolkata — this is TMC's safest zone. "
            "The Left-Congress alliance has some residual support among intellectuals "
            "and the Metiabruz Muslim enclave."
        ),
        "swing_notes": "TMC fortress; Bhabanipur Mamata vs Suvendu prestige contest; minimal swing",
        "key_seats": ["Bhabanipur", "Ballygunge", "Beleghata", "Entally", "Rashbehari"],
    },
    {
        "id": "south_rural",
        "name": "South Bengal Rural TMC Stronghold",
        "domain": "bengal_south_rural",
        "n_seats": 55,
        "tmc_2021": 0.77,
        "bjp_2021": 0.20,
        "left_2021": 0.03,
        "others_2021": 0.00,
        "n_personas": 40,
        "marginal_seats_2021": 10,
        "context_note": (
            "You are voting in South Bengal's rural zones — South 24-Parganas, coastal "
            "Midnapore, and Hooghly. This is Mamata Banerjee's original stronghold. "
            "Welfare schemes saturate this region: Lakshmir Bhandar reaches virtually "
            "every household; Swasthya Sathi health insurance; Krishak Bandhu for farmers. "
            "Sundarbans communities (fishermen, forest-product collectors) are TMC loyalists. "
            "Tamluk was won by TMC by just 793 votes in 2021 — a rare marginal in this belt. "
            "BJP has a presence in Hindu OBC trading communities and anti-TMC syndicate voices. "
            "Sandeshkhali (sexual violence, land-grab scandal) created national controversy "
            "but is a single constituency — broader rural TMC base remains intact."
        ),
        "swing_notes": "Welfare scheme saturated; Tamluk ultra-marginal; Sandeshkhali limited spillover",
        "key_seats": ["Tamluk", "Kakdwip", "Diamond Harbour", "Contai", "Baruipur"],
    },
    {
        "id": "burdwan_industrial",
        "name": "Burdwan Industrial Zone",
        "domain": "bengal_burdwan_industrial",
        "n_seats": 25,
        "tmc_2021": 0.72,
        "bjp_2021": 0.25,
        "left_2021": 0.03,
        "others_2021": 0.00,
        "n_personas": 60,
        "marginal_seats_2021": 10,
        "context_note": (
            "You are voting in the Burdwan industrial zone — Asansol-Durgapur-Bardhaman. "
            "This is Bengal's industrial heartland: coal mines (Kulti, Raniganj), "
            "steel plants (Durgapur), and the Bardhaman agricultural-industrial mix. "
            "The Left held this region for 34 years; CPM trade union residual (CITU) "
            "still has some presence among older workers. "
            "TMC won most seats in 2021, BJP holds Asansol-Durgapur parliamentary seats "
            "(Babul Supriyo defected to TMC, creating political flux). "
            "Kulti was decided by 679 votes. Industrial decline, job losses, and "
            "welfare vs corruption are the key voter concerns. "
            "Left-Congress alliance has its strongest residual in this industrial belt. "
            "\n"
            "2026 MANIFESTOS NOW LIVE: TMC (March 20) promises Rs 1,500/month unemployed youth "
            "stipend plus Rs 30,000 crore agriculture budget plus Lakshmir Bhandar hike to "
            "Rs 1,500/1,700 — delivered before polling. BJP Sankalp Patra (April 10) promises "
            "1 crore jobs/self-employment over 5 years, Rs 3,000/month unemployed youth, "
            "7th Pay Commission implementation for govt staff, Rs 3,000/month women DBT. "
            "Industrial worker / CITU retiree / govt employee now weighs: symmetric youth "
            "stipends (TMC Rs 1,500 delivered vs BJP Rs 3,000 promised), 7th Pay Commission "
            "appeal for govt-employee households, Left-Congress as the corruption-fatigue third option."
        ),
        "swing_notes": "Left CPM residual (Kulti 679 votes); Asansol BJP defector flux; industrial decline; 2026 manifesto symmetric youth+jobs promises (TMC delivered vs BJP conditional)",
        "key_seats": ["Kulti", "Asansol", "Durgapur", "Bardhaman", "Raniganj"],
    },
    {
        "id": "presidency_suburbs",
        "name": "Presidency Division Suburbs (Kingmaker Zone)",
        "domain": "bengal_presidency_suburbs",
        "n_seats": 40,
        "tmc_2021": 0.70,
        "bjp_2021": 0.12,
        "left_2021": 0.18,
        "others_2021": 0.00,
        "n_personas": 60,
        "marginal_seats_2021": 18,
        "context_note": (
            "You are voting in the Presidency Division suburbs — the belt of North 24 Parganas "
            "(Barasat, Baranagar, Dum Dum, Barrackpore, Habra, Bangaon) and Nadia-adjacent "
            "suburban areas. Election analysts call this Bengal's 'kingmaker zone' — whoever "
            "wins Presidency usually wins the state. "
            "The Left historically held many of these seats (18% vote share in 2021). "
            "SIR deleted 330,000 voters from North 24 Parganas — hitting both Muslim "
            "enclaves and Matua belt suburbs, hurting both TMC and BJP bases. "
            "AIMIM-AJUP is contesting seats in this belt. "
            "Urban-educated middle class here is more ideologically mixed than Kolkata core."
        ),
        "swing_notes": "KINGMAKER ZONE; Left 18% base; SIR 330k N24Pgs; Presidency determines state winner",
        "key_seats": ["Ashokenagar", "Bangaon", "Baranagar", "Dum Dum", "Barasat", "Habra"],
    },
    {
        "id": "darjeeling_hills",
        "name": "Darjeeling Hills + Adjacent Plains",
        "domain": "bengal_darjeeling_hills",
        "n_seats": 9,
        "tmc_2021": 0.20,
        "bjp_2021": 0.65,
        "left_2021": 0.10,
        "others_2021": 0.05,
        "n_personas": 20,
        "marginal_seats_2021": 5,
        "context_note": (
            "You are voting in Darjeeling district — 3 hill seats (Darjeeling, Kurseong, "
            "Kalimpong) and 6 adjacent plains seats (Siliguri, Phansidewa, Matigara-Naxalbari). "
            "The hills are dominated by Gorkha ethnic politics with a 5-cornered race: "
            "BJP-BGPM alliance vs Bimal Gurung's GJM faction vs Binoy Tamang's faction "
            "vs IGJF (Ajoy Edwards, Gorkhaland demand) vs Left-AISF. "
            "BJP swept all 3 hill seats in 2021. The plains seats (Siliguri etc.) are "
            "more mainstream with mixed Hindu-Muslim-tribal populations. "
            "Tea garden workers in Jalpaiguri-Alipurduar (covered in North Bengal cluster) "
            "have distinct concerns from the GTA hill politics here."
        ),
        "swing_notes": "5-cornered Gorkha ethnic race; BJP dominates hills; plains seats partially competitive",
        "key_seats": ["Darjeeling", "Kurseong", "Kalimpong", "Siliguri", "Phansidewa"],
    },
]

# Quick lookup by cluster id
CLUSTER_BY_ID: dict[str, dict] = {c["id"]: c for c in CLUSTERS}

# Sanity check: total seats should equal 294
_total_seats = sum(c["n_seats"] for c in CLUSTERS)
assert _total_seats == 294, f"Seat count mismatch: {_total_seats} != 294"

# Swing clusters run with ensemble averaging (3 independent runs)
SWING_CLUSTER_IDS: set[str] = {
    "matua_belt",
    "jungle_mahal",
    "burdwan_industrial",
    "presidency_suburbs",
    "murshidabad",
}
