"use strict";
// WB 2026 Post-Mortem Deck — v2: 15 slides
// - Real Bengal-shaped map (stylized polygonal outline) replaces abstract grid
// - 10 cluster-by-cluster analysis slides
// Brand: Simulatte. LAYOUT_16x9.
const pptxgen = require("pptxgenjs");

const OUT = "/Users/admin/Documents/Simulatte Projects/PopScale/engineering/wb_2026_postmortem_deck.pptx";
const MAPS_DIR = "/Users/admin/Documents/Simulatte Projects/PopScale/engineering/maps";

// Palette
const VOID       = "050505";
const PARCHMENT  = "E9E6DF";
const SIGNAL     = "A8FF3E";
const STATIC     = "9A9997";
const BODY_COPY  = "C9C7C0";
const DETAIL     = "A8A6A0";
const BORDER     = "1A1A1A";
const NEAR_BLACK = "1A1A1A";
const DIM_OUTLINE = "3A3A38";

// ────────────────────────────────────────────────────────────────
// Brand frame helpers
// ────────────────────────────────────────────────────────────────
function addMark(pptx, slide) {
  slide.addShape(pptx.ShapeType.ellipse, { x: 9.32, y: 0.14, w: 0.36, h: 0.36, fill: { color: VOID }, line: { color: SIGNAL, width: 1.5 } });
  slide.addShape(pptx.ShapeType.ellipse, { x: 9.40, y: 0.22, w: 0.20, h: 0.20, fill: { color: VOID }, line: { color: SIGNAL, width: 1.0 } });
  slide.addShape(pptx.ShapeType.ellipse, { x: 9.46, y: 0.28, w: 0.08, h: 0.08, fill: { color: SIGNAL }, line: { color: SIGNAL, width: 1 } });
}
function addMarkBL(pptx, slide) {
  slide.addShape(pptx.ShapeType.ellipse, { x: 0.40, y: 4.92, w: 0.42, h: 0.42, fill: { color: VOID }, line: { color: SIGNAL, width: 1.5 } });
  slide.addShape(pptx.ShapeType.ellipse, { x: 0.49, y: 5.01, w: 0.24, h: 0.24, fill: { color: VOID }, line: { color: SIGNAL, width: 1.0 } });
  slide.addShape(pptx.ShapeType.ellipse, { x: 0.56, y: 5.08, w: 0.10, h: 0.10, fill: { color: SIGNAL }, line: { color: SIGNAL, width: 0 } });
  slide.addText("Simulatte", { x: 0.90, y: 4.92, w: 2.5, h: 0.42, fontFace: "Arial Narrow", fontSize: 16, bold: true, color: PARCHMENT, margin: 0, valign: "middle" });
}
function addFooter(slide, slideNum) {
  slide.addText("Simulatte / Confidential", { x: 0.5, y: 5.32, w: 4, h: 0.2, fontFace: "Courier New", fontSize: 9, color: STATIC, align: "left", margin: 0 });
  slide.addText(String(slideNum), { x: 8.8, y: 5.32, w: 0.8, h: 0.2, fontFace: "Courier New", fontSize: 9, color: STATIC, align: "right", margin: 0 });
}
function addEyebrow(slide, txt) {
  slide.addText(txt, { x: 0.5, y: 0.22, w: 8.5, h: 0.22, fontFace: "Courier New", fontSize: 9, color: STATIC, charSpacing: 2, margin: 0 });
}
function bg(slide) { slide.background = { color: VOID }; }

// ────────────────────────────────────────────────────────────────
// CLUSTER GEOGRAPHIC LAYOUT
// Stylized polygon footprints in a *normalized 0..1 × 0..1* coordinate space
// approximating West Bengal's silhouette (narrow north → wide south).
// Each cluster is a list of {x,y,w,h} sub-cells whose union forms the
// cluster region. Drawn at any (ox, oy, scale) into the slide.
// ────────────────────────────────────────────────────────────────
//
// Layout sketch (north up, west left). Coords are normalized.
// Whole map fits in a unit square. WB silhouette is implied by
// the union of all cluster cells.
//
//   y=0.00  ┌─DARJEELING─┐
//   y=0.10  │N.BENGAL  │
//   y=0.20  │N.BENGAL  │
//   y=0.30  ┌MALDA┐
//   y=0.38  ├MURSHIDABAD─┐
//   y=0.50  │BURDWAN  ┤MATUA┐
//   y=0.62  │J.MAHAL ┤PRESIDENCY┤
//   y=0.74  │J.MAHAL ┤KOLKATA│
//   y=0.86  │SOUTH RURAL ───┘
//
// Coordinates chosen by hand to (a) sum to a recognizable Bengal
// silhouette and (b) keep cluster relative positions roughly correct.

