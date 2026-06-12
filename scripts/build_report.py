"""
Build docs/PULSE_phase1_phase2_report.html — self-contained file with embedded
base64 screenshots, dashboard-matched dark theme. Phase 1 heavy; 9 mentor
evaluation dimensions woven through the narrative.
"""
from __future__ import annotations
import base64
from pathlib import Path

ROOT = Path(__file__).parent.parent
SHOTS = ROOT / "docs" / "screenshots"
OUT = ROOT / "docs" / "PULSE_phase1_phase2_report.html"

LIVE_URL = "https://jacket-army-appointed-racing.trycloudflare.com"


def img(name: str) -> str:
    p = SHOTS / name
    if not p.exists():
        return ""
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


CSS = r"""
*, *::before, *::after { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
    background: #0B0F1A;
    color: #E2E8F0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Inter", Roboto,
                 "Helvetica Neue", Arial, sans-serif;
    font-size: 15px;
    line-height: 1.65;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}
.mono { font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, "Courier New", monospace; }
.wrap { max-width: 1180px; margin: 0 auto; padding: 0 32px; }

/* ────────────────────────────────────────────────  HERO  ──── */
.hero {
    background: radial-gradient(ellipse at top left, #1E293B 0%, #0B0F1A 60%);
    border-bottom: 1px solid #1E293B;
    padding: 80px 0 60px;
    position: relative;
    overflow: hidden;
}
.hero::before {
    content: "";
    position: absolute;
    top: -100px; right: -100px;
    width: 460px; height: 460px;
    background: radial-gradient(circle, rgba(245, 166, 35, 0.12) 0%, transparent 70%);
    pointer-events: none;
}
.brand {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-bottom: 32px;
}
.brand-mark {
    width: 44px; height: 44px;
    border-radius: 10px;
    background: linear-gradient(135deg, #F5A623 0%, #D97706 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    color: #0B0F1A;
    font-weight: 900;
    font-size: 22px;
    letter-spacing: -0.5px;
    box-shadow: 0 4px 24px rgba(245, 166, 35, 0.3);
}
.brand-name {
    font-weight: 800;
    font-size: 18px;
    letter-spacing: 4px;
    color: #F8FAFC;
}
.brand-tag {
    font-size: 11px;
    color: #64748B;
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-top: 2px;
}
.hero h1 {
    font-size: 56px;
    line-height: 1.05;
    margin: 0 0 16px;
    font-weight: 800;
    letter-spacing: -1.5px;
    color: #F8FAFC;
}
.hero h1 .accent { color: #F5A623; }
.hero p.lede {
    font-size: 19px;
    color: #94A3B8;
    max-width: 760px;
    line-height: 1.55;
    margin: 0 0 36px;
}
.hero-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 14px;
    margin-top: 32px;
}
.pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 14px;
    border-radius: 999px;
    background: rgba(30, 41, 59, 0.6);
    border: 1px solid #334155;
    font-size: 12px;
    color: #CBD5E1;
    letter-spacing: 0.5px;
}
.pill.live { border-color: #10B981; color: #6EE7B7; }
.pill.live .dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: #10B981;
    box-shadow: 0 0 8px #10B981;
}
.pill.gold { border-color: #F5A623; color: #FCD34D; }

/* ────────────────────────────────────────────────  SECTIONS  ──── */
section { padding: 80px 0; border-bottom: 1px solid #131A2A; }
section.tight { padding: 56px 0; }
.eyebrow {
    font-size: 11px;
    letter-spacing: 4px;
    text-transform: uppercase;
    color: #F5A623;
    font-weight: 700;
    margin-bottom: 12px;
}
h2 {
    font-size: 38px;
    margin: 0 0 18px;
    font-weight: 800;
    letter-spacing: -0.8px;
    color: #F8FAFC;
    line-height: 1.15;
}
h3 {
    font-size: 23px;
    margin: 56px 0 14px;
    font-weight: 700;
    color: #F8FAFC;
    letter-spacing: -0.3px;
    line-height: 1.3;
}
h3:first-child { margin-top: 24px; }
h4 {
    font-size: 13px;
    margin: 28px 0 10px;
    font-weight: 700;
    color: #F5A623;
    letter-spacing: 2px;
    text-transform: uppercase;
}
.section-lede {
    font-size: 17px;
    color: #94A3B8;
    max-width: 820px;
    line-height: 1.55;
    margin: 0 0 24px;
}
p { margin: 0 0 14px; color: #CBD5E1; max-width: 820px; }
p.wide { max-width: none; }
strong { color: #F8FAFC; font-weight: 700; }
em { color: #FCD34D; font-style: normal; font-weight: 600; }
code {
    font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
    font-size: 13px;
    background: #1E293B;
    padding: 1px 6px;
    border-radius: 4px;
    color: #FCD34D;
    border: 1px solid #334155;
}
a { color: #FCD34D; text-decoration: none; border-bottom: 1px dashed rgba(245, 166, 35, 0.5); transition: all .15s; }
a:hover { color: #FDE68A; border-bottom-color: #FDE68A; }

/* ────────────────────────────────────────────────  STAT STRIP  ──── */
.stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 18px;
    margin: 44px 0 0;
}
.stat {
    background: linear-gradient(180deg, #131A2A 0%, #0F1525 100%);
    border: 1px solid #1E293B;
    border-radius: 12px;
    padding: 24px 20px;
}
.stat .num {
    font-family: "JetBrains Mono", monospace;
    font-size: 38px;
    font-weight: 800;
    color: #F5A623;
    line-height: 1;
    letter-spacing: -1px;
    margin-bottom: 8px;
}
.stat .num.green { color: #10B981; }
.stat .num.cyan  { color: #22D3EE; }
.stat .num.white { color: #F8FAFC; }
.stat .lab {
    font-size: 11px;
    color: #64748B;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    font-weight: 600;
}
.stat .sub {
    font-size: 12px;
    color: #94A3B8;
    margin-top: 6px;
    line-height: 1.4;
}

/* ────────────────────────────────────────────────  TWO-COL  ──── */
.cols-2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 30px;
    margin: 28px 0;
    align-items: start;
}
.cols-3 {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 18px;
    margin: 28px 0;
}
.card {
    background: linear-gradient(180deg, #131A2A 0%, #0F1525 100%);
    border: 1px solid #1E293B;
    border-radius: 12px;
    padding: 24px;
}
.card h4 { margin-top: 0; }
.card p { font-size: 14px; line-height: 1.55; }

/* ────────────────────────────────────────────────  TABLE  ──── */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 18px 0;
    font-size: 14px;
}
thead th {
    text-align: left;
    padding: 12px 14px;
    color: #94A3B8;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    border-bottom: 1px solid #1E293B;
    background: #0F1525;
}
tbody td {
    padding: 12px 14px;
    border-bottom: 1px solid #131A2A;
    color: #CBD5E1;
    font-family: "JetBrains Mono", monospace;
    font-size: 13.5px;
}
tbody td.text { font-family: inherit; }
tbody tr:last-child td { border-bottom: 0; }
tbody td.win  { color: #6EE7B7; font-weight: 700; }
tbody td.loss { color: #FCA5A5; }
tbody td.gold { color: #FCD34D; font-weight: 700; }

/* ────────────────────────────────────────────────  SCREENSHOT  ──── */
.shot {
    margin: 24px 0 8px;
    border: 1px solid #1E293B;
    border-radius: 14px;
    overflow: hidden;
    background: #0F1525;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(245, 166, 35, 0.06);
}
.shot img { width: 100%; display: block; }
.shot-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 18px;
    margin: 24px 0 8px;
}
.shot-row .shot { margin: 0; }
.caption {
    font-size: 12.5px;
    color: #64748B;
    margin: 10px 0 0;
    line-height: 1.55;
    font-style: italic;
}
.caption strong { color: #94A3B8; font-style: normal; }
.caption + h3 { margin-top: 56px; }

/* ────────────────────────────────────────────────  CALLOUT  ──── */
.callout {
    background: linear-gradient(135deg, rgba(245, 166, 35, 0.08) 0%, rgba(245, 166, 35, 0.02) 100%);
    border: 1px solid rgba(245, 166, 35, 0.3);
    border-radius: 12px;
    padding: 22px 26px;
    margin: 28px 0;
}
.callout .lab {
    font-size: 11px;
    color: #F5A623;
    letter-spacing: 2px;
    text-transform: uppercase;
    font-weight: 700;
    margin-bottom: 8px;
}
.callout p { color: #E2E8F0; font-size: 15px; margin: 0; line-height: 1.6; max-width: none; }
.callout.green {
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.08) 0%, rgba(16, 185, 129, 0.02) 100%);
    border-color: rgba(16, 185, 129, 0.3);
}
.callout.green .lab { color: #10B981; }
.callout.cyan {
    background: linear-gradient(135deg, rgba(34, 211, 238, 0.07) 0%, rgba(34, 211, 238, 0.02) 100%);
    border-color: rgba(34, 211, 238, 0.3);
}
.callout.cyan .lab { color: #22D3EE; }

/* ────────────────────────────────────────────────  STREAM GRID  ──── */
.stream-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 10px;
    margin: 24px 0;
}
.stream {
    background: #131A2A;
    border: 1px solid #1E293B;
    border-radius: 8px;
    padding: 12px 14px;
}
.stream .dot {
    display: inline-block;
    width: 7px; height: 7px;
    border-radius: 50%;
    background: #10B981;
    box-shadow: 0 0 6px rgba(16, 185, 129, 0.7);
    margin-right: 6px;
    vertical-align: middle;
}
.stream .dot.model { background: #F5A623; box-shadow: 0 0 6px rgba(245, 166, 35, 0.7); }
.stream .dot.cache { background: #60A5FA; box-shadow: 0 0 6px rgba(96, 165, 250, 0.7); }
.stream .name {
    font-size: 12px;
    color: #E2E8F0;
    font-weight: 600;
    display: inline-block;
    vertical-align: middle;
}
.stream .src {
    font-size: 10.5px;
    color: #64748B;
    margin-top: 4px;
    font-family: "JetBrains Mono", monospace;
}

/* ────────────────────────────────────────────────  PIPELINE  ──── */
.pipe {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 8px;
    margin: 24px 0;
    align-items: stretch;
}
.pipe-step {
    background: #131A2A;
    border: 1px solid #1E293B;
    border-radius: 8px;
    padding: 16px 14px;
    position: relative;
}
.pipe-step .num {
    font-family: "JetBrains Mono", monospace;
    font-size: 10px;
    color: #475569;
    font-weight: 700;
    letter-spacing: 1px;
    margin-bottom: 6px;
}
.pipe-step .h {
    font-size: 12px;
    color: #F5A623;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
    margin-bottom: 6px;
}
.pipe-step .d {
    font-size: 11.5px;
    color: #94A3B8;
    line-height: 1.45;
}

/* ────────────────────────────────────────────────  THEME TAG  ──── */
.theme-tag {
    display: inline-block;
    padding: 3px 9px;
    border-radius: 4px;
    background: rgba(34, 211, 238, 0.1);
    border: 1px solid rgba(34, 211, 238, 0.3);
    color: #67E8F9;
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-left: 10px;
    vertical-align: middle;
}

/* ────────────────────────────────────────────────  LIVE URL  ──── */
.live-url-card {
    background: linear-gradient(135deg, rgba(245, 166, 35, 0.10) 0%, rgba(245, 166, 35, 0.03) 100%);
    border: 1px solid rgba(245, 166, 35, 0.4);
    border-radius: 14px;
    padding: 28px 30px;
    margin: 28px 0;
    text-align: center;
}
.live-url-card .lab {
    font-size: 11px;
    color: #F5A623;
    letter-spacing: 3px;
    text-transform: uppercase;
    font-weight: 700;
    margin-bottom: 14px;
}
.live-url-card a.url {
    display: inline-block;
    font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
    font-size: 19px;
    color: #FCD34D;
    word-break: break-all;
    border-bottom: 2px solid rgba(252, 211, 77, 0.4);
    padding: 6px 4px;
    font-weight: 700;
    transition: all .15s;
}
.live-url-card a.url:hover {
    color: #FEF3C7;
    border-bottom-color: #FEF3C7;
    background: rgba(245, 166, 35, 0.06);
}

/* ────────────────────────────────────────────────  FOOTER  ──── */
footer {
    background: #0F1525;
    padding: 48px 0;
    border-top: 1px solid #1E293B;
}
footer p {
    color: #64748B;
    font-size: 13px;
    margin: 0 0 4px;
    max-width: none;
}

ul { margin: 8px 0 14px; padding-left: 22px; max-width: 820px; }
ul li { margin-bottom: 6px; color: #CBD5E1; }

/* ────────────────────────────────────────────────  PRINT  ──── */
@media print {
    body { background: #fff; color: #000; }
    section { break-inside: avoid; }
    .hero { background: #0B0F1A; color: #F8FAFC; }
    .shot { box-shadow: none; break-inside: avoid; }
}
"""


