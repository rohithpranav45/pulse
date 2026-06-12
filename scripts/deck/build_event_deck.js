/**
 * Build docs/PULSE_event_to_distribution.pptx — 10-slide deck for the
 * "news event -> probability distribution for Brent calendar spreads"
 * assignment. Charts come from backend/data/research/event_study/.
 *
 * Run:  node scripts/deck/build_event_deck.js   (from repo root or anywhere)
 */
const path = require("path");
const fs = require("fs");
const pptxgen = require("pptxgenjs");

const ROOT = path.resolve(__dirname, "..", "..");
const CH = path.join(ROOT, "backend", "data", "research", "event_study");
const OUT = path.join(ROOT, "docs", "PULSE_event_to_distribution.pptx");
const R = JSON.parse(fs.readFileSync(path.join(CH, "results.json"), "utf8"));

// ── palette (PULSE dashboard) ────────────────────────────────────────────────
const BG = "0B0F1A", PANEL = "131A2A", GRID = "1E293B";
const GOLD = "F5A623", GOLD_L = "FCD34D", TEXT = "F8FAFC", BODY = "CBD5E1",
      MUT = "94A3B8", DIM = "64748B", GREEN = "10B981", CYAN = "22D3EE",
      RED = "FB7185";
const SANS = "Arial", MONO = "Courier New";

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";          // 10 x 5.625 in
pres.author = "Peruka Pranav";
pres.title = "PULSE — Event to Distribution";

function baseSlide() {
  const s = pres.addSlide();
  s.background = { color: BG };
  return s;
}

function eyebrow(s, txt, x = 0.55, y = 0.32) {
  s.addText(txt.toUpperCase(), {
    x, y, w: 9, h: 0.3, fontFace: SANS, fontSize: 10.5, bold: true,
    color: GOLD, charSpacing: 4, margin: 0,
  });
}

function title(s, txt, y = 0.62, size = 25, w = 9.0) {
  s.addText(txt, {
    x: 0.55, y, w, h: 0.62, fontFace: SANS, fontSize: size, bold: true,
    color: TEXT, margin: 0,
  });
}

function footer(s, n) {
  s.addText(`PULSE  ·  Event-to-Distribution Framework  ·  June 2026`, {
    x: 0.55, y: 5.28, w: 6, h: 0.25, fontFace: SANS, fontSize: 8,
    color: DIM, margin: 0,
  });
  s.addText(`${n} / 10`, {
    x: 9.0, y: 5.28, w: 0.55, h: 0.25, fontFace: MONO, fontSize: 8,
    color: DIM, align: "right", margin: 0,
  });
}

function statBox(s, x, y, w, label, value, sub, valColor = GOLD_L) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h: 0.92, fill: { color: PANEL }, line: { color: GRID, width: 1 },
    rectRadius: 0.06,
  });
  s.addText(label.toUpperCase(), {
    x: x + 0.12, y: y + 0.08, w: w - 0.24, h: 0.2, fontFace: SANS,
    fontSize: 8, bold: true, color: DIM, charSpacing: 2, margin: 0,
  });
  s.addText(value, {
    x: x + 0.12, y: y + 0.27, w: w - 0.24, h: 0.34, fontFace: MONO,
    fontSize: 15.5, bold: true, color: valColor, margin: 0,
  });
  if (sub) s.addText(sub, {
    x: x + 0.12, y: y + 0.62, w: w - 0.24, h: 0.24, fontFace: SANS,
    fontSize: 8, color: MUT, margin: 0,
  });
}

const ST = R.stats;
const LBL = { m1_m2: "M1-M2", m2_m4: "M2-M4", m1_m6: "M1-M6" };
const SPREAD_HEX = { m1_m2: GOLD, m2_m4: CYAN, m1_m6: GREEN };

