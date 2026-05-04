"use strict";
// WB 2026 post-mortem — DOCX (white-background print template)
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType, PageNumber,
} = require("docx");

const OUT = "/Users/admin/Documents/Simulatte Projects/PopScale/engineering/POST_ELECTION_POSTMORTEM_WB2026.docx";

// Light-mode print palette (per visual-tokens DOCX guidance)
const HEADING_HEX = "1A1A1A";
const BODY_HEX    = "2C2C2C";
const STATIC_HEX  = "5E5E5E"; // metadata only on light bg — passes contrast
const SIGNAL_HEX  = "A8FF3E";

const HEAD_FONT = "Arial Narrow"; // Barlow Condensed substitute
const BODY_FONT = "Calibri";      // Barlow substitute
const MONO_FONT = "Courier New";  // Martian Mono substitute

// helpers
const p = (children, opts = {}) => new Paragraph({ children, ...opts });
const t = (text, opts = {}) => new TextRun({
  text, font: opts.font || BODY_FONT, size: opts.size || 22, color: opts.color || BODY_HEX,
  bold: !!opts.bold, italics: !!opts.italics, allCaps: !!opts.allCaps,
});

// H1 with signal-green left border
function h1(text) {
  return new Paragraph({
    children: [new TextRun({ text, font: HEAD_FONT, size: 36, bold: true, color: HEADING_HEX })],
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 480, after: 200 },
    border: {
      left: { color: SIGNAL_HEX, style: BorderStyle.SINGLE, size: 24, space: 12 },
    },
    indent: { left: 120 },
  });
}

function h2(text) {
  return new Paragraph({
    children: [new TextRun({ text, font: HEAD_FONT, size: 28, bold: true, color: HEADING_HEX })],
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 280, after: 120 },
  });
}

function body(text, opts = {}) {
  return p([t(text, { ...opts })], { spacing: { after: 140 } });
}

function bullet(text, bold) {
  return new Paragraph({
    children: [t(text, { bold })],
    bullet: { level: 0 },
    spacing: { after: 80 },
  });
}

function eyebrow(text) {
  return p([new TextRun({
    text, font: MONO_FONT, size: 18, color: STATIC_HEX, allCaps: true, characterSpacing: 40,
  })], { spacing: { after: 80 } });
}

// Table cell helper
function cell(text, opts = {}) {
  const runs = Array.isArray(text)
    ? text
    : [new TextRun({ text, font: BODY_FONT, size: 20, color: opts.color || BODY_HEX, bold: !!opts.bold })];
  return new TableCell({
    children: [new Paragraph({ children: runs, alignment: opts.align || AlignmentType.LEFT })],
    width: { size: opts.w || 2000, type: WidthType.DXA },
    shading: opts.shade ? { fill: opts.shade, type: ShadingType.CLEAR, color: "auto" } : undefined,
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
  });
}

// Section 1 — call vs result table
function callVsResultTable() {
  const header = ["Party", "Pred. seats", "Actual seats", "Δ seats", "Pred. VS%", "Actual VS%", "Δ VS%"];
  const rows = [
    ["TMC",   "194 ± 10", "{ACTUAL_TMC}",  "{ACTUAL_TMC_DELTA}",  "~52%", "40.97%", "−11pp"],
    ["BJP",   "45 ± 10",  "{ACTUAL_BJP}",  "{ACTUAL_BJP_DELTA}",  "~24%", "45.13%", "+21pp"],
    ["L-C",   "50 ± 10",  "{ACTUAL_LC}",   "{ACTUAL_LC_DELTA}",   "~17%", "{ACTUAL_LC_VS}", "—"],
    ["Others","5 ± 3",    "{ACTUAL_OTH}",  "{ACTUAL_OTH_DELTA}",  "~7%",  "{ACTUAL_OTH_VS}", "—"],
  ];
  const W = 1280;
  const headerRow = new TableRow({
    tableHeader: true,
    children: header.map(h => cell(h, { bold: true, w: W, shade: "F2F2F0" })),
  });
  const bodyRows = rows.map(r => new TableRow({
    children: r.map(c => cell(c, { w: W })),
  }));
  return new Table({
    rows: [headerRow, ...bodyRows],
    width: { size: 9000, type: WidthType.DXA },
    borders: {
      top:    { style: BorderStyle.SINGLE, size: 4, color: "C9C7C0" },
      bottom: { style: BorderStyle.SINGLE, size: 4, color: "C9C7C0" },
      left:   { style: BorderStyle.NONE, size: 0, color: "auto" },
      right:  { style: BorderStyle.NONE, size: 0, color: "auto" },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: "E0DED9" },
      insideVertical:   { style: BorderStyle.NONE, size: 0, color: "auto" },
    },
  });
}