def html() -> str:
    S = {
        "signal":    img("01_signal.png"),
        "charts":    img("02_charts.png"),
        "fwdcurve":  img("02b_forward_curve.png"),
        "season":    img("02c_seasonality.png"),
        "cracks":    img("02d_cracks_4.png"),
        "fund":      img("03_fundamentals.png"),
        "intel":     img("04_intelligence.png"),
        "spreads":   img("05_spreads.png"),
        "paper":     img("06_paper.png"),
        "regime":    img("07_regime.png"),
        "drill":     img("09_regime_drill.png"),
        "askpulse":  img("10_ask_pulse.png"),
        "squawk":    img("11_squawk.png"),
    }

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PULSE — Phase 1 + Phase 2 Report</title>
<style>{CSS}</style>
</head>
<body>

<!-- ═══════════════════════════════════════════════════════════════════  HERO  ══ -->
<header class="hero">
  <div class="wrap">
    <div class="brand">
      <div class="brand-mark">P</div>
      <div>
        <div class="brand-name">PULSE</div>
        <div class="brand-tag">Energy Intelligence Terminal</div>
      </div>
    </div>
    <h1>The energy desk's full operating&nbsp;picture,<br>built ground-up in <span class="accent">10 weeks.</span></h1>
    <p class="lede">
      35 named data sources stitched into one cohesive workspace · a 9-indicator directional
      signal engine that tells you <em>why</em> the market is moving · seasonal &amp; refining
      lenses on every relevant spread · a regime-conditional research stack with a 7-model
      per-cell competition · and a live A/B harness comparing two production strategies on
      real paper books. One dashboard, two phases, one operator.
    </p>
    <div class="hero-meta">
      <span class="pill live"><span class="dot"></span>LIVE DEMO</span>
      <span class="pill gold">FUTURES FIRST INTERNSHIP</span>
      <span class="pill">JUNE 2026</span>
      <span class="pill mono">v2.8.6-followup</span>
    </div>
  </div>