/* ════════════════════════════════ SLIDE 1 — TITLE ═══════════════════════ */
{
  const s = baseSlide();
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.55, y: 0.55, w: 0.52, h: 0.52, fill: { color: GOLD },
    rectRadius: 0.09,
  });
  s.addText("P", {
    x: 0.55, y: 0.55, w: 0.52, h: 0.52, fontFace: SANS, fontSize: 22,
    bold: true, color: BG, align: "center", valign: "middle", margin: 0,
  });
  s.addText([
    { text: "PULSE", options: { fontSize: 15, bold: true, color: TEXT, charSpacing: 5, breakLine: true } },
    { text: "ENERGY INTELLIGENCE TERMINAL", options: { fontSize: 7.5, color: DIM, charSpacing: 2.5 } },
  ], { x: 1.22, y: 0.57, w: 4, h: 0.52, fontFace: SANS, margin: 0 });

  s.addText("From headline to distribution", {
    x: 0.55, y: 1.55, w: 9, h: 0.62, fontFace: SANS, fontSize: 34,
    bold: true, color: TEXT, margin: 0,
  });
  s.addText("A probabilistic framework for pricing geopolitical supply shocks into Brent calendar spreads", {
    x: 0.55, y: 2.2, w: 8.6, h: 0.4, fontFace: SANS, fontSize: 14,
    color: MUT, margin: 0,
  });

  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.55, y: 2.85, w: 8.9, h: 1.04, fill: { color: PANEL },
    line: { color: GRID, width: 1 }, rectRadius: 0.08,
  });
  s.addText("THE HEADLINE", {
    x: 0.8, y: 2.97, w: 4, h: 0.22, fontFace: SANS, fontSize: 8.5,
    bold: true, color: GOLD, charSpacing: 3, margin: 0,
  });
  s.addText("“Israel launches strikes on Iranian energy infrastructure. Iran threatens closure of the Strait of Hormuz.”", {
    x: 0.8, y: 3.2, w: 8.4, h: 0.58, fontFace: SANS, fontSize: 14,
    italic: true, color: TEXT, margin: 0,
  });

  s.addText([
    { text: "Deliverable   ", options: { color: DIM, fontSize: 10 } },
    { text: "1-week probability distributions for Brent M1-M2, M2-M4, M1-M6 — expected value, 50% and 90% ranges, scenario probabilities", options: { color: BODY, fontSize: 10 } },
  ], { x: 0.55, y: 4.18, w: 8.9, h: 0.32, fontFace: SANS, margin: 0 });
  s.addText([
    { text: "Method        ", options: { color: DIM, fontSize: 10 } },
    { text: "Historical event study (13 events, 2018-2025)  ·  scenario tree  ·  Monte Carlo mixture (200k draws)  ·  regime-conditional vol", options: { color: BODY, fontSize: 10 } },
  ], { x: 0.55, y: 4.48, w: 8.9, h: 0.32, fontFace: SANS, margin: 0 });

  s.addText(`Peruka Pranav  ·  Futures First internship  ·  data as of ${R.asof}`, {
    x: 0.55, y: 4.95, w: 8.9, h: 0.28, fontFace: SANS, fontSize: 10,
    color: MUT, margin: 0,
  });
  footer(s, 1);
}

/* ════════════════════════════ SLIDE 2 — FRAMEWORK ═══════════════════════ */
{
  const s = baseSlide();
  eyebrow(s, "Framework");
  title(s, "Four steps from headline to tradeable distribution");

  const steps = [
    ["1 · TYPE THE EVENT", "Severity-tier the headline against a 13-event catalogue (2018-2025). This one: kinetic strike on energy infrastructure (Tier 3) with a threatened Tier-4 escalation."],
    ["2 · MEASURE ANALOGS", "Event study: Δ spread over the 5 trading days after each event, from the last close before it. The June 2025 Israel-Iran war is the direct analog — it is in our data."],
    ["3 · BUILD SCENARIOS", "Four exhaustive outcomes for the week, probabilities anchored to historical escalation frequency + structural arguments. Each gets a per-spread conditional (μ, σ)."],
    ["4 · MIX & SIMULATE", "Monte Carlo: draw scenario, then spread changes with one-factor correlation (ρ = 0.84 measured). 200k draws → EV, 50%, 90% intervals per spread."],
  ];
  steps.forEach((st, i) => {
    const x = 0.55 + i * 2.31;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x, y: 1.5, w: 2.16, h: 2.42, fill: { color: PANEL },
      line: { color: GRID, width: 1 }, rectRadius: 0.07,
    });
    s.addText(st[0], {
      x: x + 0.13, y: 1.64, w: 1.9, h: 0.42, fontFace: SANS, fontSize: 10,
      bold: true, color: GOLD, margin: 0,
    });
    s.addText(st[1], {
      x: x + 0.13, y: 2.1, w: 1.9, h: 1.72, fontFace: SANS, fontSize: 9,
      color: BODY, margin: 0, lineSpacingMultiple: 1.12,
    });
  });

  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.55, y: 4.18, w: 8.9, h: 0.82, fill: { color: "143024" },
    line: { color: GREEN, width: 1 }, rectRadius: 0.07,
  });
  s.addText([
    { text: "PRINCIPLE   ", options: { bold: true, color: GREEN, fontSize: 9.5, charSpacing: 2 } },
    { text: "The objective is not a point forecast. A geopolitical shock is a mixture of regimes with very different outcomes — the honest answer is the whole distribution, with the scenario weights stated so they can be argued with.", options: { color: TEXT, fontSize: 10.5 } },
  ], { x: 0.8, y: 4.32, w: 8.4, h: 0.56, fontFace: SANS, margin: 0 });
  footer(s, 2);
}

