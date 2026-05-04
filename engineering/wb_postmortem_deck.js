"use strict";
// WB 2026 Post-Mortem Deck — v3: 6 slides
// 1. Cover  2. Numbers  3. Comparison map  4. Sim misses  5. Couldn't model  6. Calibrations
const pptxgen = require("pptxgenjs");

const OUT      = "/Users/admin/Documents/Simulatte Projects/PopScale/engineering/wb_2026_postmortem_deck.pptx";
const MAPS_DIR = "/Users/admin/Documents/Simulatte Projects/PopScale/engineering/maps";

// Palette
const VOID      = "050505";
const PARCHMENT = "E9E6DF";
const SIGNAL    = "A8FF3E";
const STATIC    = "9A9997";
const BODY_COPY = "C9C7C0";
const DETAIL    = "A8A6A0";
const BORDER    = "1A1A1A";

// ─────────────────────────────────────────────
// Brand frame helpers
// ─────────────────────────────────────────────
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
  slide.addText("Simulatte / Confidential", { x: 0.5, y: 5.32, w: 4, h: 0.20, fontFace: "Courier New", fontSize: 9, color: STATIC, align: "left", margin: 0 });
  slide.addText(String(slideNum), { x: 8.8, y: 5.32, w: 0.8, h: 0.20, fontFace: "Courier New", fontSize: 9, color: STATIC, align: "right", margin: 0 });
}
function addEyebrow(slide, txt) {
  slide.addText(txt, { x: 0.5, y: 0.22, w: 8.5, h: 0.22, fontFace: "Courier New", fontSize: 9, color: STATIC, charSpacing: 2, margin: 0 });
}
function bg(slide) { slide.background = { color: VOID }; }

// ─────────────────────────────────────────────
// Analysis slide helper
// Items: [{ num, head, body }]
// ─────────────────────────────────────────────
function addAnalysisSlide(pptx, opts) {
  const { slideNum, eyebrow, headlineParts, items } = opts;
  const s = pptx.addSlide();
  bg(s); addMark(pptx, s); addFooter(s, slideNum);
  addEyebrow(s, eyebrow);

  // Headline — split-lettering via headlineParts array: [{ text, signal }]
  s.addText(
    headlineParts.map(p => ({ text: p.text, options: { color: p.signal ? SIGNAL : PARCHMENT } })),
    { x: 0.5, y: 0.52, w: 9.0, h: 0.62,
      fontFace: "Arial Narrow", fontSize: 36, bold: true, margin: 0 }
  );

  // Divider
  s.addShape(pptx.ShapeType.line, { x: 0.5, y: 1.30, w: 9.0, h: 0, line: { color: STATIC, width: 0.5 } });

  // Items — 4-row layout with consistent row heights
  const rowH   = 0.82;
  const startY = 1.44;

  items.forEach((item, i) => {
    const y = startY + i * rowH;

    // Signal number tag
    s.addText(item.num, {
      x: 0.50, y, w: 0.40, h: 0.30,
      fontFace: "Courier New", fontSize: 11, bold: true, color: SIGNAL,
      charSpacing: 1, margin: 0,
    });

    // Bold heading
    s.addText(item.head, {
      x: 1.00, y, w: 8.50, h: 0.32,
      fontFace: "Arial Narrow", fontSize: 18, bold: true, color: PARCHMENT, margin: 0,
    });

    // Body copy
    s.addText(item.body, {
      x: 1.00, y: y + 0.34, w: 8.50, h: 0.42,
      fontFace: "Calibri", fontSize: 12, color: BODY_COPY, margin: 0,
    });
  });
}

// ─────────────────────────────────────────────
// Build deck
// ─────────────────────────────────────────────
const pptx = new pptxgen();
pptx.layout = "LAYOUT_16x9";
pptx.title  = "WB 2026 Post-Mortem";

// ─── SLIDE 1 — COVER ────────────────────────
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