</header>

<!-- ════════════════════════════════════════════════════  EXECUTIVE SUMMARY  ══ -->
<section>
  <div class="wrap">
    <div class="eyebrow">What you're looking at</div>
    <h2>An institutional terminal that <em>also</em> happens to be a quant lab.</h2>
    <p class="section-lede">
      Most energy dashboards do one thing — show prices, or list news, or display a single
      analyst signal. PULSE was built to be the workspace that sits underneath an analyst's
      desk for the whole trading day. <strong>Phase&nbsp;1</strong> wires together 35 live
      data streams across prices, fundamentals, news, weather, term&nbsp;structure, macro
      and options into one provenance-tracked dashboard with a directional signal engine
      and a paper-trading sandbox. <strong>Phase&nbsp;2</strong> layers a quantitative
      research stack on top: a 27-cell composite regime classifier, a 7-model competition
      per (spread, regime) cell, a 10-fold walk-forward with realistic transaction&nbsp;costs,
      and a live A/B harness validating two competing production strategies.
    </p>
    <div class="stats">
      <div class="stat">
        <div class="num">35</div>
        <div class="lab">Live Data Streams</div>
        <div class="sub">prices, curve, news, macro, vol, fundamentals — every panel cites its source</div>
      </div>
      <div class="stat">
        <div class="num">22</div>
        <div class="lab">Predictive Features</div>
        <div class="sub">curve shape, COT 156w pct, inv surprise, real rate, OVX/VIX, cracks</div>
      </div>
      <div class="stat">
        <div class="num green">14.6 y</div>
        <div class="lab">Historical Backbone</div>
        <div class="sub">Brent C1-C31 daily settlements · 5y+ 1-minute mids · 12y COT &amp; EIA</div>
      </div>
      <div class="stat">
        <div class="num cyan">+0.351</div>
        <div class="lab">NET Sharpe (Pooled)</div>
        <div class="sub">walk-forward 2024–26 · beats baseline NET by +0.05 · A/B running</div>
      </div>
    </div>
  </div>
</section>

