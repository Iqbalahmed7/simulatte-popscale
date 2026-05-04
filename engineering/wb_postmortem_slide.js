"use strict";
// WB 2026 post-mortem — single LinkedIn carousel slide (10" × 10")
// Strict Simulatte brand. Zero green except engine mark.
const pptxgen = require("pptxgenjs");

const OUT = "/Users/admin/Documents/Simulatte Projects/PopScale/engineering/wb_2026_postmortem_slide.pptx";

const VOID      = "050505";
const PARCHMENT = "E9E6DF";
const SIGNAL    = "A8FF3E";
const STATIC    = "9A9997";
const BODY_COPY = "C9C7C0";
const DETAIL    = "A8A6A0";
const BORDER    = "1A1A1A";

const ACTUAL_BJP = "{ACTUAL_BJP}"; // placeholder for swap-in

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

// ── TOP: eyebrow + divider + headline (y 0.4–1.4 then headline below)
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

// Headline split across 2 lines, ALL parchment (data slide rule — no split lettering)
slide.addText("We staked TMC.", {
  x: 0.5, y: 0.85, w: 9, h: 0.7,
  fontFace: "Arial Narrow", fontSize: 36, bold: true, color: PARCHMENT, margin: 0,
});
slide.addText("Bengal voted otherwise.", {
  x: 0.5, y: 1.50, w: 9, h: 0.7,
  fontFace: "Arial Narrow", fontSize: 36, bold: true, color: PARCHMENT, margin: 0,
});

// ── MIDDLE: two maps (cluster grids) side by side
// LEFT — PREDICTED
const LX = 0.5, RX = 5.1, MW = 4.4, MTOP = 2.4, MH = 4.5;

// Headers
slide.addText("PREDICTED", {
  x: LX, y: MTOP, w: MW, h: 0.25,
  fontFace: "Courier New", fontSize: 9, color: STATIC, charSpacing: 2, margin: 0,
});
slide.addText("ACTUAL", {
  x: RX, y: MTOP, w: MW, h: 0.25,
  fontFace: "Courier New", fontSize: 9, color: STATIC, charSpacing: 2, margin: 0,
});

// 10 cluster grid — rough geographic positions (within each map area)
// Position grid (col, row, w, h) inside a 4-col x 4-row layout
// Cluster names + rough positions: (col 0..3, row 0..3)
const clusters = [
  { name: "Darjeeling",         col: 0, row: 0, predTMC: 25, actualBJP: 55 },
  { name: "North Bengal",        col: 1, row: 0, predTMC: 50, actualBJP: 58 },
  { name: "Cooch Behar",         col: 2, row: 0, predTMC: 50, actualBJP: 60 },
  { name: "Murshidabad",         col: 0, row: 1, predTMC: 75, actualBJP: 38 },
  { name: "Matua / Nadia-N24",   col: 1, row: 1, predTMC: 60, actualBJP: 55 },
  { name: "Burdwan Industrial",  col: 2, row: 1, predTMC: 58, actualBJP: 50 },
  { name: "Howrah-Hooghly",      col: 3, row: 1, predTMC: 60, actualBJP: 48 },
  { name: "Jungle Mahal",        col: 0, row: 2, predTMC: 55, actualBJP: 56 },
  { name: "Bankura-Purulia",     col: 1, row: 2, predTMC: 52, actualBJP: 55 },
  { name: "Presidency Suburbs",  col: 2, row: 2, predTMC: 62, actualBJP: 45 },
  { name: "Kolkata Urban",       col: 3, row: 2, predTMC: 58, actualBJP: 42 },
];

const COLS = 4, ROWS = 3;
const mapInnerTop = MTOP + 0.30;
const mapInnerH = 3.6;
const cellW = MW / COLS;
const cellH = mapInnerH / ROWS;
const gap = 0.06;

// border for each map area
slide.addShape(pptx.ShapeType.rect, {
  x: LX, y: mapInnerTop - 0.04, w: MW, h: mapInnerH + 0.08,
  fill: { type: "none" }, line: { color: BORDER, width: 0.75 },
});
slide.addShape(pptx.ShapeType.rect, {
  x: RX, y: mapInnerTop - 0.04, w: MW, h: mapInnerH + 0.08,
  fill: { type: "none" }, line: { color: BORDER, width: 0.75 },
});

// Helper: parchment intensity by share — render fill as parchment with transparency
function intensity(share) {
  // share 0..100 → transparency 90..15 (lower = more visible)
  const clamped = Math.max(0, Math.min(100, share));
  return Math.round(90 - (clamped / 100) * 75);
}

clusters.forEach((c) => {
  const cx_l = LX + c.col * cellW + gap / 2;
  const cy   = mapInnerTop + c.row * cellH + gap / 2;
  const cx_r = RX + c.col * cellW + gap / 2;
  const w = cellW - gap;
  const h = cellH - gap;

  // PREDICTED side — TMC share
  slide.addShape(pptx.ShapeType.rect, {
    x: cx_l, y: cy, w, h,
    fill: { color: PARCHMENT, transparency: intensity(c.predTMC) },
    line: { color: BORDER, width: 0.5 },
  });
  slide.addText(c.name, {
    x: cx_l + 0.03, y: cy + 0.03, w: w - 0.06, h: h - 0.06,
    fontFace: "Courier New", fontSize: 7, color: STATIC, valign: "top", margin: 0,
  });

  // ACTUAL side — BJP share
  slide.addShape(pptx.ShapeType.rect, {
    x: cx_r, y: cy, w, h,
    fill: { color: PARCHMENT, transparency: intensity(c.actualBJP) },
    line: { color: BORDER, width: 0.5 },
  });
  slide.addText(c.name, {
    x: cx_r + 0.03, y: cy + 0.03, w: w - 0.06, h: h - 0.06,
    fontFace: "Courier New", fontSize: 7, color: STATIC, valign: "top", margin: 0,
  });
});

// Captions below each map
const capY = mapInnerTop + mapInnerH + 0.15;
slide.addText("TMC majority. 194 ± 10 seats. ~52% voteshare.", {
  x: LX, y: capY, w: MW, h: 0.4,
  fontFace: "Calibri", fontSize: 11, color: DETAIL, margin: 0,
});
slide.addText(`BJP majority. ${ACTUAL_BJP} seats. 45.1% voteshare.`, {
  x: RX, y: capY, w: MW, h: 0.4,
  fontFace: "Calibri", fontSize: 11, color: DETAIL, margin: 0,
});

// ── BOTTOM: factor ledger (y 7.0 to 9.5)
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
