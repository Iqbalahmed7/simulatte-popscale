"use strict";
// WB 2026 post-mortem — single LinkedIn carousel slide (10" × 10")
// Strict Simulatte brand. Zero green except engine mark.
// v0.2: binary winner-fill (parchment = TMC, hollow = anyone else),
//       5×2 grid (10 clusters, no empty cells), sharp predicted/actual asymmetry.
const pptxgen = require("pptxgenjs");

const OUT = "/Users/admin/Documents/Simulatte Projects/PopScale/engineering/wb_2026_postmortem_slide.pptx";

const VOID      = "050505";
const PARCHMENT = "E9E6DF";
const SIGNAL    = "A8FF3E";
const STATIC    = "9A9997";
const BODY_COPY = "C9C7C0";
const DETAIL    = "A8A6A0";
const BORDER    = "1A1A1A";
const NEAR_BLACK = "1A1A1A";

const ACTUAL_BJP = "{ACTUAL_BJP}"; // placeholder for swap-in (single sed replace)

// Engine mark — bottom-right, on a 10x10 canvas
function addMark(pptx, slide, x, y, size = 0.42) {
  const s = size;
  slide.addShape(pptx.ShapeType.ellipse, { x, y, w: s, h: s, fill: { color: VOID }, line: { color: SIGNAL, width: 1.5 } });
  const m = s * 0.64, mo = (s - m) / 2;
  slide.addShape(pptx.ShapeType.ellipse, { x: x + mo, y: y + mo, w: m, h: m, fill: { color: VOID }, line: { color: SIGNAL, width: 1.0 } });
  const c = s * 0.28, co = (s - c) / 2;
  slide.addShape(pptx.ShapeType.ellipse, { x: x + co, y: y + co, w: c, h: c, fill: { color: SIGNAL }, line: { type: "none" } });
}

const pptx = new pptxgen();
// Square 10" x 10" carousel
pptx.defineLayout({ name: "SQUARE10", width: 10, height: 10 });
pptx.layout = "SQUARE10";
pptx.title = "WB 2026 Post-Mortem";

const slide = pptx.addSlide();
slide.background = { color: VOID };

// ── TOP: eyebrow + divider + headline
slide.addText("POST-MORTEM · WEST BENGAL 2026", {
  x: 0.5, y: 0.40, w: 9, h: 0.25,
  fontFace: "Courier New", fontSize: 9, color: STATIC,
  charSpacing: 2, margin: 0,
});

// Divider
slide.addShape(pptx.ShapeType.line, {
  x: 0.5, y: 0.72, w: 9, h: 0,
  line: { color: BORDER, width: 0.75 },
});

// Headline split across 2 lines, ALL parchment
slide.addText("We staked TMC.", {
  x: 0.5, y: 0.85, w: 9, h: 0.7,
  fontFace: "Arial Narrow", fontSize: 36, bold: true, color: PARCHMENT, margin: 0,
});
slide.addText("Bengal voted otherwise.", {
  x: 0.5, y: 1.50, w: 9, h: 0.7,
  fontFace: "Arial Narrow", fontSize: 36, bold: true, color: PARCHMENT, margin: 0,
});

// ── MIDDLE: two maps (cluster grids) side by side
const LX = 0.5, RX = 5.1, MW = 4.4, MTOP = 2.4;

// Headers
slide.addText("PREDICTED", {
  x: LX, y: MTOP, w: MW, h: 0.25,
  fontFace: "Courier New", fontSize: 9, color: STATIC, charSpacing: 2, margin: 0,
});
slide.addText("ACTUAL", {
  x: RX, y: MTOP, w: MW, h: 0.25,
  fontFace: "Courier New", fontSize: 9, color: STATIC, charSpacing: 2, margin: 0,
});

// 10 clusters arranged 5 cols × 2 rows.
// Geographic ordering: row 0 = north Bengal, row 1 = south Bengal.
// predTMC: did our model predict TMC wins this cluster?
// actualTMC: did TMC actually win this cluster (current trend; placeholder — flip when final tally arrives)?
//
// Predicted (model output): TMC predicted in 9 of 10 clusters; we modelled BJP/GJM in Darjeeling.
// Actual (current trend, working assumption — UPDATE WHEN FINAL TALLY ARRIVES):
//   BJP appears to have won 9 of 10 clusters. Murshidabad is the lone TMC hold.
const clusters = [
  // Row 0 — North Bengal across the top
  { name: "Darjeeling",         col: 0, row: 0, predTMC: false, actualTMC: false },
  { name: "North Bengal",       col: 1, row: 0, predTMC: true,  actualTMC: false },
  { name: "Malda",              col: 2, row: 0, predTMC: true,  actualTMC: false },
  { name: "Murshidabad",        col: 3, row: 0, predTMC: true,  actualTMC: true  },
  { name: "Matua / Nadia-N24",  col: 4, row: 0, predTMC: true,  actualTMC: false },
  // Row 1 — South Bengal across the bottom
  { name: "Burdwan Industrial", col: 0, row: 1, predTMC: true,  actualTMC: false },
  { name: "Jungle Mahal",       col: 1, row: 1, predTMC: true,  actualTMC: false },
  { name: "South Rural",        col: 2, row: 1, predTMC: true,  actualTMC: false },
  { name: "Presidency Suburbs", col: 3, row: 1, predTMC: true,  actualTMC: false },
  { name: "Kolkata Urban",      col: 4, row: 1, predTMC: true,  actualTMC: false },
];