<!-- ═══════════════════════════════════════════════════════════  PHASE 1  ══ -->
<section>
  <div class="wrap">
    <div class="eyebrow">Phase 1 · Shipped 2026-06-05 · PR #2 (5,699 LoC)</div>
    <h2>The terminal foundation — designed so the question
    "<em>why is the market moving today?</em>" has one answer per panel, not five tabs of
    isolated charts.</h2>
    <p class="section-lede">
      Before we could run regressions on regime-conditional spreads, the desk needed a working
      terminal. The brief was deliberate: one dashboard that has to <em>cohere</em>. Every
      panel here was built so the analyst can trace any number back to its raw source in one
      click, and so the workspace as a whole stays loaded across a full trading day without
      a single isolated dataset that doesn't link back to the others.
    </p>

    <!-- ─────────────────────────────  THEME: WHY IS THE MARKET MOVING TODAY?  ── -->
    <h3>The Signal tab — the headline view, decomposed into its drivers
      <span class="theme-tag">Theme · Why is the market moving today?</span>
    </h3>
    <p>
      The Signal tab is purpose-built to answer one question: <em>given everything we know,
      what is the market actually doing, and which forces are dominant?</em> Three product
      cards — Brent, WTI, Henry&nbsp;Hub — each show a composite score on
      <code>[−2, +2]</code> with a directional label (BULLISH / STRONGLY BULLISH / BEARISH /
      etc.), live spot, intraday sparkline, and a <strong>9-indicator decomposition</strong>
      that breaks the score into Inventory, Curve, COT positioning, Fair Value, Sentiment,
      Technicals, DXY, Implied&nbsp;Vol, and Geopolitical risk. Each indicator gets its own
      score and a one-line plain-English reason — so the question "<em>which factor flipped
      us bullish?</em>" is answered without leaving the screen.
    </p>

    <div class="shot"><img alt="Signal tab — Phase 1 hero" src="{S['signal']}"></div>
    <p class="caption">
      <strong>Signal tab.</strong> Three product cards (Brent BULLISH, WTI BULLISH, Henry&nbsp;Hub
      STRONGLY BULLISH) with 9-indicator decompositions. Bottom strip: the Brent Price
      Decomposition with live spot vs model fair value vs 1-week target.
    </p>

    <h3>The 9-indicator weighted signal engine — the math behind the BULLISH label</h3>
    <div class="cols-2">
      <div class="card">
        <h4>Crude weighting (Brent &amp; WTI)</h4>
        <table>
          <tbody>
            <tr><td class="text">Inventory</td><td class="gold" style="text-align:right">28 %</td></tr>
            <tr><td class="text">Curve</td><td class="gold" style="text-align:right">24 %</td></tr>
            <tr><td class="text">COT positioning</td><td class="gold" style="text-align:right">19 %</td></tr>
            <tr><td class="text">Fair value gap</td><td style="text-align:right">14 %</td></tr>
            <tr><td class="text">News sentiment</td><td style="text-align:right">5 %</td></tr>
            <tr><td class="text">Technicals</td><td style="text-align:right">5 %</td></tr>
            <tr><td class="text">DXY</td><td style="text-align:right">3 %</td></tr>
            <tr><td class="text">Implied vol (OVX)</td><td style="text-align:right">2 %</td></tr>
          </tbody>
        </table>
      </div>
      <div class="card">
        <h4>Henry Hub weighting</h4>
        <table>
          <tbody>
            <tr><td class="text">Inventory</td><td class="gold" style="text-align:right">30 %</td></tr>
            <tr><td class="text">Weather (HDD/CDD)</td><td class="gold" style="text-align:right">25 %</td></tr>
            <tr><td class="text">Curve</td><td style="text-align:right">15 %</td></tr>
            <tr><td class="text">COT positioning</td><td style="text-align:right">15 %</td></tr>
            <tr><td class="text">Fair value</td><td style="text-align:right">10 %</td></tr>
            <tr><td class="text">Technicals</td><td style="text-align:right">5 %</td></tr>
          </tbody>
        </table>
      </div>
    </div>
    <p>
      Weights are hand-set "expert priors" calibrated against historical regimes. Conviction
      tags fire on agreement: HIGH when ≥5/9 indicators align, MODERATE when ≥3, else LOW.
      Phase&nbsp;2 evaluates whether data-driven, per-regime weights can beat these priors —
      that's the next-natural extension of the same engine.
    </p>

    <!-- ────────────────────────────  THEME: LINK THE INFORMATION TOGETHER  ── -->
    <h3>Charts — intraday OHLCV with EMA overlays, forward curve, and 1-day evolution
      <span class="theme-tag">Theme · Linking information together</span>
    </h3>
    <p>
      The Charts tab is where the analyst goes to verify a signal. OHLCV candles for the
      Brent front contract with EMA20/50 overlays and volume bars, the live forward curve
      M1–M9 for Brent vs WTI, and a curve-evolution panel that overlays today's curve
      against a cached 1-day-prior snapshot with a contract-by-contract delta. The
      BACKWARDATION tag the engine prints on the right is its own structural read of the
      curve shape.
    </p>
    <div class="shot"><img alt="Charts tab — OHLCV + forward curve" src="{S['charts']}"></div>
    <p class="caption">
      <strong>Charts tab · top.</strong> Brent intraday 5-minute OHLCV with EMA20 (cyan
      line) and a volume histogram below; the live forward curve M1–M9 (Brent in gold,
      WTI in cyan); and a forward-curve evolution panel showing how each contract moved
      relative to a 1-day-prior cached snapshot. The BACKWARDATION tag is the engine's
      own structural read.
    </p>

    <h3>Seasonality lens — 5 products, 5-year average monthly returns</h3>
    <p>
      Seasonality matters more in energy than in any other asset class — gasoline-summer,
      heating-oil-winter, natural-gas-cooling-demand — and PULSE surfaces it as a first-class
      view rather than a derived report. The chart below plots the 5-year average monthly
      return for Brent, WTI, Nat&nbsp;Gas, RBOB and Heating&nbsp;Oil with the current month
      highlighted; the status strip beneath gives the prevailing direction for each product
      (TAILWIND / HEADWIND / NEUTRAL) for the calendar week.
    </p>
    <div class="shot"><img alt="Seasonality — 5 products" src="{S['season']}"></div>
    <p class="caption">
      <strong>Seasonality · 5 products.</strong> 5-year average monthly returns for the
      core energy complex; the current month is the gold dashed vertical. Below: per-product
      status — today Brent <em>NEUTRAL</em>, WTI <em>TAILWIND</em>, Nat&nbsp;Gas
      <em>HEADWIND</em>, RBOB <em>HEADWIND</em>, Heating&nbsp;Oil <em>TAILWIND</em>.
    </p>

    <h3>Refining-margin lens — RBOB-HO, 3-2-1, gasoline crack, distillate crack</h3>
    <p>
      The four refining spreads that matter on a US desk, all on one screen with their
      1-year context and a current-vs-z highlight. RBOB&nbsp;−&nbsp;Heating&nbsp;Oil is the
      gasoline-over-distillate premium that signals refinery yield shifts. The 3-2-1 crack
      is the canonical US refining margin proxy
      ((2×RBOB + 1×HO − 3×WTI) / 3). The gasoline and distillate cracks separate the two
      unit-margin components so the analyst can see which product is driving strength.
    </p>
    <div class="shot"><img alt="4 crack spread charts" src="{S['cracks']}"></div>
    <p class="caption">
      <strong>Charts · refining lens.</strong> All four crack spreads visible in one frame —
      RBOB&nbsp;−&nbsp;HO (gasoline premium over distillate), the 3-2-1 blended crack
      (canonical US refining margin), Gasoline crack (RBOB&nbsp;−&nbsp;WTI) and
      Distillate crack (HO&nbsp;−&nbsp;WTI). 1-year ranges with current readings on the
      left of each card.
    </p>

    <!-- ─────────────────────────────  THEME: FUNDAMENTALS &amp; SURPRISE  ── -->
    <h3>Fundamentals — the alpha is in the surprise, not the level</h3>
    <p>
      Phase&nbsp;1 deliberately surfaces inventory data as a <strong>surprise</strong>
      (actual minus 4-week trailing baseline) rather than the raw weekly level — because the
      market mostly prices in the consensus. The EIA Surprise tracker shows the last 10
      releases with actual, expected, surprise, and 1-bar price reaction, plus a regression
      scatter at the bottom that gives a per-release coefficient.
    </p>
    <div class="shot"><img alt="Fundamentals tab" src="{S['fund']}"></div>
    <p class="caption">
      <strong>Fundamentals tab — EIA Surprise tracker.</strong> Every Wednesday at 10:30 ET
      the EIA publishes weekly crude stocks; PULSE tracks the surprise and the realised
      1-bar price reaction. The bottom scatter is the regression of one against the other —
      a strong negative slope says <em>bigger draws → bigger rallies</em>, which is the prior
      we expect. The next release countdown sits top-right.
    </p>

    <!-- ────────────────────────────────  THEME: NEWS, FLOW, PATTERN  ── -->
    <h3>Intelligence — news with sentiment, correlations, and pattern memory
      <span class="theme-tag">Theme · Why is the market moving today?</span>
    </h3>
    <p>
      Three views in one tab. <strong>Energy News + FinBERT</strong> on the left ranks the most
      sentiment-significant articles from GDELT&nbsp;2.0, NewsAPI, and MarketAux feeds; each
      headline carries a numerical sentiment score from a fine-tuned FinBERT transformer.
      The <strong>cross-asset correlation matrix</strong> top-right is a 30-day rolling
      Pearson over CL / NG / RBOB / HO / SPX — the heatmap colour gives the analyst the macro
      regime read at a glance. Bottom-left: stumpy matrix-profile pattern recognition over
      <em>14.6 years</em> of Brent — when today's 14-day window is close to a historical
      analog, it surfaces here with the realised forward return of the historical match.
    </p>
    <div class="shot"><img alt="Intelligence tab" src="{S['intel']}"></div>
    <p class="caption">
      <strong>Intelligence tab.</strong> FinBERT-tagged news with sentiment colour (red bearish,
      green bullish), 30-day cross-asset correlation matrix CL/NG/RBOB/HO/SPX, and stumpy
      pattern-recognition over 14.6y of Brent.
    </p>

    <!-- ─────────────────────────────  THEME: SPREADS — BRIDGE TO PHASE 2  ── -->
    <h3>Spreads &amp; Curve — the bridge from prices to relative-value
      <span class="theme-tag">Theme · Linking information together</span>
    </h3>
    <p>
      Spreads is where the analyst goes before deciding a calendar trade is worth pushing to
      paper. Calendar ladder M1-M2 through M11-M12 for Brent and WTI with the spread
      differential; the <strong>EIA STEO global oil balance</strong> table showing forward
      supply / demand / inventory build forecast for the next 12 months;
      <strong>cross-product correlation matrix</strong> over Brent / WTI / RBOB / HO / NG to
      give a refined-vs-crude regime read; and a plain-English curve-structure interpretation
      at the bottom-right.
    </p>
    <div class="shot"><img alt="Spreads & Curve tab" src="{S['spreads']}"></div>
    <p class="caption">
      <strong>Spreads &amp; Curve tab.</strong> Calendar spread ladder (Brent and WTI),
      EIA STEO global supply / demand / balance, term-structure correlation matrix, and a
      plain-English regime read at the bottom-right. This is the screen the analyst uses to
      <em>decide</em> a spread idea; Phase&nbsp;2 then tells them which spread.
    </p>

    <!-- ─────────────────────────────  THEME: PAPER BOOK — PROOF IT WORKS  ── -->
    <h3>Paper trading sandbox — the single tab that proves the system works
      <span class="theme-tag">Theme · Linking information together</span>
    </h3>
    <p>
      Every Trade-Idea push writes a row to <code>paper_trades</code> with entry / target /
      stop / fair&nbsp;value. An APScheduler MTM job refreshes the live mark every 60&nbsp;s;
      TP/SL auto-closes when hit. The Performance panel shows win rate, annualised Sharpe
      (√252), max drawdown, profit factor, and an equity curve. Phase&nbsp;2 extended this
      with a <code>paper_legs</code> table — a SHORT&nbsp;M3-M6 push records as one parent
      row plus <em>SHORT&nbsp;C3</em> + <em>LONG&nbsp;C6</em> leg rows, so the audit trail
      shows what's actually held at the outright level.
    </p>
    <div class="shot"><img alt="Paper trading tab" src="{S['paper']}"></div>
    <p class="caption">
      <strong>Paper trading tab.</strong> 12 open positions, 1 closed, +$15.50 realised PnL,
      100 % win rate so far. The suggested-trade card up top is the Phase&nbsp;1 directional
      Brent signal (BACKWARDATION + tight curve + BULLISH composite, LONG). Open positions
      table shows spreads with indented leg rows — e.g. <code>BRENT_M3_M6 SHORT</code> ↳
      <code>C3 SHORT</code> + <code>C6 LONG</code> with per-leg entry / MTM / unrealised PnL.
    </p>

    <!-- ─────────────────────────  THEME: COMPLETENESS — THE 35 STREAMS  ── -->
    <h3>The 35 active data streams
      <span class="theme-tag">Theme · Coverage &amp; completeness</span>
    </h3>
    <p>
      Below is the live roster, grouped by SLA tier. The top-bar health pill renders this
      live; click it for the per-stream drill modal.
    </p>
    <div class="stream-grid">
      <div class="stream"><span class="dot"></span><span class="name">Brent prices</span><div class="src">yfinance · 60s TTL</div></div>
      <div class="stream"><span class="dot"></span><span class="name">WTI prices</span><div class="src">yfinance · 60s TTL</div></div>
      <div class="stream"><span class="dot"></span><span class="name">Henry Hub</span><div class="src">yfinance · 60s TTL</div></div>
      <div class="stream"><span class="dot"></span><span class="name">OHLCV intraday</span><div class="src">yfinance · 60s TTL</div></div>
      <div class="stream"><span class="dot cache"></span><span class="name">Brent C1-C31</span><div class="src">/Data settle CSV</div></div>
      <div class="stream"><span class="dot"></span><span class="name">Forward curve</span><div class="src">multi-source · 600s</div></div>
      <div class="stream"><span class="dot cache"></span><span class="name">Curve regime</span><div class="src">15y M1-M12 spread</div></div>
      <div class="stream"><span class="dot"></span><span class="name">EIA crude stocks</span><div class="src">EIA v2 weekly</div></div>
      <div class="stream"><span class="dot"></span><span class="name">EIA STEO</span><div class="src">EIA v2 monthly</div></div>
      <div class="stream"><span class="dot"></span><span class="name">EIA surprise</span><div class="src">computed Δ vs 4w MA</div></div>
      <div class="stream"><span class="dot"></span><span class="name">CFTC COT</span><div class="src">12y disagg history</div></div>
      <div class="stream"><span class="dot"></span><span class="name">OPEC reference</span><div class="src">static data</div></div>
      <div class="stream"><span class="dot"></span><span class="name">JODI-Oil</span><div class="src">monthly · 24h TTL</div></div>
      <div class="stream"><span class="dot"></span><span class="name">Rig count</span><div class="src">Baker Hughes</div></div>
      <div class="stream"><span class="dot"></span><span class="name">Weather (7 regions)</span><div class="src">Open-Meteo · 1h TTL</div></div>
      <div class="stream"><span class="dot model"></span><span class="name">Technicals</span><div class="src">5min EMA + RSI</div></div>
      <div class="stream"><span class="dot"></span><span class="name">Crack spreads</span><div class="src">RB/HO/CL computed</div></div>
      <div class="stream"><span class="dot"></span><span class="name">Seasonality (5y)</span><div class="src">same-week DOY</div></div>
      <div class="stream"><span class="dot"></span><span class="name">Macro (FRED)</span><div class="src">DXY · DGS10 · T5YIE</div></div>
      <div class="stream"><span class="dot"></span><span class="name">OVX (FRED)</span><div class="src">crude implied vol</div></div>
      <div class="stream"><span class="dot"></span><span class="name">ECB FX</span><div class="src">daily reference</div></div>
      <div class="stream"><span class="dot"></span><span class="name">News (NewsAPI)</span><div class="src">600s TTL</div></div>
      <div class="stream"><span class="dot"></span><span class="name">GDELT 2.0 tone</span><div class="src">global news tone</div></div>
      <div class="stream"><span class="dot"></span><span class="name">MarketAux news</span><div class="src">900s TTL</div></div>
      <div class="stream"><span class="dot model"></span><span class="name">FinBERT sentiment</span><div class="src">per-article</div></div>
      <div class="stream"><span class="dot"></span><span class="name">RSS aggregator</span><div class="src">Reuters / Bloomberg</div></div>
      <div class="stream"><span class="dot"></span><span class="name">Analyst watch</span><div class="src">GDELT-filtered</div></div>
      <div class="stream"><span class="dot"></span><span class="name">Tanker watch</span><div class="src">aisstream.io live</div></div>
      <div class="stream"><span class="dot model"></span><span class="name">Geo risk score</span><div class="src">10 hotspots</div></div>
      <div class="stream"><span class="dot model"></span><span class="name">Pattern analogs</span><div class="src">stumpy MP 14.6y</div></div>
      <div class="stream"><span class="dot model"></span><span class="name">Realised vol</span><div class="src">1-min mid → 20d RV</div></div>
      <div class="stream"><span class="dot model"></span><span class="name">Order flow</span><div class="src">desk buy/sell volume</div></div>
      <div class="stream"><span class="dot model"></span><span class="name">Fair value model</span><div class="src">cost-of-carry + 4 adj</div></div>
      <div class="stream"><span class="dot model"></span><span class="name">Signal engine</span><div class="src">9-indicator composite</div></div>
      <div class="stream"><span class="dot model"></span><span class="name">Trade idea + brief</span><div class="src">Groq + local LLaMA</div></div>
    </div>
    <p class="caption" style="margin-top: 10px;">
      <span style="display:inline-flex;align-items:center;gap:6px;margin-right:14px;"><span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#10B981;"></span> LIVE</span>
      <span style="display:inline-flex;align-items:center;gap:6px;margin-right:14px;"><span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#60A5FA;"></span> CACHED</span>
      <span style="display:inline-flex;align-items:center;gap:6px;"><span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#F5A623;"></span> MODEL</span>
    </p>

    <h3>Trade Idea pipeline</h3>
    <div class="pipe">
      <div class="pipe-step"><div class="num">STEP 1</div><div class="h">Score</div><div class="d">9-indicator weighted composite on [−2, +2]</div></div>
      <div class="pipe-step"><div class="num">STEP 2</div><div class="h">Direction</div><div class="d">LONG / SHORT / NEUTRAL gated by score AND fair-value gap</div></div>
      <div class="pipe-step"><div class="num">STEP 3</div><div class="h">Target &amp; Stop</div><div class="d">target = spot ± 0.5×gap · stop = spot ∓ 1.5×ATR</div></div>
      <div class="pipe-step"><div class="num">STEP 4</div><div class="h">Thesis</div><div class="d">top 3 indicators by |weight × score| in plain English</div></div>
      <div class="pipe-step"><div class="num">STEP 5</div><div class="h">Brief</div><div class="d">Groq LLaMA → local LLaMA → rule-based fallback</div></div>
    </div>

    <h3>Engineering hygiene — quiet wins that show up in every panel
      <span class="theme-tag">Theme · Quality &amp; reliability</span>
    </h3>
    <div class="cols-3">
      <div class="card">
        <h4>DuckDB + Parquet lake</h4>
        <p>The 3.5 GB /Data folder was converted to columnar Parquet with ZSTD compression.
        <strong>10× faster cold queries, 130× warm, ~6.5:1 compression.</strong> One
        <code>duckdb_conn()</code> registers every source as a SQL view.</p>
      </div>
      <div class="card">
        <h4>Pydantic typed contracts</h4>
        <p>All production endpoints pinned to Pydantic&nbsp;v2 models with auto-generated
        TypeScript types. <strong>38 interfaces</strong> shared between Flask and React.
        The "wrong shape" bug class is dead.</p>
      </div>
      <div class="card">
        <h4>Sentry + Better Stack</h4>
        <p>Errors flow to Sentry from both Flask and React. Structured logs stream to
        Better Stack. Every <code>safe_fetch()</code> swallow is captured with a tag so
        silent failures leave a trail.</p>
      </div>
    </div>
    <p style="margin-top: 16px;">
      Every panel also displays its data source as a <code>SourceTag</code> chip — a green
      LIVE pill, blue CACHED, gold MODEL, amber for ESTIMATE, red for HARDCODED. Click the
      shield icon top-right and the full 35-entry source ledger opens as a searchable modal.
      The top-bar health pill classifies all 34 streams as <code>up / stale / down</code>
      with per-stream age and TTL.
    </p>

    <!-- ─────────────────────  COMPLEMENTARY FEATURES — SQUAWK + ASK PULSE  ── -->
    <h3>Complementary — news squawk and Ask&nbsp;PULSE</h3>
    <p>
      Two features make the dashboard feel <em>alive</em> rather than static during a long
      trading session, and both are accessible from any tab. The <strong>news squawk</strong>
      reads breaking-tape headlines aloud the moment they cross the wire — a chime followed
      by a spoken summary via the browser's Web Speech API; the <em>Replay News</em> button
      on every tab replays the most recent breaking item, or the most-negative FinBERT-tagged
      article if no breaking item exists.
    </p>
    <p>
      <strong>Ask&nbsp;PULSE</strong> — the retrieval-augmented chat dock floating
      bottom-right — answers free-form questions about the current state of the market using
      a <strong>local LLaMA</strong> model grounded in the dashboard's own live data (curve,
      fundamentals, OHLCV, signal score, news headlines) with a Groq LLaMA-3.3-70B fallback
      when on the network. Click the gold button at bottom-right (or press <code>/</code>)
      to open, then either pick one of the curated starter questions or type your own.
    </p>
    <div class="shot-row">
      <div class="shot"><img alt="News squawk close-up" src="{S['squawk']}"></div>
      <div class="shot"><img alt="Ask PULSE chat dock" src="{S['askpulse']}"></div>
    </div>
    <p class="caption">
      <strong>Left — News squawk &amp; provenance bar.</strong> The pill
      <code>33/34 · 1 STALE</code> summarises live-stream health; the shield icon opens the
      35-entry provenance ledger; <em>Replay&nbsp;News</em> reads the latest breaking item
      aloud. <strong>Right — Ask&nbsp;PULSE.</strong> Local LLaMA RAG chat with curated
      starter questions ("Why is Brent moving today?", "Explain backwardation vs contango",
      "What does the 3-2-1 crack tell me about today's setup?"). Type free-form below.
    </p>
  </div>