const CLUSTER_GEOM = {
  darjeeling_hills: [
    { x: 0.18, y: 0.00, w: 0.18, h: 0.10 },
  ],
  north_bengal: [
    { x: 0.16, y: 0.10, w: 0.22, h: 0.12 },
    { x: 0.22, y: 0.22, w: 0.18, h: 0.08 },
  ],
  malda: [
    { x: 0.22, y: 0.30, w: 0.18, h: 0.08 },
  ],
  murshidabad: [
    { x: 0.30, y: 0.38, w: 0.22, h: 0.12 },
  ],
  burdwan_industrial: [
    { x: 0.10, y: 0.42, w: 0.20, h: 0.16 },
    { x: 0.12, y: 0.58, w: 0.18, h: 0.06 },
  ],
  matua_belt: [
    { x: 0.52, y: 0.42, w: 0.20, h: 0.18 },
  ],
  jungle_mahal: [
    { x: 0.04, y: 0.58, w: 0.30, h: 0.18 },
    { x: 0.10, y: 0.76, w: 0.18, h: 0.06 },
  ],
  presidency_suburbs: [
    { x: 0.34, y: 0.50, w: 0.18, h: 0.14 },
    { x: 0.40, y: 0.64, w: 0.14, h: 0.06 },
  ],
  kolkata_urban: [
    { x: 0.54, y: 0.60, w: 0.10, h: 0.10 },
  ],
  south_rural: [
    { x: 0.28, y: 0.70, w: 0.36, h: 0.18 },
  ],
};

const CLUSTER_LABEL_POS = {
  darjeeling_hills:   { x: 0.27, y: 0.05, label: "DARJ" },
  north_bengal:       { x: 0.31, y: 0.18, label: "N.BENGAL" },
  malda:              { x: 0.31, y: 0.34, label: "MALDA" },
  murshidabad:        { x: 0.41, y: 0.44, label: "MURSHIDABAD" },
  burdwan_industrial: { x: 0.20, y: 0.50, label: "BURDWAN" },
  matua_belt:         { x: 0.62, y: 0.51, label: "MATUA / N24" },
  jungle_mahal:       { x: 0.18, y: 0.67, label: "JUNGLE MAHAL" },
  presidency_suburbs: { x: 0.43, y: 0.57, label: "PRESIDENCY" },
  kolkata_urban:      { x: 0.59, y: 0.65, label: "KOL" },
  south_rural:        { x: 0.46, y: 0.79, label: "SOUTH RURAL" },
};

// Draw the WB map at a given anchor, with options for which clusters to fill
// or highlight. ox/oy/scale are slide inches.
function drawWBMap(pptx, slide, opts) {
  const { ox, oy, scale, fillSet = new Set(), highlightCluster = null,
          showLabels = true, labelColor = STATIC, labelSize = 7,
          dimOnly = false, fillColor = PARCHMENT, highlightColor = SIGNAL } = opts;

  Object.entries(CLUSTER_GEOM).forEach(([cid, cells]) => {
    const isHighlight = (cid === highlightCluster);
    const isFilled = fillSet.has(cid);

    cells.forEach((c) => {
      const x = ox + c.x * scale;
      const y = oy + c.y * scale;
      const w = c.w * scale;
      const h = c.h * scale;

      let cellFill, cellLine;
      if (isHighlight) {
        cellFill = { color: highlightColor };
        cellLine = { type: "none" };
      } else if (dimOnly) {
        // dim parchment fill — same Bengal silhouette, just dim
        cellFill = { color: PARCHMENT, transparency: 88 };
        cellLine = { type: "none" };
      } else if (isFilled) {
        cellFill = { color: fillColor };
        cellLine = { type: "none" };
      } else {
        // hollow cells render as dim parchment so silhouette stays continuous
        cellFill = { color: PARCHMENT, transparency: 88 };
        cellLine = { type: "none" };
      }
      slide.addShape(pptx.ShapeType.rect, { x, y, w, h, fill: cellFill, line: cellLine });
    });
  });

  if (showLabels) {
    // Smaller cells need a smaller label to fit inside cell bounds
    const SMALL_CELL_CLUSTERS = new Set(["darjeeling_hills", "kolkata_urban", "malda"]);
    Object.entries(CLUSTER_LABEL_POS).forEach(([cid, lp]) => {
      const isHighlight = (cid === highlightCluster);
      // For highlighted cluster on cluster-detail slide, draw label dark on green
      const color = isHighlight ? NEAR_BLACK : labelColor;
      const fs = SMALL_CELL_CLUSTERS.has(cid) ? Math.min(labelSize, 7) : labelSize;
      slide.addText(lp.label, {
        x: ox + lp.x * scale - 0.30,
        y: oy + lp.y * scale - 0.06,
        w: 0.80, h: 0.18,
        fontFace: "Courier New", fontSize: fs, bold: isHighlight,
        color, align: "center", margin: 0,
      });
    });
  }
}