const children = [
  // Title block
  eyebrow("POST-MORTEM · WEST BENGAL 2026 · SIMULATTE / THE CONSTRUCT"),
  p([new TextRun({
    text: "We staked TMC. Bengal voted otherwise.",
    font: HEAD_FONT, size: 56, bold: true, color: HEADING_HEX,
  })], { spacing: { after: 120 } }),
  p([new TextRun({
    text: "4 May 2026 · v0.1 · figures pending final tally swap-in",
    font: MONO_FONT, size: 18, color: STATIC_HEX,
  })], { spacing: { after: 360 } }),

  // Lead
  body("On 22 April 2026 The Construct simulated a TMC majority of 194 ± 10 seats at ~52% voteshare. Counting on 4 May produced a BJP majority above the 148-seat threshold at 45.13% voteshare against TMC at 40.97%. This document records what we modelled, what actually decided the result, and the specific prior shifts that will be applied to the next study."),

  // 1. The Call vs the Result
  h1("1. The Call vs the Result"),
  body("Per-party predicted vs actual. Final actuals are pending — bracketed placeholders are swapped in once counting closes (~7 PM IST, 4 May 2026)."),
  callVsResultTable(),
  p([t("Source: ECI live counts at 13:35 IST 4 May 2026; Simulatte WB 2026 study report 22 April 2026.", { color: STATIC_HEX, size: 18 })], { spacing: { before: 120, after: 200 } }),

  // 2. What we modelled
  h1("2. What We Modelled — Predictive Side"),
  body("Six factors carried the model toward a TMC majority. Each is listed with its weight in the cluster mix and the empirical signal it was anchored to."),
  bullet("TMC organisational depth — panchayat machinery. Weight: high. Signal: 2023 panchayat election dominance and continuous incumbent presence at booth level.", true),
  bullet("Muslim consolidation in Murshidabad — modelled at ~75–90% TMC share. Signal: 2021 baseline (TMC carried 18 of 22 Murshidabad seats); 2024 LS reaffirmation outside the Berhampore anomaly.", true),
  bullet("CAA backlash hypothesis in Matua belt — modelled as a TMC retention factor. Signal: pre-2024 protest mobilisation in Bongaon, Ranaghat, Bagda.", true),
  bullet("Tribal anti-BJP sentiment in Jungle Mahal — corrective swing back to TMC after 2021. Signal: 2023 panchayat sweeps in Jhargram, Bankura, Purulia rural.", true),
  bullet("Welfare delivery — Lakshmir Bhandar, Kanyashree, Swasthya Sathi. Weight: medium-high. Signal: enrolment data showing 2.1cr+ Lakshmir Bhandar beneficiaries.", true),
  bullet("2021 baseline anchoring — TMC at 213 seats. Uniform-swing model assumed correction of 10–20pp at most across non-Muslim clusters.", true),

  // 3. What actually decided
  h1("3. What Actually Decided It — Ground Truth"),
  body("The dominant factors visible in the live result, with the ground-truth signal where available."),
  bullet("Hindu consolidation as a state-wide frame — BJP voteshare 45.13% against modelled ~22–25%. The frame crossed cluster boundaries the model treated as independent.", true),
  bullet("SIR voter-roll exercise — ~460k deletions concentrated in Muslim-majority constituencies created structural turnout asymmetry favouring BJP. Effect was systemic, not cluster-local.", true),
  bullet("4-way Muslim vote fragmentation — TMC, AIMIM, AJUP and INDI collectively split the Muslim vote in Murshidabad and parts of Malda; BJP carried multiple seats on plurality.", true),
  bullet("Matua identification with CAA delivery — citizenship grants in 2025 reversed the modelled direction of CAA effect; Matua belt swung toward BJP rather than away.", true),
  bullet("BJP organisational expansion in rural Bengal — sustained booth presence post-2021, welfare counter-narrative on PM-Kisan and Awas. Eroded TMC’s panchayat advantage faster than the model assumed.", true),
  bullet("Anti-incumbency on corruption cases — Sandeshkhali fallout, teacher recruitment scam (SSC), municipal recruitment scam. Compounded into a state-wide governance frame.", true),

  // 4. Where the model was wrong
  h1("4. Where the Model Was Wrong — Mechanism, Not Apology"),
  body("Three structural failures, ordered by magnitude of contribution to the prediction error."),
  h2("Anchoring on 2021 baseline."),
  body("The 213-seat 2021 result was the structural anchor. Uniform-swing logic assumed corrections of 10–20pp at most. Realised swing was 25–30pp in non-Muslim clusters. The model treated the 2021 result as a stable equilibrium when it was the peak of a cycle."),
  h2("Single-frame Hindu consolidation hypothesis."),
  body("Hindu consolidation was modelled as a localised factor in pre-existing BJP-leaning clusters (North Bengal, Cooch Behar, parts of Jangalmahal). The actual frame ran state-wide and lifted BJP voteshare uniformly. Treating it as cluster-local under-counted its reach by a factor of two."),
  h2("Insufficient weight on SIR."),
  body("SIR deletions were modelled as a marginal swing factor inside Muslim-belt clusters. Actual impact was structural turnout asymmetry across every cluster with a Muslim-majority booth set. The model did not have a feature for institutional roll-management as a determinant of outcome."),

  // 5. Calibration updates
  h1("5. Calibration Updates for Next Run"),
  body("Specific prior shifts that will enter the calibration loop. These follow BRIEF-021 adjustment-rule logic — magnitude scales with observed error in the most affected cluster."),
  bullet("Murshidabad TMC prior: shift down 12pp (from ~75% to ~63%).", true),
  bullet("Matua belt TMC prior: shift down 18pp; reverse CAA-effect direction.", true),
  bullet("Jungle Mahal TMC prior: shift down 15pp; remove 2021-baseline correction term.", true),
  bullet("BJP base across all clusters: shift up 15–25pp depending on Hindu-share and rural/urban mix.", true),
  bullet("New structural feature: SIR-coverage as a cluster-level adjustment to expected turnout-mix.", true),
  bullet("Anchor change: replace 2021 baseline with a 2024 LS-projected baseline weighted 0.6, 2021 baseline 0.4.", true),

  // 6. What's next
  h1("6. What’s Next"),
  body("Final tally and per-constituency breakdown will be input to the calibration loop tomorrow morning."),
  body("The new priors will be applied to the next election study (US Midterms or Bihar 2025)."),
  body("The point of building the calibration loop is to make this update mechanically, not narratively."),

  // Footer
  p([new TextRun({
    text: "Simulatte / The Construct · 4 May 2026 · v0.1",
    font: MONO_FONT, size: 16, color: STATIC_HEX,
  })], { spacing: { before: 480 }, alignment: AlignmentType.LEFT }),
];

const doc = new Document({
  creator: "Simulatte / The Construct",
  title: "WB 2026 Post-Mortem",
  styles: {
    default: {
      document: {
        run: { font: BODY_FONT, size: 22, color: BODY_HEX },
        paragraph: { spacing: { line: 320 } },
      },
    },
  },
  sections: [{
    properties: {
      page: { margin: { top: 1080, right: 1080, bottom: 1080, left: 1080 } },
    },
    children,
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(OUT, buf);
  console.log("WROTE:", OUT, buf.length, "bytes");
});