// ─── SLIDE 2 — THE NUMBERS ───────────────────
{
  const s = pptx.addSlide();
  bg(s); addMark(pptx, s); addFooter(s, 2);
  addEyebrow(s, "01 — THE CALL VS THE RESULT");
  s.addText("Every party landed outside the band.", {
    x: 0.5, y: 0.62, w: 8.5, h: 0.60,
    fontFace: "Arial Narrow", fontSize: 32, bold: true, color: PARCHMENT, margin: 0,
  });
  s.addShape(pptx.ShapeType.line, { x: 0.5, y: 1.40, w: 9.0, h: 0, line: { color: STATIC, width: 0.5 } });

  const cards = [
    { label: "TMC",         pred: "194 ± 10", actual: "84",  delta: "−110", deltaGreen: false },
    { label: "BJP",         pred: "45 ± 10",  actual: "203", delta: "+158", deltaGreen: true  },
    { label: "LEFT + CONG", pred: "50 ± 10",  actual: "6",   delta: "−44",  deltaGreen: false },
    { label: "OTHERS",      pred: "5 ± 3",    actual: "1",   delta: "−4",   deltaGreen: false },
  ];
  const cw = 2.10, ch = 2.30, cy = 1.65, cgap = 0.18, startX = 0.5;
  cards.forEach((c, i) => {
    const cx = startX + i * (cw + cgap);
    s.addShape(pptx.ShapeType.rect, { x: cx, y: cy, w: cw, h: ch,
      fill: { color: VOID }, line: { color: PARCHMENT, width: 0.75, transparency: 80 } });
    s.addText(c.label, { x: cx, y: cy + 0.10, w: cw, h: 0.26,
      fontFace: "Courier New", fontSize: 9, color: STATIC, align: "center", charSpacing: 2, margin: 0 });
    s.addText("PREDICTED", { x: cx + 0.15, y: cy + 0.42, w: cw - 0.3, h: 0.20,
      fontFace: "Courier New", fontSize: 8, color: STATIC, margin: 0 });
    s.addText(c.pred, { x: cx + 0.15, y: cy + 0.62, w: cw - 0.3, h: 0.30,
      fontFace: "Calibri", fontSize: 13, color: DETAIL, margin: 0 });
    s.addText("ACTUAL", { x: cx + 0.15, y: cy + 1.00, w: cw - 0.3, h: 0.20,
      fontFace: "Courier New", fontSize: 8, color: STATIC, margin: 0 });
    s.addText(c.actual, { x: cx + 0.15, y: cy + 1.18, w: cw - 0.3, h: 0.65,
      fontFace: "Arial Narrow", fontSize: 44, bold: true, color: PARCHMENT, margin: 0 });
    s.addText(c.delta, { x: cx + 0.15, y: cy + 1.85, w: cw - 0.3, h: 0.32,
      fontFace: "Arial Narrow", fontSize: 18, bold: true,
      color: c.deltaGreen ? SIGNAL : STATIC, margin: 0 });
  });
  s.addText("BJP voteshare 45.1% (modelled ~22%)  ·  TMC 41.0% (modelled ~52%)", {
    x: 0.5, y: 4.08, w: 9.0, h: 0.28,
    fontFace: "Calibri", fontSize: 11, color: DETAIL, margin: 0,
  });
}