// ────────────────────────────────────────────────────────────────
// CLUSTER DATA — predicted vs actual (estimated)
// ────────────────────────────────────────────────────────────────
const CLUSTERS = {
  matua_belt: {
    title: "Matua Belt (Nadia · N24Pgs)",
    seats: 40,
    predTMC: 65, predBJP: 30,
    actTMC: 30, actBJP: 60,
    predSeats: "TMC 28 · BJP 12",
    actSeats:  "BJP 33 · TMC 7",
    factorHead: "Reverse CAA swing.",
    factorBody: "Matua identification with BJP's CAA delivery, not the modelled backlash.",
    predTMCWin: true, actTMCWin: false,
  },
  presidency_suburbs: {
    title: "Presidency Suburbs",
    seats: 40,
    predTMC: 52, predBJP: 30,
    actTMC: 36, actBJP: 50,
    predSeats: "TMC 28 · BJP 12",
    actSeats:  "BJP 30 · TMC 10",
    factorHead: "Hindu consolidation.",
    factorBody: "Unified BJP voteshare across heterogeneous suburbs.",
    predTMCWin: true, actTMCWin: false,
  },
  jungle_mahal: {
    title: "Jungle Mahal",
    seats: 50,
    predTMC: 58, predBJP: 28,
    actTMC: 32, actBJP: 56,
    predSeats: "TMC 38 · BJP 12",
    actSeats:  "BJP 38 · TMC 12",
    factorHead: "Sustained BJP organisation.",
    factorBody: "2021 anti-BJP correction did not stick; rural welfare delivery held.",
    predTMCWin: true, actTMCWin: false,
  },
  south_rural: {
    title: "South Rural",
    seats: 35,
    predTMC: 55, predBJP: 32,
    actTMC: 35, actBJP: 52,
    predSeats: "TMC 25 · BJP 10",
    actSeats:  "BJP 26 · TMC 9",
    factorHead: "Anti-incumbency.",
    factorBody: "Corruption cases (Sandeshkhali, recruitment scam) cut deepest here.",
    predTMCWin: true, actTMCWin: false,
  },
  kolkata_urban: {
    title: "Kolkata Urban",
    seats: 32,
    predTMC: 50, predBJP: 28,
    actTMC: 36, actBJP: 48,
    predSeats: "TMC 22 · BJP 10",
    actSeats:  "BJP 20 · TMC 12",
    factorHead: "Muslim vote split.",
    factorBody: "4-way fragmentation handed BJP pluralities in Muslim-mixed seats.",
    predTMCWin: true, actTMCWin: false,
  },
  burdwan_industrial: {
    title: "Burdwan Industrial",
    seats: 25,
    predTMC: 53, predBJP: 30,
    actTMC: 35, actBJP: 50,
    predSeats: "TMC 17 · BJP 8",
    actSeats:  "BJP 18 · TMC 7",
    factorHead: "Industrial worker swing.",
    factorBody: "Economic anxiety + Hindu consolidation, not modelled together.",
    predTMCWin: true, actTMCWin: false,
  },
  north_bengal: {
    title: "North Bengal",
    seats: 24,
    predTMC: 48, predBJP: 35,
    actTMC: 28, actBJP: 56,
    predSeats: "TMC 14 · BJP 10",
    actSeats:  "BJP 22 · TMC 2",
    factorHead: "SIR voter-roll deletions.",
    factorBody: "Disproportionate impact in Muslim-majority blocks; turnout asymmetry.",
    predTMCWin: true, actTMCWin: false,
  },
  murshidabad: {
    title: "Murshidabad",
    seats: 22,
    predTMC: 78, predBJP: 12,
    actTMC: 52, actBJP: 38,
    predSeats: "TMC 19 · BJP 3",
    actSeats:  "TMC 13 · BJP 9",
    factorHead: "Held — but barely.",
    factorBody: "Muslim consolidation worked here as modelled. The model was right about this cluster.",
    predTMCWin: true, actTMCWin: true,
  },
  malda: {
    title: "Malda",
    seats: 12,
    predTMC: 56, predBJP: 30,
    actTMC: 38, actBJP: 48,
    predSeats: "TMC 7 · BJP 4 · INC 1",
    actSeats:  "BJP 7 · TMC 4 · INC 1",
    factorHead: "Muslim split + INC weakness.",
    factorBody: "AIMIM/AJUP fragmentation handed BJP pluralities.",
    predTMCWin: true, actTMCWin: false,
  },
  darjeeling_hills: {
    title: "Darjeeling Hills",
    seats: 13,
    predTMC: 22, predBJP: 50,
    actTMC: 20, actBJP: 60,
    predSeats: "BJP/GJM 10 · TMC 3",
    actSeats:  "BJP/GJM 10 · TMC 2 · Oth 1",
    factorHead: "Correctly predicted.",
    factorBody: "BJP/GJM alliance worked as modelled.",
    predTMCWin: false, actTMCWin: false,
  },
};