</section>

<!-- ═══════════════════════════════════════════════════════════  PHASE 2  ══ -->
<section style="background: #0F1525;">
  <div class="wrap">
    <div class="eyebrow">Phase 2 · Live · v2.8.6-followup</div>
    <h2>From "<em>what's the market doing?</em>" to "<em>what should I trade given the regime?</em>"</h2>
    <p class="section-lede">
      Phase&nbsp;1 answered the directional question for outrights. Phase&nbsp;2 answers the
      harder relative-value question for spreads &amp; butterflies, under the explicit
      hypothesis that the same spread behaves differently depending on the prevailing market
      regime — and that conditioning on regime should beat regime-unaware mean-reversion.
      The Phase&nbsp;2 stack is built directly on Phase&nbsp;1's data lake; nothing here
      needed a new data source, only smarter use of what was already wired in.
    </p>

    <div class="shot"><img alt="Regime tab — Phase 2 hero" src="{S['regime']}"></div>
    <p class="caption">
      <strong>Regime tab — the Phase 2 hero.</strong> Today's composite regime is
      <code>BACK / LOW / STRESSED</code> (backwardation + storage deficit + stressed vol).
      Top pick: <strong>BUY Brent front fly</strong>, current −$0.07 vs fair $0.56,
      z = −3.85 σ, confidence 96 %. Winner-model: XGBoost (19/19 features active). Below is
      the live A/B paper-test panel comparing pooled vs gated arms.
    </p>

    <h3>The 27-cell composite regime grid</h3>
    <p>
      Three axes, each cut into three buckets with economically defensible hard thresholds.
      Composite label format is <code>CURVE / INV / VOL</code>. 66 of 162 (spread × regime)
      cells are populated with ≥30 historical observations; the empty cells are economically
      implausible (BACK × HIGH, CONTANGO × LOW) and stay empty by design rather than fitting
      noise.
    </p>
    <table>
      <thead>
        <tr><th>Axis</th><th>Buckets</th><th>Threshold</th><th>Source</th></tr>
      </thead>
      <tbody>
        <tr><td class="text"><strong>Curve</strong> (M1–M12)</td><td class="text">CONTANGO / NEUTRAL / BACK</td><td>≤ −$2 / −$2..+$5 / &gt; +$5</td><td class="text">Brent settle</td></tr>
        <tr><td class="text"><strong>Inventory</strong> (US crude)</td><td class="text">LOW / AVG / HIGH</td><td>≤ −4 % / ±4 % / &gt; +4 %</td><td class="text">EIA WCRSTUS1 vs 5y</td></tr>
        <tr><td class="text"><strong>Realised Vol</strong> (20 d)</td><td class="text">CALM / NORMAL / STRESSED</td><td>≤ 20 % / 20–35 % / &gt; 35 %</td><td class="text">Brent C1 1-min mids</td></tr>
      </tbody>
    </table>

    <h3>Per-cell 7-model competition</h3>
    <p>
      For each (spread, regime) cell, seven candidate models compete: <strong>Ridge, Lasso,
      ElasticNet, Huber</strong> (linear baseline) and <strong>XGBoost, LightGBM,
      CatBoost</strong> (boosters). Selection by 5-fold <code>TimeSeriesSplit</code> CV&nbsp;R²
      with a sparsity tiebreak that prefers linear models on ties &lt;0.005 (interpretability
      prior). Quantile p10 / p50 / p90 fit separately for confidence bands. Boosters gated by
      n_train ≥ 80 to avoid overfitting tiny cells.
    </p>

    <div class="shot"><img alt="Regime drill modal" src="{S['drill']}"></div>
    <p class="caption">
      <strong>Drill modal — receipts behind today's top pick.</strong> Scatter of actual vs
      model fair value for every historical day in today's regime; today's signal is the
      gold dot. Below: the three closest historical analogs (Euclidean over standardised
      features) with their <em>realised</em> 20-day forward spread change. The July 2022
      backwardation episode delivered −$0.50 to −$0.36 over 20 days — directly supporting
      the BUY signal today.
    </p>

    <h3>Walk-forward backtest with realistic transaction costs</h3>
    <p>
      The headline question — <em>does regime conditioning beat regime-unaware mean
      reversion?</em> — is answered by a 10-quarterly-refit walk-forward across 2024-2026
      against a 252-day rolling z-score baseline, with Phase 2.8.6 transaction costs
      ($0.030 / $0.040 / $0.050 round-trip per bbl for M1-M2 / M3-M6 / fly, derived from ICE
      exchange-published fees + half bid-ask slippage). Costs scale with sizing.
    </p>
    <table>
      <thead>
        <tr><th>Mode</th><th>Gross Sharpe</th><th>NET Sharpe</th><th>Hit Rate</th><th>Mean PnL/bbl</th><th>n signals</th></tr>
      </thead>
      <tbody>
        <tr><td class="text">Baseline 252d z</td><td>+0.385</td><td>+0.301</td><td>71.6 %</td><td>+$0.180</td><td>2,082</td></tr>
        <tr><td class="text"><strong>Pooled (un-gated)</strong></td><td class="win">+0.437</td><td class="win">+0.351</td><td>58.5 %</td><td>+$0.092</td><td>1,996</td></tr>
        <tr><td class="text">Gated blend (current prod)</td><td>+0.384</td><td>+0.297</td><td class="win">72.3 %</td><td>+$0.176</td><td>2,154</td></tr>
      </tbody>
    </table>

    <div class="callout green">
      <div class="lab">Honest finding</div>
      <p>
        The gated blend, designed to be conservative, <em>ties</em> baseline NET
        (+0.297 vs +0.301). But the un-gated pooled engine — lifted by the Phase 2.8.1+2
        booster + alpha-feature expansion — <strong>beats baseline by +0.05 NET Sharpe</strong>.
        We don't flip the production default on a walk-forward result. We launched a live
        A/B harness instead.
      </p>
    </div>

    <h3>Live A/B harness — letting reality settle the argument</h3>
    <p>
      Parallel paper books. Each daily signal-generation tick produces both a pooled
      (un-gated) and a gated recommendation; both push to the same <code>paper_trades</code>
      table tagged with <code>ab_mode ∈ {{pooled, gated}}</code>. <strong>Stop criteria</strong>:
      minimum n_closed ≥ 30 per arm <em>AND</em> Welch t-test p &lt; 0.05 on per-trade NET PnL
      → declare winner; hard timeout at 14 calendar days → <code>undecided_timeout</code>.
      Dedup on <code>(asset, direction, ab_mode)</code> so persistent signals don't stack.
      The ABComparePanel polls every 30 s and renders verdict ribbon + per-arm KPIs +
      equity curves + difference panel.
    </p>

    <div class="callout cyan">
      <div class="lab">Live status · 2026-06-12</div>
      <p>
        Harness running since 2026-06-11. 4 trades opened per arm on day 1, 0 closed yet.
        Verdict ribbon: <code>UNDECIDED</code> with note "need ≥30 closed/arm". Expected
        verdict ~2026-06-25. If pooled wins, the production default flips with a one-line change.
      </p>
    </div>

    <h3>What the per-(spread × source) breakdown actually shows</h3>
    <p>
      Under the widened Phase 2.8.3 gate, the engine's <em>own</em> Sharpe — across the
      244 fires it owns — lifted to <strong>+0.888 gross / +0.806 NET</strong>. That's the
      slice the engine legitimately speaks on; the blended headline above is baseline-dominated
      by construction. Per-spread regime-leg breakdown:
    </p>
    <table>
      <thead>
        <tr><th>Spread</th><th>Regime-leg Sharpe (gross)</th><th>n fires</th><th>Hit rate</th><th>Note</th></tr>
      </thead>
      <tbody>
        <tr><td class="text">WTI fly (M1-2M2+M3)</td><td class="win">+1.499</td><td>95</td><td>75.8 %</td><td class="text">strongest cohort</td></tr>
        <tr><td class="text">WTI M3-M6</td><td class="win">+1.610</td><td>9</td><td>77.8 %</td><td class="text">small but clean</td></tr>
        <tr><td class="text">Brent fly (M1-2M2+M3)</td><td class="win">+0.956</td><td>85</td><td>61.2 %</td><td class="text">flagship pick today</td></tr>
        <tr><td class="text">Brent M1-M2</td><td>+0.292</td><td>51</td><td>62.7 %</td><td class="text">marginal</td></tr>
      </tbody>
    </table>
  </div>