/* ═══════════════════ SLIDE 3 — TRANSMISSION + CURRENT STATE ═════════════ */
{
  const s = baseSlide();
  eyebrow(s, "Mechanism");
  title(s, "How a supply threat prices into the futures curve", 0.62, 23);

  const rows = [
    ["Prompt scarcity premium", "Physical barrels at risk are near-dated. Buyers pay up for prompt delivery → M1 rallies vs deferred → backwardation steepens, front spreads widen first."],
    ["Belly repricing", "If the outage is expected to PERSIST, the 2-6 month curve reprices too. Abqaiq 2019: M2-M4 moved +0.69 while M1-M2 moved only +0.07 — SPR-release expectations cap the prompt."],
    ["Freight, insurance & routing", "War-risk premia on Hormuz transits push landed costs up and slow flows even with the strait open — a tax on prompt supply."],
    ["Demand offsets & releases", "Strategic reserve releases and demand destruction act with a lag — they cap the FRONT more than the belly, skewing event risk toward M2-M4 / M1-M6."],
  ];
  rows.forEach((r, i) => {
    const y = 1.42 + i * 0.78;
    s.addText(r[0], {
      x: 0.55, y, w: 2.5, h: 0.7, fontFace: SANS, fontSize: 11, bold: true,
      color: GOLD_L, margin: 0,
    });
    s.addText(r[1], {
      x: 3.15, y, w: 3.45, h: 0.76, fontFace: SANS, fontSize: 9,
      color: BODY, margin: 0, lineSpacingMultiple: 1.08,
    });
  });

  // current state panel
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 6.85, y: 1.42, w: 2.6, h: 3.06, fill: { color: PANEL },
    line: { color: GRID, width: 1 }, rectRadius: 0.08,
  });
  s.addText("STARTING CONDITIONS", {
    x: 7.03, y: 1.56, w: 2.3, h: 0.22, fontFace: SANS, fontSize: 8.5,
    bold: true, color: GOLD, charSpacing: 2, margin: 0,
  });
  s.addText([
    { text: "Regime  ", options: { color: DIM, fontSize: 9 } },
    { text: "BACK / LOW / STRESSED", options: { color: RED, fontSize: 9.5, bold: true, breakLine: true } },
    { text: "backwardation + storage deficit + stressed vol (PULSE classifier)", options: { color: MUT, fontSize: 8 } },
  ], { x: 7.03, y: 1.82, w: 2.3, h: 0.72, fontFace: SANS, margin: 0 });
  const lvl = R.current_levels;
  s.addText([
    { text: `M1-M2   ${lvl.m1_m2.toFixed(2)}`, options: { color: GOLD_L, breakLine: true } },
    { text: `M2-M4   ${lvl.m2_m4.toFixed(2)}`, options: { color: CYAN, breakLine: true } },
    { text: `M1-M6  ${lvl.m1_m6.toFixed(2)}`, options: { color: GREEN } },
  ], { x: 7.03, y: 2.62, w: 2.3, h: 0.84, fontFace: MONO, fontSize: 12.5, bold: true, margin: 0 });
  s.addText("Base is already STRETCHED: M1-M2 at 2.91 vs 10-yr p99 of 5.22. The geopolitical premium partially priced → de-escalation has real downside.", {
    x: 7.03, y: 3.52, w: 2.3, h: 0.9, fontFace: SANS, fontSize: 8.2,
    color: MUT, margin: 0, lineSpacingMultiple: 1.1,
  });
  footer(s, 3);
}

