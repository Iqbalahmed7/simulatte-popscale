"use strict";
// WB 2026 Post-Mortem Deck — 9 slides, widescreen 10" × 5.63"
// Brand: Simulatte. LAYOUT_16x9 to match Construct Capabilities deck.
const pptxgen = require("pptxgenjs");

const OUT = "/Users/admin/Documents/Simulatte Projects/PopScale/engineering/wb_2026_postmortem_deck.pptx";

// Palette
const VOID      = "050505";
const PARCHMENT = "E9E6DF";
const SIGNAL    = "A8FF3E";
const STATIC    = "9A9997";
const BODY_COPY = "C9C7C0";
const DETAIL    = "A8A6A0";
const BORDER    = "1A1A1A";
const NEAR_BLACK = "1A1A1A";

// Engine mark — top-right, non-cover slides (size 0.36)
function addMark(pptx, slide) {
  slide.addShape(pptx.ShapeType.ellipse, { x: 9.32, y: 0.14, w: 0.36, h: 0.36, fill: { color: VOID }, line: { color: SIGNAL, width: 1.5 } });
  slide.addShape(pptx.ShapeType.ellipse, { x: 9.40, y: 0.22, w: 0.20, h: 0.20, fill: { color: VOID }, line: { color: SIGNAL, width: 1.0 } });
  slide.addShape(pptx.ShapeType.ellipse, { x: 9.46, y: 0.28, w: 0.08, h: 0.08, fill: { color: SIGNAL }, line: { color: SIGNAL, width: 1 } });
}

// Engine mark + wordmark for cover/closing — bottom-left
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

const pptx = new pptxgen();
pptx.layout = "LAYOUT_16x9"; // 10" × 5.625"
pptx.title = "WB 2026 Post-Mortem";