// Order by impact (largest miss first)
const CLUSTER_ORDER = [
  "matua_belt", "presidency_suburbs", "jungle_mahal", "south_rural",
  "kolkata_urban", "burdwan_industrial", "north_bengal", "murshidabad",
  "malda", "darjeeling_hills",
];

// ────────────────────────────────────────────────────────────────
// Build deck
// ────────────────────────────────────────────────────────────────
const pptx = new pptxgen();
pptx.layout = "LAYOUT_16x9";
pptx.title = "WB 2026 Post-Mortem v2";

// ─── SLIDE 1 — COVER ──────────────────────────────────────────
{
  const s = pptx.addSlide();
  bg(s);
  s.addText("POST-MORTEM · WEST BENGAL 2026", {
    x: 0.5, y: 0.30, w: 9.0, h: 0.22,
    fontFace: "Courier New", fontSize: 9, color: STATIC, charSpacing: 2, margin: 0,
  });
  s.addText([
    { text: "We staked ", options: { color: PARCHMENT } },
    { text: "TMC.",       options: { color: SIGNAL } },
  ], {
    x: 0.5, y: 1.30, w: 9.0, h: 0.85,
    fontFace: "Arial Narrow", fontSize: 48, bold: true, margin: 0,
  });
  s.addText("Bengal voted otherwise.", {
    x: 0.5, y: 2.15, w: 9.0, h: 0.85,
    fontFace: "Arial Narrow", fontSize: 48, bold: true, color: PARCHMENT, margin: 0,
  });
  s.addText("DECISION INFRASTRUCTURE · 4 MAY 2026", {
    x: 0.5, y: 3.30, w: 6.0, h: 0.28,
    fontFace: "Courier New", fontSize: 10, color: STATIC, charSpacing: 2, margin: 0,
  });
  addMarkBL(pptx, s);
}