/* ═══════════════════════ SLIDE 4 — EVENT STUDY ══════════════════════════ */
{
  const s = baseSlide();
  eyebrow(s, "Step 1-2 · Historical evidence");
  title(s, "13 supply-threat events, measured 5-day spread response", 0.62, 21);
  s.addImage({ path: path.join(CH, "chart_event_study.png"), x: 0.42, y: 1.18, w: 9.16, h: 3.36 });
  const chips = [
    ["Tier 1 — verbal / proxy", "JCPOA, drone, Soleimani, 2024 exchanges: ±0.0-0.3 — noise", MUT],
    ["Tier 2-3 — kinetic on infra", "Abqaiq: belly +0.7 to +1.2 · June 2025 war: +0.6 / +1.2 / +2.5", GOLD_L],
    ["Tier 4 — supply war", "Russia 2022: +1.1 / +3.3 / +6.5 — observed ceiling for one week", RED],
  ];
  chips.forEach((c, i) => {
    const x = 0.55 + i * 3.05;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x, y: 4.62, w: 2.9, h: 0.62, fill: { color: PANEL },
      line: { color: GRID, width: 1 }, rectRadius: 0.06,
    });
    s.addText([
      { text: c[0], options: { bold: true, color: c[2], fontSize: 8.6, breakLine: true } },
      { text: c[1], options: { color: BODY, fontSize: 8.2 } },
    ], { x: x + 0.12, y: 4.69, w: 2.66, h: 0.5, fontFace: SANS, margin: 0 });
  });
  footer(s, 4);
}

/* ═══════════════════════ SLIDE 5 — JUNE 2025 ANALOG ═════════════════════ */
{
  const s = baseSlide();
  eyebrow(s, "The direct analog");
  title(s, "June 2025: the same headline, watched day by day", 0.62, 22);
  s.addImage({ path: path.join(CH, "chart_june2025.png"), x: 0.42, y: 1.18, w: 9.16, h: 3.6 });
  s.addText([
    { text: "What it teaches:  ", options: { bold: true, color: GOLD, fontSize: 10 } },
    { text: "(1) spreads spike within 2-4 sessions while strikes continue — D+5 deltas were +0.61 / +1.19 / +2.48;  (2) the premium COLLAPSES on ceasefire — M1-M2 gave back 0.57 in one session;  (3) the week-end outcome is therefore binary-ish around the ceasefire question → exactly why we model a scenario mixture.", options: { color: BODY, fontSize: 10 } },
  ], { x: 0.55, y: 4.78, w: 8.9, h: 0.62, fontFace: SANS, margin: 0, lineSpacingMultiple: 1.05 });
  footer(s, 5);
}

/* ═══════════════════════ SLIDE 6 — SCENARIO TREE ════════════════════════ */
{
  const s = baseSlide();
  eyebrow(s, "Step 3 · Scenarios");
  title(s, "Four outcomes for the week — probabilities you can argue with", 0.62, 21);
  s.addImage({ path: path.join(CH, "chart_scenarios.png"), x: 0.42, y: 1.14, w: 7.0, h: 2.77 });

  const rats = [
    ["30%", "De-escalation", "June 2025 reached ceasefire in 8 trading days; symbolic-response precedent (Apr & Oct 2024)"],
    ["40%", "Sustained, Hormuz open", "Base case: strikes continue, shipping flows — the June-2025 D+5 state"],
    ["22%", "Partial disruption", "Tanker War 1984-88 precedent: harassment, mining, seizures — flows impaired, not stopped"],
    ["8%", "Closure attempt", "Never observed in 40 yrs. Iran exports 1.5-1.7 mb/d through Hormuz itself — self-deterrence + US 5th Fleet"],
  ];
  rats.forEach((r, i) => {
    const y = 1.14 + i * 0.72;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: 7.55, y, w: 1.95, h: 0.64, fill: { color: PANEL },
      line: { color: GRID, width: 1 }, rectRadius: 0.06,
    });
    s.addText([
      { text: `${r[0]}  ${r[1]}`, options: { bold: true, color: GOLD_L, fontSize: 8.4, breakLine: true } },
      { text: r[2], options: { color: MUT, fontSize: 6.9 } },
    ], { x: 7.65, y: y + 0.05, w: 1.78, h: 0.56, fontFace: SANS, margin: 0, lineSpacingMultiple: 1.0 });
  });

  s.addText([
    { text: "Parameterisation:  ", options: { bold: true, color: GOLD, fontSize: 9.5 } },
    { text: "scenario means anchored to measured event deltas (S2 = June-2025 verbatim; S3 = 2.5× Abqaiq; S4 = 1.2× Russia-2022 + lognormal right tail). σ floors at BACK-regime weekly vol (1.02 / 1.23 / 2.71) — a scenario never claims more precision than baseline regime noise. De-escalation mean is tilted NEGATIVE (-0.48 / -0.63 / -1.29): the stretched base unwinds, as on 2025-06-23.", options: { color: BODY, fontSize: 9.5 } },
  ], { x: 0.55, y: 4.1, w: 8.9, h: 0.95, fontFace: SANS, margin: 0, lineSpacingMultiple: 1.1 });
  footer(s, 6);
}