// ─── SLIDE 3 — COMPARISON MAP ────────────────
{
  const s = pptx.addSlide();
  bg(s); addMark(pptx, s); addFooter(s, 3);
  addEyebrow(s, "02 — PREDICTED VS ACTUAL  |  WEST BENGAL 2026");

  // Headline — identical split lettering to cover
  s.addText([
    { text: "We staked ",        options: { color: PARCHMENT } },
    { text: "TMC.",              options: { color: SIGNAL } },
    { text: " Bengal voted otherwise.", options: { color: PARCHMENT } },
  ], {
    x: 0.4, y: 0.52, w: 9.2, h: 0.55,
    fontFace: "Arial Narrow", fontSize: 32, bold: true, margin: 0,
  });

  // ── LEFT COLUMN — PREDICTED ──
  {
    const cx = 0.4, cw = 4.4;
    s.addText("PREDICTED", {
      x: cx, y: 1.20, w: cw, h: 0.22,
      fontFace: "Courier New", fontSize: 10, color: STATIC, charSpacing: 2, margin: 0,
    });
    const mapW = 3.4, mapH = 3.0;
    const mapX = cx + (cw - mapW) / 2;
    s.addImage({
      path: `${MAPS_DIR}/wb_predicted_per_ac.png`,
      x: mapX, y: 1.45, w: mapW, h: mapH,
      sizing: { type: "contain", w: mapW, h: mapH },
    });
    const sy = 1.45 + mapH + 0.10;
    s.addText("TMC 194 · BJP 45 · INDI 50 · OTH 5", {
      x: cx, y: sy, w: cw, h: 0.24,
      fontFace: "Calibri", fontSize: 11, color: PARCHMENT, align: "center", margin: 0,
    });
    s.addText("TMC majority by +47", {
      x: cx, y: sy + 0.24, w: cw, h: 0.24,
      fontFace: "Calibri", fontSize: 11, color: PARCHMENT, align: "center", margin: 0,
    });
    s.addText("Vote share: TMC 52% · BJP 22%", {
      x: cx, y: sy + 0.48, w: cw, h: 0.24,
      fontFace: "Calibri", fontSize: 11, color: PARCHMENT, align: "center", margin: 0,
    });
  }

  // ── RIGHT COLUMN — ACTUAL ──
  {
    const cx = 5.2, cw = 4.4;
    s.addText("ACTUAL", {
      x: cx, y: 1.20, w: cw, h: 0.22,
      fontFace: "Courier New", fontSize: 10, color: STATIC, charSpacing: 2, margin: 0,
    });
    const mapW = 3.4, mapH = 3.0;
    const mapX = cx + (cw - mapW) / 2;
    s.addImage({
      path: `${MAPS_DIR}/wb_actual_per_ac.png`,
      x: mapX, y: 1.45, w: mapW, h: mapH,
      sizing: { type: "contain", w: mapW, h: mapH },
    });
    const sy = 1.45 + mapH + 0.10;
    s.addText("BJP 203 · TMC 84 · INDI 6 · OTH 1", {
      x: cx, y: sy, w: cw, h: 0.24,
      fontFace: "Calibri", fontSize: 11, color: PARCHMENT, align: "center", margin: 0,
    });
    s.addText("BJP majority by +55", {
      x: cx, y: sy + 0.24, w: cw, h: 0.24,
      fontFace: "Calibri", fontSize: 11, color: PARCHMENT, align: "center", margin: 0,
    });
    s.addText("Vote share: BJP 45.1% · TMC 41.0%", {
      x: cx, y: sy + 0.48, w: cw, h: 0.24,
      fontFace: "Calibri", fontSize: 11, color: PARCHMENT, align: "center", margin: 0,
    });
  }
}