// ─── SLIDE 2 — THE NUMBERS ────────────────────────────────────
{
  const s = pptx.addSlide();
  bg(s); addMark(pptx, s); addFooter(s, 2);
  addEyebrow(s, "01 — THE CALL VS THE RESULT");
  s.addText("Every party landed outside the band.", {
    x: 0.5, y: 0.62, w: 8.5, h: 0.6,
    fontFace: "Arial Narrow", fontSize: 32, bold: true, color: PARCHMENT, margin: 0,
  });
  s.addShape(pptx.ShapeType.line, { x: 0.5, y: 1.40, w: 9.0, h: 0, line: { color: STATIC, width: 0.5 } });
  const cards = [
    { label: "TMC",         pred: "194 ± 10", actual: "84",  delta: "-110", deltaGreen: false },
    { label: "BJP",         pred: "45 ± 10",  actual: "203", delta: "+158", deltaGreen: true  },
    { label: "LEFT + CONG", pred: "50 ± 10",  actual: "6",   delta: "-44",  deltaGreen: false },
    { label: "OTHERS",      pred: "5 ± 3",    actual: "1",   delta: "-4",   deltaGreen: false },
  ];
  const cw = 2.10, ch = 2.30, cy = 1.65, cgap = 0.18, startX = 0.5;
  cards.forEach((c, i) => {
    const cx = startX + i * (cw + cgap);
    s.addShape(pptx.ShapeType.rect, {
      x: cx, y: cy, w: cw, h: ch,
      fill: { color: VOID }, line: { color: PARCHMENT, width: 0.75, transparency: 80 },
    });
    s.addText(c.label, { x: cx, y: cy + 0.10, w: cw, h: 0.26, fontFace: "Courier New", fontSize: 9, color: STATIC, align: "center", charSpacing: 2, margin: 0 });
    s.addText("PREDICTED", { x: cx + 0.15, y: cy + 0.42, w: cw - 0.3, h: 0.20, fontFace: "Courier New", fontSize: 8, color: STATIC, margin: 0 });
    s.addText(c.pred, { x: cx + 0.15, y: cy + 0.62, w: cw - 0.3, h: 0.30, fontFace: "Calibri", fontSize: 13, color: DETAIL, margin: 0 });
    s.addText("ACTUAL", { x: cx + 0.15, y: cy + 1.00, w: cw - 0.3, h: 0.20, fontFace: "Courier New", fontSize: 8, color: STATIC, margin: 0 });
    s.addText(c.actual, { x: cx + 0.15, y: cy + 1.18, w: cw - 0.3, h: 0.65, fontFace: "Arial Narrow", fontSize: 44, bold: true, color: PARCHMENT, margin: 0 });
    s.addText(c.delta, { x: cx + 0.15, y: cy + 1.85, w: cw - 0.3, h: 0.32, fontFace: "Arial Narrow", fontSize: 18, bold: true, color: c.deltaGreen ? SIGNAL : STATIC, margin: 0 });
  });
  s.addText("BJP voteshare 45.1% (modelled ~22%) · TMC 41.0% (modelled ~52%)", {
    x: 0.5, y: 4.08, w: 9.0, h: 0.28,
    fontFace: "Calibri", fontSize: 11, color: DETAIL, margin: 0,
  });
}

// ─── SLIDES 3 & 4 — DENSE PER-AC MAP (PREDICTED, ACTUAL) ──
// Format mirrors the pre-election forecast slide: per-AC WB map (centre),
// parliament hemicycle + party legend (left), three metric cards (right).
// Party-convention colors used here only.
const C_TMC  = "3FA34D";  // green — established TMC convention
const C_BJP  = "F4A02C";  // orange
const C_INDI = "C44545";  // red
const C_OTH  = "8A8A8A";  // grey