/* ═══════════════ SLIDES 7-9 — PER-SPREAD RESULTS ════════════════════════ */
const READS = {
  m1_m2: "The coin-flip of the three: P(widen) only 55% — the stretched 2.91 base unwinds hardest on de-escalation; fat right tail through 5.0 if Hormuz is touched.",
  m2_m4: "The cleanest event signal: P(widen) 65%. Infrastructure damage reprices 2-4 month supply with no SPR offset — the Abqaiq lesson.",
  m1_m6: "Biggest absolute range (90%: 8.2 - 23.9) — where a closure attempt is most visible: the S4 conditional mean alone is +7.8.",
};
["m1_m2", "m2_m4", "m1_m6"].forEach((sp, i) => {
  const s = baseSlide();
  const st = ST[sp];
  eyebrow(s, `Step 4 · Results ${i + 1} of 3`);
  title(s, `${LBL[sp]} — one-week distribution`, 0.62, 23);

  s.addImage({ path: path.join(CH, `chart_dist_${sp}.png`), x: 0.42, y: 1.3, w: 6.35, h: 3.04 });

  const px = 7.0, pw = 2.5;
  statBox(s, px, 1.30, pw, "Current level", st.current.toFixed(2), `as of ${R.asof}`, TEXT);
  statBox(s, px, 2.32, pw, "Expected value (1 wk)", `${st.ev_level.toFixed(2)}`, `Δ ${st.ev_delta >= 0 ? "+" : ""}${st.ev_delta.toFixed(2)} $/bbl`, SPREAD_HEX[sp]);
  statBox(s, px, 3.34, pw, "P(spread widens)", `${(st.p_widen * 100).toFixed(0)}%`, "share of 200k draws above 0", st.p_widen > 0.6 ? GREEN : GOLD_L);

  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: 0.42, y: 4.42, w: 9.16, h: 0.46, fill: { color: PANEL },
    line: { color: GRID, width: 1 }, rectRadius: 0.06,
  });
  s.addText([
    { text: `50% range  `, options: { color: DIM, fontSize: 9.5 } },
    { text: `${st.ci50_level[0].toFixed(2)} – ${st.ci50_level[1].toFixed(2)}`, options: { color: SPREAD_HEX[sp], fontSize: 11.5, bold: true, fontFace: MONO } },
    { text: `      90% range  `, options: { color: DIM, fontSize: 9.5 } },
    { text: `${st.ci90_level[0].toFixed(2)} – ${st.ci90_level[1].toFixed(2)}`, options: { color: SPREAD_HEX[sp], fontSize: 11.5, bold: true, fontFace: MONO } },
    { text: `      ($/bbl, spread LEVEL)`, options: { color: DIM, fontSize: 8.5 } },
  ], { x: 0.62, y: 4.48, w: 8.8, h: 0.34, fontFace: SANS, margin: 0 });

  s.addText(READS[sp], {
    x: 0.55, y: 4.94, w: 8.9, h: 0.3, fontFace: SANS, fontSize: 9,
    color: BODY, italic: true, margin: 0,
  });
  footer(s, 7 + i);
});