// ─── SLIDE 4 — SIMULATION-BASED MISSES ───────
addAnalysisSlide(pptx, {
  slideNum: 4,
  eyebrow: "03 — WHERE THE SIMULATION FAILED",
  headlineParts: [
    { text: "What the simulation", signal: false },
    { text: " got wrong.", signal: true },
  ],
  items: [
    {
      num: "01",
      head: "2021 baseline anchored every seat projection.",
      body: "The model over-weighted the 2021 anti-BJP correction. BJP's organisational depth and Hindu consolidation reversed that swing statewide — we had no prior encoding this.",
    },
    {
      num: "02",
      head: "CAA modelled as Matua backlash — it was Matua reward.",
      body: "We expected Matua grievance over delayed citizenship delivery. The community instead credited BJP for CAA passage; our voteshare prior for Nadia/N24Pgs was ~20pp off.",
    },
    {
      num: "03",
      head: "Muslim vote modelled as a unified TMC bloc.",
      body: "4-way fragmentation (AIMIM, AJUP, AISF, independents) in Kolkata, Malda and presidency seats handed BJP pluralities in seats we had TMC leading by 8–12pp.",
    },
    {
      num: "04",
      head: "Global voteshare prior: BJP ~22%, TMC ~52%.",
      body: "Actual: BJP 45.1%, TMC 41.0%. A ~20pp miss on BJP voteshare propagated through every cluster model. The prior came from 2021 assembly, not from 2024 Lok Sabha signals.",
    },
  ],
});

// ─── SLIDE 5 — THINGS WE COULDN'T MODEL ──────
addAnalysisSlide(pptx, {
  slideNum: 5,
  eyebrow: "04 — STRUCTURAL LIMITS",
  headlineParts: [
    { text: "What no", signal: false },
    { text: " dataset", signal: true },
    { text: " could see.", signal: false },
  ],
  items: [
    {
      num: "01",
      head: "SIR voter-roll deletions — structural disenfranchisement.",
      body: "Systematic deletion of names in Muslim-majority blocks in North Bengal and Murshidabad. Not visible from published rolls at modelling time; no signal in our population layer.",
    },
    {
      num: "02",
      head: "Anti-incumbency depth was qualitative, not quantifiable.",
      body: "Sandeshkhali incidents, teacher recruitment scam, post-2021 booth violence — each individually measurable, but the compounding effect on swing was not. No composite index existed.",
    },
    {
      num: "03",
      head: "2026 became a Hindu identity election, not a welfare election.",
      body: "The simulation ran on welfare delivery signals (beneficiary schemes, Duare Sarkar reach). The operative frame on election day was religio-cultural consolidation — orthogonal to our model.",
    },
    {
      num: "04",
      head: "BJP booth-level expansion was silent and unmeasured.",
      body: "Shakha density, worker count, mobilisation capacity — none are in any public dataset. The silent voter mobilisation differential vs 2021 was the largest single unmodelled variable.",
    },
  ],
});

// ─── SLIDE 6 — WHAT GOES INTO CALIBRATIONS ───
addAnalysisSlide(pptx, {
  slideNum: 6,
  eyebrow: "05 — CALIBRATION LOOP",
  headlineParts: [
    { text: "What", signal: false },
    { text: " changes", signal: true },
    { text: " next.", signal: false },
  ],
  items: [
    {
      num: "01",
      head: "Re-weight priors toward Lok Sabha over assembly cycles.",
      body: "Per-cluster Bayesian prior will weight 2024 + 2019 Lok Sabha results at 60%, 2021 assembly at 40%. Assembly corrections now treated as transient, not structural.",
    },
    {
      num: "02",
      head: "SIR deletion rate as a structural population feature.",
      body: "Add voter-roll attrition signal to the Niobe population layer — per-block deletion rate as a suppression proxy, especially in Muslim-majority geographies.",
    },
    {
      num: "03",
      head: "Anti-incumbency composite index.",
      body: "Build a scored index: scandal exposure × media intensity + violence incidents + service delivery gap score. Feed as a cluster-level adjustment on top of base voteshare.",
    },
    {
      num: "04",
      head: "Replace uniform swing with cluster-bounded correction.",
      body: "Each cluster treated independently with its own volatility ceiling. No statewide uniform-swing assumption. Cluster-level MAE from WB 2026 becomes the seed prior for the next study.",
    },
  ],
});

// ─────────────────────────────────────────────
// Write file
// ─────────────────────────────────────────────
pptx.writeFile({ fileName: OUT })
  .then(() => console.log(`✅  Written → ${OUT}`))
  .catch(err => { console.error(err); process.exit(1); });