function addDensePerAcSlide(pptx, opts) {
  const {
    slideNum, eyebrow, headlineLeft, headlineRightPlain, headlineRightSignal,
    seatHeadline, mapPath, hemiPath, legend,
    cardLeader, cardLeaderMargin, cardLeaderSeats,
  } = opts;
  const s = pptx.addSlide();
  bg(s); addMark(pptx, s); addFooter(s, slideNum);
  addEyebrow(s, eyebrow);

  // Split-lettering headline at top
  s.addText([
    { text: headlineLeft, options: { color: PARCHMENT } },
    { text: " ", options: {} },
    { text: headlineRightPlain, options: { color: PARCHMENT } },
    { text: headlineRightSignal, options: { color: SIGNAL } },
  ], {
    x: 0.4, y: 0.55, w: 9.2, h: 0.55,
    fontFace: "Arial Narrow", fontSize: 36, bold: true, margin: 0,
  });

  // ── LEFT BLOCK — seat distribution + hemicycle + legend ──
  const lx = 0.4, lw = 2.8;
  s.addText("SEAT DISTRIBUTION", {
    x: lx, y: 1.20, w: lw, h: 0.20,
    fontFace: "Courier New", fontSize: 9, color: STATIC, charSpacing: 2, margin: 0,
  });
  s.addText(seatHeadline, {
    x: lx, y: 1.42, w: lw, h: 0.34,
    fontFace: "Arial Narrow", fontSize: 22, color: PARCHMENT, margin: 0,
  });
  // hemicycle image
  s.addImage({
    path: hemiPath,
    x: lx, y: 1.80, w: lw, h: 1.55,
    sizing: { type: "contain", w: lw, h: 1.55 },
  });
  s.addText("294 SEATS  ·  148 = MAJORITY", {
    x: lx, y: 3.40, w: lw, h: 0.20,
    fontFace: "Courier New", fontSize: 8, color: STATIC, charSpacing: 1.5, margin: 0,
  });
  // 4-row legend
  const legY0 = 3.70, legRowH = 0.32;
  legend.forEach((row, i) => {
    const y = legY0 + i * legRowH;
    s.addShape(pptx.ShapeType.rect, {
      x: lx, y: y + 0.05, w: 0.16, h: 0.16,
      fill: { color: row.color }, line: { color: row.color, width: 0 },
    });
    s.addText(row.party, {
      x: lx + 0.24, y, w: 1.4, h: 0.26,
      fontFace: "Arial Narrow", fontSize: 13, bold: true, color: PARCHMENT, margin: 0,
    });
    s.addText(String(row.count), {
      x: lx + 1.6, y, w: 1.2, h: 0.26,
      fontFace: "Arial Narrow", fontSize: 13, bold: true,
      color: row.highlight ? SIGNAL : PARCHMENT, align: "right", margin: 0,
    });
  });

  // ── CENTRE BLOCK — per-AC map ──
  s.addText("WEST BENGAL · 294 ASSEMBLY CONSTITUENCIES", {
    x: 3.4, y: 1.20, w: 4.2, h: 0.20,
    fontFace: "Courier New", fontSize: 9, color: STATIC, charSpacing: 2, margin: 0, align: "center",
  });
  s.addImage({
    path: mapPath,
    x: 3.4, y: 1.40, w: 4.2, h: 3.95,
    sizing: { type: "contain", w: 4.2, h: 3.95 },
  });

  // ── RIGHT BLOCK — three metric cards ──
  const rx = 7.80, rw = 1.90;
  // Card 1: MAJORITY LINE / 148
  s.addShape(pptx.ShapeType.rect, {
    x: rx, y: 1.20, w: rw, h: 1.18,
    fill: { color: VOID }, line: { color: BORDER, width: 0.75 },
  });
  s.addText("MAJORITY LINE", {
    x: rx + 0.14, y: 1.30, w: rw - 0.20, h: 0.20,
    fontFace: "Courier New", fontSize: 8, color: STATIC, charSpacing: 1.5, margin: 0,
  });
  s.addText("148", {
    x: rx + 0.14, y: 1.55, w: rw - 0.20, h: 0.70,
    fontFace: "Arial Narrow", fontSize: 36, bold: true, color: PARCHMENT, margin: 0,
  });

  // Card 2: <LEADER> MARGIN with vertical signal accent
  const c2y = 2.55;
  s.addShape(pptx.ShapeType.rect, {
    x: rx, y: c2y, w: rw, h: 1.18,
    fill: { color: VOID }, line: { color: BORDER, width: 0.75 },
  });
  s.addShape(pptx.ShapeType.rect, {
    x: rx, y: c2y, w: 0.06, h: 1.18,
    fill: { color: SIGNAL }, line: { color: SIGNAL, width: 0 },
  });
  s.addText(`${cardLeader} MARGIN`, {
    x: rx + 0.18, y: c2y + 0.10, w: rw - 0.24, h: 0.20,
    fontFace: "Courier New", fontSize: 8, color: STATIC, charSpacing: 1.5, margin: 0,
  });
  s.addText(cardLeaderMargin, {
    x: rx + 0.18, y: c2y + 0.35, w: rw - 0.24, h: 0.70,
    fontFace: "Arial Narrow", fontSize: 36, bold: true, color: SIGNAL, margin: 0,
  });

  // Card 3: <LEADER> SEATS / 294 — value
  const c3y = 3.90;
  s.addShape(pptx.ShapeType.rect, {
    x: rx, y: c3y, w: rw, h: 1.18,
    fill: { color: VOID }, line: { color: BORDER, width: 0.75 },
  });
  s.addText(`${cardLeader} SEATS / 294`, {
    x: rx + 0.14, y: c3y + 0.10, w: rw - 0.20, h: 0.20,
    fontFace: "Courier New", fontSize: 8, color: STATIC, charSpacing: 1.5, margin: 0,
  });
  s.addText(String(cardLeaderSeats), {
    x: rx + 0.14, y: c3y + 0.35, w: rw - 0.20, h: 0.70,
    fontFace: "Arial Narrow", fontSize: 36, bold: true, color: PARCHMENT, margin: 0,
  });
}

// SLIDE 3 — PREDICTED
addDensePerAcSlide(pptx, {
  slideNum: 3,
  eyebrow: "03 — 294 ASSEMBLY SEATS  |  PREDICTED WINNER  |  WEST BENGAL 2026",
  headlineLeft: "TMC holds the",
  headlineRightPlain: "",
  headlineRightSignal: "map.",
  seatHeadline: "294  /  TMC 194",
  mapPath: `${MAPS_DIR}/wb_predicted_per_ac.png`,
  hemiPath: `${MAPS_DIR}/wb_predicted_hemicycle.png`,
  legend: [
    { party: "TMC",  count: 194, color: C_TMC,  highlight: true  },
    { party: "BJP",  count:  45, color: C_BJP,  highlight: false },
    { party: "INDI", count:  50, color: C_INDI, highlight: false },
    { party: "OTH",  count:   5, color: C_OTH,  highlight: false },
  ],
  cardLeader: "TMC",
  cardLeaderMargin: "+47",
  cardLeaderSeats: 194,
});