// ══════════════════════════════════════════════════════════════
// SLIDE 1 — Cover
// ══════════════════════════════════════════════════════════════
{
  const s = pptx.addSlide();
  bg(s);
  s.addText("POST-MORTEM · WEST BENGAL 2026", {
    x: 0.5, y: 0.30, w: 9.0, h: 0.22,
    fontFace: "Courier New", fontSize: 9, color: STATIC, charSpacing: 2, margin: 0,
  });

  // Line 1 — "We staked TMC." with TMC in green
  s.addText([
    { text: "We staked ", options: { color: PARCHMENT } },
    { text: "TMC.",       options: { color: SIGNAL } },
  ], {
    x: 0.5, y: 1.30, w: 9.0, h: 0.85,
    fontFace: "Arial Narrow", fontSize: 48, bold: true, margin: 0,
  });

  // Line 2 — all parchment
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

// ══════════════════════════════════════════════════════════════
// SLIDE 2 — The Numbers
// ══════════════════════════════════════════════════════════════
{
  const s = pptx.addSlide();
  bg(s);
  addMark(pptx, s);
  addFooter(s, 2);
  addEyebrow(s, "01 — THE CALL VS THE RESULT");

  s.addText("Every party landed outside the band.", {
    x: 0.5, y: 0.62, w: 8.5, h: 0.6,
    fontFace: "Arial Narrow", fontSize: 32, bold: true, color: PARCHMENT, margin: 0,
  });

  s.addShape(pptx.ShapeType.line, { x: 0.5, y: 1.40, w: 9.0, h: 0, line: { color: STATIC, width: 0.5 } });

  // 4 metric cards laid out 4×1
  const cards = [
    { label: "TMC",         pred: "194 ± 10", actual: "84",  delta: "−110", deltaGreen: false },
    { label: "BJP",         pred: "45 ± 10",  actual: "203", delta: "+158",      deltaGreen: true  },
    { label: "LEFT + CONG", pred: "50 ± 10",  actual: "6",   delta: "−44",  deltaGreen: false },
    { label: "OTHERS",      pred: "5 ± 3",    actual: "1",   delta: "−4",   deltaGreen: false },
  ];

  const cw = 2.10, ch = 2.30, cy = 1.65, cgap = 0.18;
  const startX = 0.5;

  cards.forEach((c, i) => {
    const cx = startX + i * (cw + cgap);
    s.addShape(pptx.ShapeType.rect, {
      x: cx, y: cy, w: cw, h: ch,
      fill: { color: VOID }, line: { color: PARCHMENT, width: 0.75, transparency: 80 },
    });

    // Party label
    s.addText(c.label, {
      x: cx, y: cy + 0.10, w: cw, h: 0.26,
      fontFace: "Courier New", fontSize: 9, color: STATIC, align: "center", charSpacing: 2, margin: 0,
    });

    // PREDICTED row
    s.addText("PREDICTED", {
      x: cx + 0.15, y: cy + 0.42, w: cw - 0.3, h: 0.20,
      fontFace: "Courier New", fontSize: 8, color: STATIC, margin: 0,
    });
    s.addText(c.pred, {
      x: cx + 0.15, y: cy + 0.62, w: cw - 0.3, h: 0.30,
      fontFace: "Calibri", fontSize: 13, color: DETAIL, margin: 0,
    });

    // ACTUAL — big
    s.addText("ACTUAL", {
      x: cx + 0.15, y: cy + 1.00, w: cw - 0.3, h: 0.20,
      fontFace: "Courier New", fontSize: 8, color: STATIC, margin: 0,
    });
    s.addText(c.actual, {
      x: cx + 0.15, y: cy + 1.18, w: cw - 0.3, h: 0.65,
      fontFace: "Arial Narrow", fontSize: 44, bold: true, color: PARCHMENT, margin: 0,
    });

    // Delta
    s.addText(c.delta, {
      x: cx + 0.15, y: cy + 1.85, w: cw - 0.3, h: 0.32,
      fontFace: "Arial Narrow", fontSize: 18, bold: true,
      color: c.deltaGreen ? SIGNAL : STATIC, margin: 0,
    });
  });

  // Voteshare line
  s.addText("BJP voteshare 45.1% (modelled ~22%) · TMC 41.0% (modelled ~52%)", {
    x: 0.5, y: 4.08, w: 9.0, h: 0.28,
    fontFace: "Calibri", fontSize: 11, color: DETAIL, margin: 0,
  });
}

// ══════════════════════════════════════════════════════════════
// SLIDE 3 — The Map (centerpiece)
// ══════════════════════════════════════════════════════════════
{
  const s = pptx.addSlide();
  bg(s);
  addMark(pptx, s);
  addFooter(s, 3);
  addEyebrow(s, "01 — THE PREDICTED MAP VS THE ACTUAL");

  s.addText("Where we said TMC. Where TMC actually held.", {
    x: 0.5, y: 0.62, w: 8.5, h: 0.6,
    fontFace: "Arial Narrow", fontSize: 28, bold: true, color: PARCHMENT, margin: 0,
  });

  // Two cluster grids side by side
  const clusters = [
    { name: "Darjeeling",        col: 0, row: 0, predTMC: false, actualTMC: false },
    { name: "North Bengal",      col: 1, row: 0, predTMC: true,  actualTMC: false },
    { name: "Malda",             col: 2, row: 0, predTMC: true,  actualTMC: false },
    { name: "Murshidabad",       col: 3, row: 0, predTMC: true,  actualTMC: true  },
    { name: "Matua/Nadia-N24",   col: 4, row: 0, predTMC: true,  actualTMC: false },
    { name: "Burdwan Indl.",     col: 0, row: 1, predTMC: true,  actualTMC: false },
    { name: "Jungle Mahal",      col: 1, row: 1, predTMC: true,  actualTMC: false },
    { name: "South Rural",       col: 2, row: 1, predTMC: true,  actualTMC: false },
    { name: "Presidency Sub.",   col: 3, row: 1, predTMC: true,  actualTMC: false },
    { name: "Kolkata Urban",     col: 4, row: 1, predTMC: true,  actualTMC: false },
  ];

  // Layout — two grids spanning the slide width with breathing room
  const LX = 0.5, RX = 5.10, MW = 4.40, MTOP = 1.50;
  const COLS = 5, ROWS = 2;
  const gridH = 1.95;
  const cellW = MW / COLS;
  const cellH = gridH / ROWS;
  const gap = 0.05;

  // Headers
  s.addText("PREDICTED", {
    x: LX, y: MTOP, w: MW, h: 0.22,
    fontFace: "Courier New", fontSize: 9, color: STATIC, charSpacing: 2, margin: 0,
  });
  s.addText("ACTUAL", {
    x: RX, y: MTOP, w: MW, h: 0.22,
    fontFace: "Courier New", fontSize: 9, color: STATIC, charSpacing: 2, margin: 0,
  });

  const gridTop = MTOP + 0.28;

  // Grid borders
  s.addShape(pptx.ShapeType.rect, { x: LX, y: gridTop - 0.04, w: MW, h: gridH + 0.08, fill: { type: "none" }, line: { color: BORDER, width: 0.75 } });
  s.addShape(pptx.ShapeType.rect, { x: RX, y: gridTop - 0.04, w: MW, h: gridH + 0.08, fill: { type: "none" }, line: { color: BORDER, width: 0.75 } });

  function drawCell(x, y, w, h, isTMC, label) {
    if (isTMC) {
      s.addShape(pptx.ShapeType.rect, { x, y, w, h, fill: { color: PARCHMENT }, line: { color: PARCHMENT, width: 0.5 } });
      s.addText(label, {
        x: x + 0.04, y: y + 0.04, w: w - 0.08, h: h - 0.08,
        fontFace: "Courier New", fontSize: 7, bold: true, color: NEAR_BLACK, valign: "top", margin: 0,
      });
    } else {
      s.addShape(pptx.ShapeType.rect, { x, y, w, h, fill: { color: VOID }, line: { color: PARCHMENT, width: 0.5 } });
      s.addText(label, {
        x: x + 0.04, y: y + 0.04, w: w - 0.08, h: h - 0.08,
        fontFace: "Courier New", fontSize: 7, color: STATIC, valign: "top", margin: 0,
      });
    }
  }

  clusters.forEach((c) => {
    const cyL = gridTop + c.row * cellH + gap / 2;
    const cxL = LX + c.col * cellW + gap / 2;
    const cxR = RX + c.col * cellW + gap / 2;
    const w = cellW - gap;
    const h = cellH - gap;
    drawCell(cxL, cyL, w, h, c.predTMC, c.name);
    drawCell(cxR, cyL, w, h, c.actualTMC, c.name);
  });

  const capY = gridTop + gridH + 0.15;
  s.addText("Predicted: TMC majority · 194 ± 10 seats", {
    x: LX, y: capY, w: MW, h: 0.30,
    fontFace: "Calibri", fontSize: 11, color: DETAIL, margin: 0,
  });
  s.addText("Actual: BJP majority · 203 seats", {
    x: RX, y: capY, w: MW, h: 0.30,
    fontFace: "Calibri", fontSize: 11, color: DETAIL, margin: 0,
  });
}

// ══════════════════════════════════════════════════════════════
// SLIDE 4 — What We Weighted (statement → list)
// ══════════════════════════════════════════════════════════════
{
  const s = pptx.addSlide();
  bg(s);
  addMark(pptx, s);
  addFooter(s, 4);
  addEyebrow(s, "02 — INPUTS");

  // Split lettering: "weighted" in green
  s.addText([
    { text: "What the model ", options: { color: PARCHMENT } },
    { text: "weighted.",       options: { color: SIGNAL } },
  ], {
    x: 0.5, y: 0.62, w: 9.0, h: 0.7,
    fontFace: "Arial Narrow", fontSize: 32, bold: true, margin: 0,
  });

  s.addShape(pptx.ShapeType.line, { x: 0.5, y: 1.42, w: 9.0, h: 0, line: { color: STATIC, width: 0.5 } });

  const factors = [
    "TMC organisational depth in panchayats — the 2021 machine",
    "Muslim consolidation around TMC in Murshidabad — 90% TMC baseline",
    "CAA backlash hypothesis in the Matua belt",
    "Jungle Mahal tribal anti-BJP sentiment from 2021",
    "2021 baseline anchoring — 213 TMC seats",
  ];

  const top = 1.65, rh = 0.62;
  factors.forEach((t, i) => {
    const y = top + i * rh;
    // Number
    s.addText(`0${i + 1}`, {
      x: 0.5, y, w: 0.5, h: 0.4,
      fontFace: "Courier New", fontSize: 11, color: STATIC, margin: 0,
    });
    s.addText(t, {
      x: 1.0, y, w: 8.4, h: 0.45,
      fontFace: "Calibri", fontSize: 13, color: BODY_COPY, valign: "top", margin: 0,
    });
  });
}

// ══════════════════════════════════════════════════════════════
// SLIDE 5 — What Decided It
// ══════════════════════════════════════════════════════════════
{
  const s = pptx.addSlide();
  bg(s);
  addMark(pptx, s);
  addFooter(s, 5);
  addEyebrow(s, "02 — REALITY");

  s.addText("What actually decided the election.", {
    x: 0.5, y: 0.62, w: 8.5, h: 0.6,
    fontFace: "Arial Narrow", fontSize: 32, bold: true, color: PARCHMENT, margin: 0,
  });

  s.addShape(pptx.ShapeType.line, { x: 0.5, y: 1.42, w: 9.0, h: 0, line: { color: STATIC, width: 0.5 } });

  const factors = [
    { head: "Hindu consolidation as a statewide frame",     supp: "BJP voteshare 45.1% vs ~22% modelled" },
    { head: "SIR voter-roll deletions",                     supp: "Structural turnout asymmetry" },
    { head: "4-way Muslim vote fragmentation",              supp: "TMC / AIMIM / AJUP / INDI — pluralities, not consolidation" },
    { head: "Reverse Matua swing",                          supp: "Identification with BJP’s CAA delivery" },
    { head: "The depth of anti-incumbency",                 supp: "The unseen factor" },
  ];

  const top = 1.65, rh = 0.62;
  factors.forEach((f, i) => {
    const y = top + i * rh;
    s.addText(`0${i + 1}`, {
      x: 0.5, y, w: 0.5, h: 0.4,
      fontFace: "Courier New", fontSize: 11, color: STATIC, margin: 0,
    });
    s.addText(f.head, {
      x: 1.0, y, w: 5.0, h: 0.45,
      fontFace: "Calibri", fontSize: 13, bold: true, color: PARCHMENT, valign: "top", margin: 0,
    });
    s.addText(f.supp, {
      x: 6.05, y, w: 3.4, h: 0.45,
      fontFace: "Calibri", fontSize: 11, color: DETAIL, valign: "top", margin: 0,
    });
  });
}

// ══════════════════════════════════════════════════════════════
// SLIDE 6 — Statement (philosophical line)
// ══════════════════════════════════════════════════════════════
{
  const s = pptx.addSlide();
  bg(s);
  addMark(pptx, s);
  addFooter(s, 6);
  addEyebrow(s, "03 — WHAT THE MODEL SEES");

  // Line 1 — split, "visible" green
  s.addText([
    { text: "Simulations are good at the ", options: { color: PARCHMENT } },
    { text: "visible.",                      options: { color: SIGNAL } },
  ], {
    x: 0.5, y: 1.40, w: 9.0, h: 0.85,
    fontFace: "Arial Narrow", fontSize: 40, bold: true, margin: 0,
  });

  s.addText("The unseen is where they lose.", {
    x: 0.5, y: 2.30, w: 9.0, h: 0.85,
    fontFace: "Arial Narrow", fontSize: 40, bold: true, color: PARCHMENT, margin: 0,
  });

  s.addText("Surveys, news cycles, panchayat data — none captured the depth of voter sentiment that decided the election.", {
    x: 0.5, y: 3.55, w: 8.6, h: 0.80,
    fontFace: "Calibri", fontSize: 13, color: DETAIL, margin: 0,
  });
}

// ══════════════════════════════════════════════════════════════
// SLIDE 7 — The Mechanism
// ══════════════════════════════════════════════════════════════
{
  const s = pptx.addSlide();
  bg(s);
  addMark(pptx, s);
  addFooter(s, 7);
  addEyebrow(s, "03 — STRUCTURAL FAILURE");

  s.addText("Three things to fix in the model.", {
    x: 0.5, y: 0.62, w: 8.5, h: 0.6,
    fontFace: "Arial Narrow", fontSize: 32, bold: true, color: PARCHMENT, margin: 0,
  });

  s.addShape(pptx.ShapeType.line, { x: 0.5, y: 1.42, w: 9.0, h: 0, line: { color: STATIC, width: 0.5 } });

  const mechs = [
    { head: "Anchoring on 2021 baseline.",              body: "Uniform-swing assumed corrections of 10–20pp; realised swing was 25–30pp." },
    { head: "Hindu consolidation modelled as localized.", body: "The data shows it was the dominant statewide frame." },
    { head: "SIR weight too small.",                     body: "Modelled as marginal; reality showed structural turnout asymmetry across all Muslim-majority clusters." },
  ];

  const top = 1.70, rh = 1.10;
  mechs.forEach((m, i) => {
    const y = top + i * rh;
    s.addText(`0${i + 1}`, {
      x: 0.5, y, w: 0.5, h: 0.5,
      fontFace: "Courier New", fontSize: 11, color: STATIC, margin: 0,
    });
    s.addText(m.head, {
      x: 1.0, y, w: 8.4, h: 0.40,
      fontFace: "Calibri", fontSize: 13, bold: true, color: PARCHMENT, margin: 0,
    });
    s.addText(m.body, {
      x: 1.0, y: y + 0.40, w: 8.4, h: 0.65,
      fontFace: "Calibri", fontSize: 13, color: BODY_COPY, margin: 0,
    });
  });
}

// ══════════════════════════════════════════════════════════════
// SLIDE 8 — Calibration
// ══════════════════════════════════════════════════════════════
{
  const s = pptx.addSlide();
  bg(s);
  addMark(pptx, s);
  addFooter(s, 8);
  addEyebrow(s, "04 — WHAT CHANGES NEXT");

  s.addText("The priors update tomorrow.", {
    x: 0.5, y: 0.62, w: 8.5, h: 0.6,
    fontFace: "Arial Narrow", fontSize: 32, bold: true, color: PARCHMENT, margin: 0,
  });

  s.addShape(pptx.ShapeType.line, { x: 0.5, y: 1.42, w: 9.0, h: 0, line: { color: STATIC, width: 0.5 } });

  // 4 prior-shift cards 2x2
  const cards = [
    { lbl: "MURSHIDABAD TMC PRIOR",  val: "−12pp" },
    { lbl: "MATUA BELT TMC PRIOR",   val: "−18pp" },
    { lbl: "JUNGLE MAHAL TMC PRIOR", val: "−15pp" },
    { lbl: "BJP BASE ACROSS CLUSTERS", val: "+15–25pp" },
  ];

  const cw = 4.30, ch = 1.20, gx = 0.30;
  const startX = 0.5, startY = 1.65;

  cards.forEach((c, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const cx = startX + col * (cw + gx);
    const cy = startY + row * (ch + 0.20);
    s.addShape(pptx.ShapeType.rect, {
      x: cx, y: cy, w: cw, h: ch,
      fill: { color: VOID }, line: { color: PARCHMENT, width: 0.75, transparency: 80 },
    });
    s.addText(c.lbl, {
      x: cx + 0.15, y: cy + 0.12, w: cw - 0.3, h: 0.24,
      fontFace: "Courier New", fontSize: 9, color: STATIC, charSpacing: 1, margin: 0,
    });
    s.addText(c.val, {
      x: cx + 0.15, y: cy + 0.40, w: cw - 0.3, h: 0.75,
      fontFace: "Arial Narrow", fontSize: 44, bold: true, color: PARCHMENT, margin: 0,
    });
  });

  s.addText("BRIEF-021 calibration loop runs 5 May 09:07 IST. Adjustments computed per gentle 25% step rule. Next study uses corrected weights.", {
    x: 0.5, y: 4.40, w: 9.0, h: 0.40,
    fontFace: "Calibri", fontSize: 11, color: DETAIL, margin: 0,
  });
}

// ══════════════════════════════════════════════════════════════
// SLIDE 9 — Closing
// ══════════════════════════════════════════════════════════════
{
  const s = pptx.addSlide();
  bg(s);

  s.addText("We’ll be back", {
    x: 0.5, y: 1.40, w: 9.0, h: 0.85,
    fontFace: "Arial Narrow", fontSize: 40, bold: true, color: PARCHMENT, margin: 0,
  });

  // Split — "nail-biter" in green
  s.addText([
    { text: "for the next ",  options: { color: PARCHMENT } },
    { text: "nail-biter.",    options: { color: SIGNAL } },
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