/* ═══════════════════ SLIDE 10 — SUMMARY + CAVEATS ═══════════════════════ */
{
  const s = baseSlide();
  eyebrow(s, "Summary");
  title(s, "The answer, on one slide", 0.62, 24);

  const head = [
    { text: "SPREAD", options: { fill: { color: PANEL }, color: MUT, bold: true } },
    { text: "NOW", options: { fill: { color: PANEL }, color: MUT, bold: true } },
    { text: "EV (1 WK)", options: { fill: { color: PANEL }, color: MUT, bold: true } },
    { text: "50% RANGE", options: { fill: { color: PANEL }, color: MUT, bold: true } },
    { text: "90% RANGE", options: { fill: { color: PANEL }, color: MUT, bold: true } },
    { text: "P(WIDEN)", options: { fill: { color: PANEL }, color: MUT, bold: true } },
  ];
  const rows = [head];
  ["m1_m2", "m2_m4", "m1_m6"].forEach((sp) => {
    const st = ST[sp];
    rows.push([
      { text: LBL[sp], options: { color: SPREAD_HEX[sp], bold: true } },
      { text: st.current.toFixed(2), options: { color: BODY } },
      { text: `${st.ev_level.toFixed(2)} (${st.ev_delta >= 0 ? "+" : ""}${st.ev_delta.toFixed(2)})`, options: { color: TEXT, bold: true } },
      { text: `${st.ci50_level[0].toFixed(2)} – ${st.ci50_level[1].toFixed(2)}`, options: { color: BODY } },
      { text: `${st.ci90_level[0].toFixed(2)} – ${st.ci90_level[1].toFixed(2)}`, options: { color: BODY } },
      { text: `${(st.p_widen * 100).toFixed(0)}%`, options: { color: st.p_widen > 0.6 ? GREEN : GOLD_L, bold: true } },
    ]);
  });
  s.addTable(rows, {
    x: 0.55, y: 1.3, w: 8.9, rowH: 0.36, fontFace: MONO, fontSize: 10.5,
    border: { pt: 0.75, color: GRID }, fill: { color: "0F1525" },
    valign: "middle", margin: 0.06,
  });

  s.addText("HONEST CAVEATS", {
    x: 0.55, y: 3.18, w: 4.3, h: 0.26, fontFace: SANS, fontSize: 10,
    bold: true, color: GOLD, charSpacing: 2, margin: 0,
  });
  s.addText([
    { text: "n=13 events, one Tier-4 — the closure tail is judgment anchored on Russia-2022, not estimated", options: { bullet: true, breakLine: true } },
    { text: "Base levels already stretched (p97+): symmetric vol assumptions understate downside on de-escalation", options: { bullet: true, breakLine: true } },
    { text: "Scenario probabilities are priors — built to be argued with, then re-run in seconds", options: { bullet: true, breakLine: true } },
    { text: "One-factor ρ=0.84 understates tail co-movement; spreads decouple in squeezes", options: { bullet: true } },
  ], { x: 0.55, y: 3.46, w: 4.35, h: 1.7, fontFace: SANS, fontSize: 8.8, color: BODY, margin: 0, lineSpacingMultiple: 1.12 });

  s.addText("WHAT WOULD RE-WEIGHT THE SCENARIOS", {
    x: 5.15, y: 3.18, w: 4.3, h: 0.26, fontFace: SANS, fontSize: 10,
    bold: true, color: CYAN, charSpacing: 2, margin: 0,
  });
  s.addText([
    { text: "Tanker war-risk insurance quotes (first to move on real Hormuz risk)", options: { bullet: true, breakLine: true } },
    { text: "Iranian export loadings at Kharg Island (satellite-tracked)", options: { bullet: true, breakLine: true } },
    { text: "US carrier-group positioning + ceasefire backchannel headlines", options: { bullet: true, breakLine: true } },
    { text: "Framework runs live in PULSE: event → tier → mixture → distribution, refreshed daily against the regime classifier", options: { bullet: true } },
  ], { x: 5.15, y: 3.46, w: 4.35, h: 1.7, fontFace: SANS, fontSize: 8.8, color: BODY, margin: 0, lineSpacingMultiple: 1.12 });

  footer(s, 10);
}

pres.writeFile({ fileName: OUT }).then(() => {
  console.log("wrote", OUT);
});