// SLIDE 4 — ACTUAL
addDensePerAcSlide(pptx, {
  slideNum: 4,
  eyebrow: "04 — 294 ASSEMBLY SEATS  |  ACTUAL WINNER  |  WEST BENGAL 2026",
  headlineLeft: "BJP holds the",
  headlineRightPlain: "",
  headlineRightSignal: "map.",
  seatHeadline: "294  /  BJP 203",
  mapPath: `${MAPS_DIR}/wb_actual_per_ac.png`,
  hemiPath: `${MAPS_DIR}/wb_actual_hemicycle.png`,
  legend: [
    { party: "BJP",  count: 203, color: C_BJP,  highlight: true  },
    { party: "TMC",  count:  84, color: C_TMC,  highlight: false },
    { party: "INDI", count:   6, color: C_INDI, highlight: false },
    { party: "OTH",  count:   1, color: C_OTH,  highlight: false },
  ],
  cardLeader: "BJP",
  cardLeaderMargin: "+55",
  cardLeaderSeats: 203,
});

// ─── SLIDES 5–14 — CLUSTER ANALYSIS ───────────────────────────
CLUSTER_ORDER.forEach((cid, idx) => {
  const slideNum = 5 + idx;
  const ord = String(idx + 1).padStart(2, "0");
  const c = CLUSTERS[cid];
  const s = pptx.addSlide();
  bg(s); addMark(pptx, s); addFooter(s, slideNum);
  addEyebrow(s, `ANALYSIS · ${ord} OF 10 · ${c.title.toUpperCase()}`);

  // Headline
  const predWinner = c.predTMCWin ? "TMC" : "BJP";
  const actWinner = c.actTMCWin ? "TMC" : "BJP";
  s.addText(`${c.title}: ${predWinner} → ${actWinner}`, {
    x: 0.5, y: 0.62, w: 9.0, h: 0.6,
    fontFace: "Arial Narrow", fontSize: 30, bold: true, color: PARCHMENT, margin: 0,
  });
  s.addShape(pptx.ShapeType.line, { x: 0.5, y: 1.42, w: 9.0, h: 0, line: { color: STATIC, width: 0.5 } });

  // LEFT — mini-map highlighting this cluster (real WB geography)
  s.addImage({
    path: `${MAPS_DIR}/wb_cluster_${cid}.png`,
    x: 0.55, y: 1.65, w: 3.30, h: 3.40,
    sizing: { type: "contain", w: 3.30, h: 3.40 },
  });

  // MIDDLE — numbers
  const mx = 4.1, my = 1.70, mw = 2.9;
  s.addText("PREDICTED", { x: mx, y: my, w: mw, h: 0.22, fontFace: "Courier New", fontSize: 9, color: STATIC, charSpacing: 1.5, margin: 0 });
  s.addText(`TMC ${c.predTMC}%`, { x: mx, y: my + 0.24, w: mw, h: 0.30, fontFace: "Calibri", fontSize: 14, color: PARCHMENT, margin: 0 });
  s.addText(`BJP ${c.predBJP}%`, { x: mx, y: my + 0.50, w: mw, h: 0.30, fontFace: "Calibri", fontSize: 14, color: DETAIL, margin: 0 });

  s.addText("ACTUAL", { x: mx, y: my + 0.95, w: mw, h: 0.22, fontFace: "Courier New", fontSize: 9, color: STATIC, charSpacing: 1.5, margin: 0 });
  s.addText(`TMC ${c.actTMC}%`, { x: mx, y: my + 1.19, w: mw, h: 0.30, fontFace: "Calibri", fontSize: 14, color: PARCHMENT, margin: 0 });
  s.addText(`BJP ${c.actBJP}%`, { x: mx, y: my + 1.45, w: mw, h: 0.30, fontFace: "Calibri", fontSize: 14, color: DETAIL, margin: 0 });

  s.addText("SEATS", { x: mx, y: my + 1.90, w: mw, h: 0.22, fontFace: "Courier New", fontSize: 9, color: STATIC, charSpacing: 1.5, margin: 0 });
  s.addText(`Pred: ${c.predSeats}`, { x: mx, y: my + 2.13, w: mw, h: 0.26, fontFace: "Calibri", fontSize: 11, color: DETAIL, margin: 0 });
  s.addText(`Act:  ${c.actSeats}`,  { x: mx, y: my + 2.38, w: mw, h: 0.26, fontFace: "Calibri", fontSize: 11, color: DETAIL, margin: 0 });

  // RIGHT — factor
  const rx = 7.20, ry = 1.70, rw = 2.45;
  s.addText("THE FACTOR", { x: rx, y: ry, w: rw, h: 0.22, fontFace: "Courier New", fontSize: 9, color: STATIC, charSpacing: 1.5, margin: 0 });
  s.addText(c.factorHead, {
    x: rx, y: ry + 0.30, w: rw, h: 0.50,
    fontFace: "Calibri", fontSize: 14, bold: true, color: PARCHMENT, margin: 0,
  });
  s.addText(c.factorBody, {
    x: rx, y: ry + 0.95, w: rw, h: 2.20,
    fontFace: "Calibri", fontSize: 12, color: BODY_COPY, margin: 0,
  });
  s.addText(`${c.seats} SEATS`, {
    x: rx, y: ry + 2.85, w: rw, h: 0.30,
    fontFace: "Courier New", fontSize: 10, color: STATIC, charSpacing: 1.5, margin: 0,
  });
});