</section>

<!-- ═══════════════════════════════════════════════════════════  ROADMAP  ══ -->
<section>
  <div class="wrap">
    <div class="eyebrow">Roadmap</div>
    <h2>What's next, and what would close the loop.</h2>
    <div class="cols-2">
      <div class="card">
        <h4>Phase 2 remaining (model side)</h4>
        <ul>
          <li><strong>2.8.4</strong> — Pool to one global model with regime-as-feature</li>
          <li><strong>2.8.5</strong> — Soft regime probabilities (replace hard thresholds)</li>
          <li><strong>2.8.7</strong> — Multi-horizon sweep (5 / 20 / 60 d) per spread</li>
          <li><strong>2.8.8</strong> — Extend walk-forward to 2018–2026 (contango coverage)</li>
          <li><strong>2.8.9</strong> — HMM / change-point regime detection</li>
          <li><strong>2.8.10</strong> — Portfolio-level vol targeting</li>
        </ul>
      </div>
      <div class="card">
        <h4>Phase 3 — production hardening</h4>
        <ul>
          <li>FastAPI migration (Flask → async I/O)</li>
          <li>Postgres + TimescaleDB for paper book &amp; signal history</li>
          <li>Redis + dependency-tracked cache invalidation</li>
          <li>WebSocket push (replace polling for prices/alerts/MTM)</li>
          <li>Docker + Cloudflare named-tunnel deploy + Access auth</li>
          <li>MLflow model tracking for the Phase 2 experiment grid</li>
        </ul>
      </div>
    </div>
  </div>