const COLS = 5, ROWS = 2;
const mapInnerTop = MTOP + 0.30;
const mapInnerH = 3.0;
const cellW = MW / COLS;
const cellH = mapInnerH / ROWS;
const gap = 0.05;

// Border for each map area
slide.addShape(pptx.ShapeType.rect, {
  x: LX, y: mapInnerTop - 0.04, w: MW, h: mapInnerH + 0.08,
  fill: { type: "none" }, line: { color: BORDER, width: 0.75 },
});
slide.addShape(pptx.ShapeType.rect, {
  x: RX, y: mapInnerTop - 0.04, w: MW, h: mapInnerH + 0.08,
  fill: { type: "none" }, line: { color: BORDER, width: 0.75 },
});

// Render each cell on both sides.
// Color rule: parchment fill iff TMC wins (predicted side: predTMC; actual side: actualTMC).
// Hollow = anyone else (BJP, L-C, GJM/BJP-allied, etc).
function drawCell(x, y, w, h, isTMC, label) {
  if (isTMC) {
    // Parchment-filled: TMC win
    slide.addShape(pptx.ShapeType.rect, {
      x, y, w, h,
      fill: { color: PARCHMENT },
      line: { color: PARCHMENT, width: 0.5 },
    });
    slide.addText(label, {
      x: x + 0.05, y: y + 0.05, w: w - 0.10, h: h - 0.10,
      fontFace: "Courier New", fontSize: 9, bold: true, color: NEAR_BLACK,
      valign: "top", margin: 0,
    });
  } else {
    // Hollow: dark grey with thin parchment outline
    slide.addShape(pptx.ShapeType.rect, {
      x, y, w, h,
      fill: { color: VOID },
      line: { color: PARCHMENT, width: 0.5 },
    });
    slide.addText(label, {
      x: x + 0.05, y: y + 0.05, w: w - 0.10, h: h - 0.10,
      fontFace: "Courier New", fontSize: 9, color: STATIC,
      valign: "top", margin: 0,
    });
  }
}

clusters.forEach((c) => {
  const cx_l = LX + c.col * cellW + gap / 2;
  const cy   = mapInnerTop + c.row * cellH + gap / 2;
  const cx_r = RX + c.col * cellW + gap / 2;
  const w = cellW - gap;
  const h = cellH - gap;

  // PREDICTED side
  drawCell(cx_l, cy, w, h, c.predTMC, c.name);
  // ACTUAL side
  drawCell(cx_r, cy, w, h, c.actualTMC, c.name);
});

// Captions below each map
const capY = mapInnerTop + mapInnerH + 0.20;
slide.addText("Predicted: TMC majority · 194 ± 10 seats · ~52% vs ~22% voteshare modelled", {
  x: LX, y: capY, w: MW, h: 0.5,
  fontFace: "Calibri", fontSize: 11, color: DETAIL, margin: 0,
});
slide.addText(`Actual: BJP majority · ${ACTUAL_BJP} seats · 45.1% voteshare`, {
  x: RX, y: capY, w: MW, h: 0.5,
  fontFace: "Calibri", fontSize: 11, color: DETAIL, margin: 0,
});

// ── BOTTOM: factor ledger
const LY = 7.0;
slide.addText("WHAT WE WEIGHTED", {
  x: 0.5, y: LY, w: 4.6, h: 0.22,
  fontFace: "Courier New", fontSize: 9, color: STATIC, charSpacing: 2, margin: 0,
});
slide.addText("WHAT ACTUALLY DECIDED", {
  x: 5.1, y: LY, w: 4.4, h: 0.22,
  fontFace: "Courier New", fontSize: 9, color: STATIC, charSpacing: 2, margin: 0,
});
slide.addShape(pptx.ShapeType.line, {
  x: 0.5, y: LY + 0.28, w: 9, h: 0, line: { color: BORDER, width: 0.5 },
});

const rows = [
  ["TMC organisational depth in panchayats", "SIR voter-roll deletions hit TMC base disproportionately"],
  ["Muslim consolidation around TMC in Murshidabad", "4-way Muslim split (TMC/AIMIM/AJUP/INDI) yielded BJP pluralities"],
  ["Manifesto economic populism", "Hindu consolidation as the dominant frame across non-Muslim clusters"],
  ["Matua belt loyalty after CAA implementation", "Reverse swing — Matua identification with BJP’s CAA delivery"],
  ["Jungle Mahal tribal anti-BJP sentiment 2021", "Sustained BJP organisational presence + welfare delivery"],
];

const rowTop = LY + 0.40;
const rowH = 0.40;
rows.forEach((r, i) => {
  const y = rowTop + i * rowH;
  slide.addText(r[0], {
    x: 0.5, y, w: 4.4, h: rowH - 0.04,
    fontFace: "Calibri", fontSize: 11, bold: true, color: PARCHMENT, valign: "top", margin: 0,
  });
  slide.addText(r[1], {
    x: 5.1, y, w: 4.4, h: rowH - 0.04,
    fontFace: "Calibri", fontSize: 11, color: BODY_COPY, valign: "top", margin: 0,
  });
});

// ── FOOTER
slide.addText("Simulatte / The Construct · 4 May 2026", {
  x: 0.5, y: 9.65, w: 6, h: 0.22,
  fontFace: "Courier New", fontSize: 9, color: STATIC, margin: 0,
});

// Engine mark bottom-right
addMark(pptx, slide, 9.10, 9.50, 0.42);

pptx.writeFile({ fileName: OUT }).then(() => {
  console.log("WROTE:", OUT);
});