// ─── SLIDE 15 — THE MECHANISM ─────────────────────────────────
{
  const s = pptx.addSlide();
  bg(s); addMark(pptx, s); addFooter(s, 15);
  addEyebrow(s, "05 — STRUCTURAL FAILURE");
  s.addText("Three things to fix in the model.", {
    x: 0.5, y: 0.62, w: 8.5, h: 0.6,
    fontFace: "Arial Narrow", fontSize: 32, bold: true, color: PARCHMENT, margin: 0,
  });
  s.addShape(pptx.ShapeType.line, { x: 0.5, y: 1.42, w: 9.0, h: 0, line: { color: STATIC, width: 0.5 } });
  const mechs = [
    { head: "Anchoring on 2021 baseline.",                head2: "", body: "Uniform-swing assumed corrections of 10-20pp; realised swing was 25-30pp." },
    { head: "Hindu consolidation modelled as localized.", head2: "", body: "The data shows it was the dominant statewide frame." },
    { head: "SIR weight too small.",                      head2: "", body: "Modelled as marginal; reality showed structural turnout asymmetry across all Muslim-majority clusters." },
  ];
  const top = 1.70, rh = 1.10;
  mechs.forEach((m, i) => {
    const y = top + i * rh;
    s.addText(`0${i + 1}`, { x: 0.5, y, w: 0.5, h: 0.5, fontFace: "Courier New", fontSize: 11, color: STATIC, margin: 0 });
    s.addText(m.head, { x: 1.0, y, w: 8.4, h: 0.40, fontFace: "Calibri", fontSize: 13, bold: true, color: PARCHMENT, margin: 0 });
    s.addText(m.body, { x: 1.0, y: y + 0.40, w: 8.4, h: 0.65, fontFace: "Calibri", fontSize: 13, color: BODY_COPY, margin: 0 });
  });
}

// ─── SLIDE 16 — CLOSING ───────────────────────────────────────
{
  const s = pptx.addSlide();
  bg(s);
  s.addText("We'll be back", {
    x: 0.5, y: 1.40, w: 9.0, h: 0.85,
    fontFace: "Arial Narrow", fontSize: 40, bold: true, color: PARCHMENT, margin: 0,
  });
  s.addText([
    { text: "for the next ", options: { color: PARCHMENT } },
    { text: "nail-biter.",   options: { color: SIGNAL } },
  ], {
    x: 0.5, y: 2.30, w: 9.0, h: 0.85,
    fontFace: "Arial Narrow", fontSize: 40, bold: true, margin: 0,
  });
  s.addText("INDIA · 28 STATES · EVERY ELECTION ITS OWN PHYSICS", {
    x: 0.5, y: 3.55, w: 8.0, h: 0.28,
    fontFace: "Courier New", fontSize: 10, color: STATIC, charSpacing: 2, margin: 0,
  });
  addMarkBL(pptx, s);
}

pptx.writeFile({ fileName: OUT })
  .then(() => console.log("DONE:", OUT))
  .catch((e) => { console.error("ERROR:", e); process.exit(1); });