</section>

<!-- ═══════════════════════════════════════════════════════════  TRY IT  ══ -->
<section class="tight" style="background: #0F1525;">
  <div class="wrap">
    <div class="eyebrow">Try it now</div>
    <h2>Live demo, real data, no setup.</h2>
    <p style="font-size: 16px; line-height: 1.6;">
      The dashboard is exposed via a Cloudflare tunnel running from the office desk.
      Best in Chrome. Once you're in, press <code>8</code> to jump to the Regime tab — the
      A/B panel sits below the top-pick card. <code>1</code> through <code>7</code> map to
      the Phase&nbsp;1 tabs in order; press <code>/</code> or click the floating button at
      bottom-right to open Ask&nbsp;PULSE.
    </p>
    <div class="live-url-card">
      <div class="lab">Live URL — click to open</div>
      <a class="url" href="{LIVE_URL}" target="_blank" rel="noopener">{LIVE_URL}</a>
    </div>
    <p style="font-size: 13px; color: #64748B; line-height: 1.55; margin-top: 14px; max-width: none;">
      Notes — URL is currently a Cloudflare quick-tunnel and may change if the desk reboots.
      A named-tunnel upgrade with Cloudflare Access (email-gated auth) is pending an admin
      password from IT. Price feeds refresh every 60&nbsp;s; the A/B harness fires one tick
      per 24 h. If you'd rather wait for the stable URL with auth, drop a line and I'll send
      it the moment it's up.
    </p>
  </div>
</section>

<!-- ═══════════════════════════════════════════════════════════  FOOTER  ══ -->
<footer>
  <div class="wrap">
    <p><strong style="color:#94A3B8;">PULSE</strong> — Energy Intelligence Terminal · Futures First Internship · June 2026</p>
    <p>Built by Peruka Pranav · Flask 3 · React 18 · TypeScript · Tailwind · DuckDB · scikit-learn · XGBoost / LightGBM / CatBoost</p>
    <p>Methodology PDF: <code>backend/data/research/PULSE_methodology.pdf</code> · Project notes: <code>CLAUDE.md</code></p>
  </div>
</footer>

</body>
</html>
"""


def main() -> None:
    OUT.write_text(html(), encoding="utf-8")
    size_kb = OUT.stat().st_size // 1024
    print(f"wrote {OUT}  ({size_kb} KB)")


if __name__ == "__main__":
    main()
