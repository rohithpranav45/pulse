"""
Mentor-facing methodology PDF (Sprint 4 + Phase 2.5 + 2.6 + 2.7).

Page 1 — Methodology
  • Problem statement (regime-conditional fair value for crude spreads)
  • Universe + regime grids (composite 27-cell + pooled 3-cell curve-axis)
  • Feature set + model competition
  • Trading rule + horizon
  • Walk-forward evaluation design
  • Phase 2.6 gated blend (production rule)
  • Phase 2.7 sized blend (position sizing for the regime leg)

Page 2 — Results & Caveats
  • Walk-forward headline: composite / pooled / gated / baseline (Phase 2.6)
  • Phase 2.7 sized-blend comparison: gated full / half / kelly / baseline
  • Per-spread breakdown
  • Honest finding + caveats

Reads `walkforward_report.json` (combined: composite + pooled + gated +
sized + baseline). If sized_blend is absent (pre-Phase-2.7 report) the
sized section reports "not available".

Output: backend/data/research/PULSE_methodology.pdf
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes  import letter
from reportlab.lib.styles     import getSampleStyleSheet, ParagraphStyle
from reportlab.lib            import colors
from reportlab.lib.units      import inch
from reportlab.platypus       import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

log = logging.getLogger("pulse.research.methodology")

_RESEARCH_DIR = Path(__file__).parent.parent / "data" / "research"
_WF_REPORT    = _RESEARCH_DIR / "walkforward_report.json"
_BT_REPORT    = _RESEARCH_DIR / "backtest_report.json"
_OUT_PDF      = _RESEARCH_DIR / "PULSE_methodology.pdf"


# ─────────────────────────────────────────────────────────────────────────────
def _load(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _fmt(x, digits: int = 3) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:+.{digits}f}" if x else "0.000"
    return str(x)


def _fmt_pct(x) -> str:
    if x is None:
        return "—"
    return f"{x * 100:.1f}%"


def _style_table(t: Table, header_bg=colors.HexColor("#1f3a5a"), zebra=True):
    style = [
        ("BACKGROUND",    (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 8.5),
        ("FONTSIZE",      (0, 1), (-1, -1), 8),
        ("ALIGN",         (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN",         (0, 0), (0, -1),  "LEFT"),
        ("BOTTOMPADDING", (0, 0), (-1, 0),  5),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ("LINEBELOW",     (0, 0), (-1, 0),  0.8, colors.HexColor("#1f3a5a")),
        ("LINEBELOW",     (0, -1),(-1, -1), 0.4, colors.HexColor("#9aa9bf")),
    ]
    if zebra:
        for r in range(1, len(t._cellvalues), 2):
            style.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#eef2f7")))
    t.setStyle(TableStyle(style))


# ─────────────────────────────────────────────────────────────────────────────
def build_pdf(out_path: Path = _OUT_PDF) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    wf = _load(_WF_REPORT) or {}
    bt = _load(_BT_REPORT) or {}

    styles = getSampleStyleSheet()
    title  = ParagraphStyle("Title",   parent=styles["Title"],
                            fontSize=18, leading=22,
                            textColor=colors.HexColor("#0f1e36"))
    h2     = ParagraphStyle("H2",      parent=styles["Heading2"],
                            fontSize=10.5, leading=13, spaceBefore=5, spaceAfter=2,
                            textColor=colors.HexColor("#1f3a5a"))
    body   = ParagraphStyle("Body",    parent=styles["BodyText"],
                            fontSize=8.5, leading=11, spaceAfter=3)
    note   = ParagraphStyle("Note",    parent=body,
                            fontSize=7.5, leading=10, textColor=colors.HexColor("#5a6a83"))
    callout = ParagraphStyle("Callout", parent=body,
                            fontSize=9, leading=12, spaceBefore=3, spaceAfter=4,
                            backColor=colors.HexColor("#fff8e6"), borderColor=colors.HexColor("#e8b94a"),
                            borderWidth=0.5, borderPadding=4, leftIndent=2, rightIndent=2)

    doc = SimpleDocTemplate(
        str(out_path), pagesize=letter,
        leftMargin=0.50 * inch, rightMargin=0.50 * inch,
        topMargin=0.40 * inch, bottomMargin=0.35 * inch,
        title="PULSE — Regime-Conditional Spread Engine",
        author="PULSE",
    )

    story = []

    # ── PAGE 1 — METHODOLOGY ───────────────────────────────────────────────
    story += [
        Paragraph("PULSE — Regime-Conditional Crude Spread Engine", title),
        Paragraph(
            f"Methodology &amp; Walk-Forward Results · "
            f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} · "
            f"Reproduce: <font face='Courier'>python -m backend.research.walkforward</font> · "
            f"<font face='Courier'>python -m backend.research.methodology_pdf</font>",
            note,
        ),
        Spacer(1, 6),

        Paragraph("1. Problem", h2),
        Paragraph(
            "Identify when crude calendar spreads (front carry, mid-curve carry, "
            "front butterfly) deviate from their <i>regime-conditional</i> fair "
            "value. Output a single ranked opportunity per day with full receipts: "
            "fair, 80% band, residual z-score, top drivers, historical analogs.",
            body,
        ),

        Paragraph("2. Universe", h2),
        Paragraph(
            "<b>6 instruments</b> &mdash; 3 Brent (M1-M2, M3-M6, front fly "
            "M1-2&times;M2+M3) + 3 WTI mirror instruments. Brent legs from /Data "
            "C1-C31 daily settlements (2016-2026, 2,712 trading days). WTI legs "
            "from synthesised daily settlements (last 1-min mid per session, "
            "2021-2026, 1,676 trading days &mdash; flagged ESTIMATE pending the "
            "real exchange file).",
            body,
        ),

        Paragraph("3. Regime grids — composite + pooled", h2),
        Paragraph(
            "<b>Composite (Sprint 3)</b>: 27 cells = <b>CURVE</b> {CONTANGO / "
            "NEUTRAL / BACK on Brent M1-M12 at -$2, +$5} × <b>INVENTORY</b> "
            "{LOW / AVG / HIGH on US crude stocks vs 5y seasonal at ±4%} × "
            "<b>VOL</b> {CALM / NORMAL / STRESSED on Brent 20d realised vol "
            "at 20%, 35%}. Hard thresholds &mdash; mentor can answer "
            "&lsquo;why this regime?&rsquo; in one line. ~10-15 cells/spread "
            "have usable n; the rest are economically implausible.",
            body,
        ),
        Paragraph(
            "<b>Pooled (Phase 2.5)</b>: 3 cells/spread = curve axis only "
            "{CONTANGO / NEUTRAL / BACK}. Same thresholds; inventory + vol "
            "still surface on the UI as regime context but no longer "
            "fragment the training set. Average ~770 rows per cell (vs "
            "~150 composite) — explicitly addresses the Sprint 4 finding "
            "that per-cell data was too thin to beat a 252-d rolling z.",
            body,
        ),

        Paragraph("4. Feature set (Phase 2.8.2 expansion)", h2),
        Paragraph(
            "<b>20 Brent features</b> per cell (was 11): "
            "<i>Curve shape</i> &mdash; M1-M12, its square, and <b>curvature</b> "
            "(M1 &minus; 2&times;M6 + M12) for fly-specific information. "
            "<i>Front state</i> &mdash; Brent close + 5d return + 20d realised vol. "
            "<i>Inventory</i> &mdash; US crude vs 5y seasonal AND <b>inventory "
            "surprise</b> (weekly &Delta; minus its 4-week MA). "
            "<i>Seasonality</i> &mdash; sin/cos of day-of-year. "
            "<i>Lagged spreads</i> &mdash; M1-M2 / M3-M6 / fly lag-1.",
            body,
        ),
        Paragraph(
            "<b>Phase 2.8.2 alpha features</b> (new) &mdash; <b>COT managed-money "
            "percentile</b> (rolling 156-week, contrarian crowding), <b>3-2-1 "
            "crack</b> + <b>gasoline crack</b> (refining-margin pressure on the "
            "front), <b>WTI-Brent spread</b> (Atlantic-basin arb), <b>real rate</b> "
            "(DGS10 &minus; 5y TIPS breakeven; storage-cost driver), <b>OVX/VIX "
            "ratio</b> (crude vs equity vol risk-premium), and <b>days to "
            "front-month expiry</b>. WTI cells append 5 more (WTI close, M1-M12, "
            "3 lag-1 spreads). The target spread's own lag is removed to "
            "avoid self-leakage.",
            body,
        ),

        Paragraph("5. Per-cell model competition", h2),
        Paragraph(
            "We <i>do not</i> pick a single regression family a priori. For "
            "each (spread, regime) cell, <b>seven candidates</b> compete on 5-fold "
            "TimeSeriesSplit cross-validated R² (Phase 2.8.1 expansion):",
            body,
        ),
        Paragraph(
            "<b>Linear:</b> Ridge (shrinks coefficients — good with correlated "
            "predictors), Lasso (zeroes out noise features — good when 3-4 "
            "signals dominate), ElasticNet (L1+L2 blend — mixed correlation), "
            "Huber (robust loss — COVID-2020 / Russia-2022 outliers).",
            body,
        ),
        Paragraph(
            "<b>Gradient boosting (Phase 2.8.1):</b> XGBoost, LightGBM, "
            "CatBoost — shallow trees with strong regularisation that capture "
            "non-linear interactions between features. Win in cells where "
            "linear leaves alpha on the table.",
            body,
        ),
        Paragraph(
            "Winner = max mean CV R², simplicity tiebreak within 0.005: linear "
            "families rank above boosters (ElasticNet &gt; Lasso &gt; Ridge &gt; "
            "Huber &gt; XGBoost &gt; LightGBM &gt; CatBoost), so interpretability "
            "wins when CV scores are close. Quantile regressors (p10/p50/p90) "
            "are fit separately for the 80% confidence band.",
            body,
        ),

        Paragraph("6. Trading rule", h2),
        Paragraph(
            "At each daily settle: classify today's composite regime → look up "
            "winner model for (spread, regime) → predict fair, p10, p50, p90 → "
            "z = (actual − fair) / residual_σ from training. Direction = SELL "
            "if z &gt; +0.5σ, BUY if z &lt; −0.5σ, else NEUTRAL. Target = p50 "
            "(mean reversion). Stop = entry ± 1.5σ. Horizon = 20 trading days.",
            body,
        ),

        Paragraph("7. Walk-forward design", h2),
        Paragraph(
            f"Refits every quarter from 2024-Q1 through 2026-Q2 "
            f"({len(wf.get('composite', {}).get('refits', wf.get('refits', []))) } refits). "
            f"Each refit re-runs the full 4-model competition on data "
            f"≤ cutoff, then we walk forward day-by-day to the next cutoff, "
            f"generating signals. <b>Phase 2.5 runs BOTH grids in parallel</b> "
            f"(composite + pooled) over the same refit dates and the same "
            f"trading rule, then compares each to a regime-<i>unaware</i> "
            f"252-day rolling z-score baseline — isolating the contribution "
            f"of regime conditioning and of grid resolution.",
            body,
        ),

        Paragraph("8. Phase 2.6 — gated blend (production rule)", h2),
        Paragraph(
            "Phase 2.5 surfaced the BACK × {Lasso, Huber} slice as the only "
            "(spread × regime × winner) subset where the pooled engine "
            "demonstrably beats baseline in walk-forward. <b>Phase 2.6 codifies "
            "that finding as a production rule</b> and tests it as a third leg "
            "alongside composite / pooled / baseline. For each (date, spread):"
            " (i) if the pooled candidate has <i>regime_pooled='BACK'</i>, "
            "<i>winner_model</i> ∈ {Lasso, Huber}, AND <i>|z|</i> ≥ 0.5σ → "
            "take the pooled signal; (ii) else fall back to the 252-day "
            "rolling-z baseline. This routing is the exact rule shipped under "
            "<code>PULSE_GATED_BLEND=1</code>, so the table on page 2 measures "
            "the strategy a trader would actually run.",
            body,
        ),

        Paragraph("9. Phase 2.7 — position sizing for the regime leg", h2),
        Paragraph(
            "Phase 2.6 left max drawdown on the gated blend at &minus;271 "
            "(vs &minus;169 baseline) — the cost of concentrating 97 high-Sharpe "
            "regime fires on a small number of days. <b>Phase 2.7 scales the "
            "regime-leg notional</b> while leaving the baseline leg at 1.0, "
            "asking whether sizing compresses the DD without giving up the "
            "+1.332 regime-leg Sharpe. Three modes simulated end-to-end as a "
            "fourth walk-forward leg behind <code>PULSE_GATED_SIZE=&lt;mode&gt;</code>:",
            body,
        ),
        Paragraph(
            "<b>full</b> — scale 1.0 (sanity check; identical to gated_blend). "
            "<b>half</b> — scale 0.5 (uniform risk reduction). "
            "<b>kelly</b> — per-spread Kelly fraction <i>f*</i> = p − (1−p)/b "
            "computed at each refit boundary from prior closed regime-leg PnLs "
            "(p = win rate, b = mean_win / |mean_loss|). Clamped to [0.10, 1.00]; "
            "defaults to 0.50 when fewer than 5 prior trades exist. The "
            "schedule is expanding-window so the per-spread sample grows over "
            "time. Live inference reads the per-spread Kelly at the latest "
            "refit boundary from <code>sized_blend_summary.kelly_per_spread_latest</code>.",
            body,
        ),

        Paragraph("10. Phase 2.8 &mdash; real model + real features", h2),
        Paragraph(
            "Phase 2.8.1 adds <b>XGBoost / LightGBM / CatBoost</b> to the per-cell "
            "competition so cells with non-linear interactions aren't forced to "
            "fit a linear model. Boosters fit only on cells with &ge;80 train "
            "rows (smaller samples can't reliably distinguish trees from linears "
            "via CV); shallow trees (depth 3-4) and low learning rate (0.05) "
            "keep them from memorising. Boosters rank below linears in the "
            "tiebreak so interpretability still wins on ties.",
            body,
        ),
        Paragraph(
            "Phase 2.8.2 nearly <b>doubles the feature set</b> (11 &rarr; 20 "
            "Brent features) with the alpha-bearing predictors documented in "
            "&sect;4: COT crowding, inventory surprise, curvature, refining "
            "cracks, real rate, OVX/VIX ratio, WTI-Brent arb, days-to-expiry. "
            "The aim is to give every model family &mdash; linear and tree "
            "&mdash; a richer set of predictors so the gated-blend Sharpe lifts "
            "by tightening the pooled BACK fair-value estimates the gate rule "
            "relies on.",
            body,
        ),
        Paragraph(
            "Phase 2.8.3 widened the gate to admit boosters "
            "(GATED_WINNERS = {Lasso, Huber, XGBoost, LightGBM, CatBoost}). "
            "The widened gate is methodologically correct &mdash; the regime "
            "leg&apos;s reported Sharpe lifted from +0.369 to <b>+0.888</b> across "
            "244 fires (was 71) &mdash; but the headline blended Sharpe stayed "
            "flat (+0.389 -> +0.384) because most of the newly-routed booster "
            "trades had baseline-z direction matching pooled-z direction. The "
            "widening REASSIGNS attribution rather than CREATING new alpha at "
            "the blended level.",
            body,
        ),

        Paragraph("11. Phase 2.8.6 &mdash; transaction costs", h2),
        Paragraph(
            "Every Sharpe/PnL number above is <b>gross</b> &mdash; per-trade "
            "transaction cost is not modelled by the walk-forward&apos;s "
            "spread-move PnL. Phase 2.8.6 layers a defensible cost model on "
            "top of the existing trade tape so the table on page 2 reports "
            "<b>NET (after-cost)</b> Sharpe alongside gross.",
            body,
        ),
        Paragraph(
            "<b>Cost model.</b> Per-leg, per-side: $0.0025/bbl commission + "
            "clearing + brokerage (~$2.45 per 1,000-bbl contract) + half "
            "bid-ask slippage ($0.0050/bbl for front M1/M2, $0.0075/bbl for "
            "deferred M3-M6). Round-trip cost = N legs &times; 2 sides &times; "
            "(commission + half-spread). That gives: <b>2-leg M1-M2 = $0.030/bbl "
            "RT, 2-leg M3-M6 = $0.040, 3-leg fly = $0.050</b>. Cost scales with "
            "<code>sizing_scale</code> on regime rows (half-sized regime trade "
            "= half the contracts = half the fees). NEUTRAL trades incur zero "
            "cost (no fill).",
            body,
        ),
        Paragraph(
            "Cost is applied at the aggregation step only &mdash; per-cell CV "
            "is on gross fair-value R&sup2;, so winner selection is unaffected "
            "and no retraining is required. Live inference does <i>not</i> "
            "subtract cost at entry; the cost-aware NET metric exists purely "
            "for backtest reporting.",
            body,
        ),

        PageBreak(),
    ]

    # ── PAGE 2 — RESULTS (composite/pooled/gated/sized/baseline) ──────────
    comp = wf.get("composite") or {}
    pool = wf.get("pooled") or {}
    gate = wf.get("gated_blend") or {}
    sized = wf.get("sized_blend") or {}
    sized_full  = sized.get("full")  or {}
    sized_half  = sized.get("half")  or {}
    sized_kelly = sized.get("kelly") or {}
    sized_summary = wf.get("sized_blend_summary") or {}
    base_overall = wf.get("baseline_overall") or {}

    co = comp.get("overall") or wf.get("overall") or {}  # fallback to legacy top-level
    po = pool.get("overall") or {}
    go = gate.get("overall") or {}
    sho = sized_half.get("overall")  or {}
    sko = sized_kelly.get("overall") or {}
    bo = base_overall

    n_refits = len(comp.get("refits") or wf.get("refits") or [])
    n_total  = comp.get("n_trades", wf.get("n_trades", 0))
    gate_counts = gate.get("gate_counts") or {}

    story += [
        Paragraph("Walk-forward results &mdash; 2024-2026", title),
        Paragraph(
            f"Refits: {n_refits} · Records/mode: {n_total:,} · "
            f"Horizon: 20 trading days · Universe: 6 spreads · "
            f"Composite grid: 27 cells · Pooled grid: 3 curve cells · "
            f"Gated blend (Phase 2.6): regime engine fires on BACK + {{Lasso,Huber}} + |z|≥0.5σ, else 252d z baseline "
            f"(regime/baseline split: {gate_counts.get('regime_fires', 0):,} / {gate_counts.get('baseline_fallback', 0):,}) · "
            f"Sized blend (Phase 2.7): regime-leg notional scaled by {{full=1.0, half=0.5, kelly=per-spread f*}}",
            note,
        ),
        Spacer(1, 6),

        Paragraph("Overall — composite / pooled / gated blend / baseline", h2),
    ]

    def _delta(x, y, d=2):
        if x is None or y is None:
            return "—"
        return _fmt(x - y, d)

    def _delta_pct(x, y):
        if x is None or y is None:
            return "—"
        return _fmt_pct(x - y)

    headline = Table([
        ["Metric",            "Composite (27)",                "Pooled (3)",                  "Gated blend",                 "Baseline 252d z",              "Δ gated vs base"],
        ["Signals fired",     str(co.get("n_signals") or 0),   str(po.get("n_signals") or 0), str(go.get("n_signals") or 0), str(bo.get("n_signals") or 0), "—"],
        ["Hit rate",          _fmt_pct(co.get("hit_rate")),    _fmt_pct(po.get("hit_rate")),  _fmt_pct(go.get("hit_rate")),  _fmt_pct(bo.get("hit_rate")),  _delta_pct(go.get("hit_rate"), bo.get("hit_rate"))],
        ["Mean PnL ($/bbl)",  _fmt(co.get("mean_pnl"), 3),     _fmt(po.get("mean_pnl"), 3),   _fmt(go.get("mean_pnl"), 3),   _fmt(bo.get("mean_pnl"), 3),   _delta(go.get("mean_pnl"), bo.get("mean_pnl"), 3)],
        ["Median PnL",        _fmt(co.get("median_pnl"), 3),   _fmt(po.get("median_pnl"), 3), _fmt(go.get("median_pnl"), 3), _fmt(bo.get("median_pnl"), 3),"—"],
        ["Total PnL",         _fmt(co.get("total_pnl"), 1),    _fmt(po.get("total_pnl"), 1),  _fmt(go.get("total_pnl"), 1),  _fmt(bo.get("total_pnl"), 1),  "—"],
        ["Sharpe (ann.)",     _fmt(co.get("sharpe"), 2),       _fmt(po.get("sharpe"), 2),     _fmt(go.get("sharpe"), 2),     _fmt(bo.get("sharpe"), 2),     _delta(go.get("sharpe"), bo.get("sharpe"), 2)],
        ["Max drawdown",      _fmt(co.get("max_drawdown"), 1), _fmt(po.get("max_drawdown"), 1), _fmt(go.get("max_drawdown"), 1), _fmt(bo.get("max_drawdown"), 1), "—"],
    ], colWidths=[1.18*inch, 1.05*inch, 0.95*inch, 1.05*inch, 1.1*inch, 1.1*inch])
    _style_table(headline)
    story.append(headline)
    story.append(Spacer(1, 8))

    # ── Honest finding callout (Phase 2.5 + 2.6) ──────────────────────────
    cs = co.get("sharpe");   ps = po.get("sharpe");   gs = go.get("sharpe");   bs = bo.get("sharpe")

    gated_beats_base    = (gs is not None and bs is not None and gs > bs)
    gated_beats_pool    = (gs is not None and ps is not None and gs > ps)
    gated_beats_comp    = (gs is not None and cs is not None and gs > cs)

    verdict_bits = []
    if cs is not None: verdict_bits.append(f"composite {cs:+.2f}")
    if ps is not None: verdict_bits.append(f"pooled {ps:+.2f}")
    if gs is not None: verdict_bits.append(f"<b>gated {gs:+.2f}</b>")
    if bs is not None: verdict_bits.append(f"baseline {bs:+.2f}")

    finding_lead = "<b>Phase 2.6 finding:</b> "
    if gated_beats_base:
        finding_lead += (
            "the gated blend <b>does</b> close the gap to baseline — gating the pooled "
            "engine on BACK + {Lasso,Huber} + |z|≥0.5σ keeps the slice where regime "
            "conditioning genuinely adds value and routes the rest to the rolling z. "
        )
    elif gated_beats_pool:
        finding_lead += (
            "gating improves on the un-gated pooled engine but doesn't quite close the "
            "gap to baseline at the headline. The gate removes the loss-making slices "
            "of the pooled grid; it can't manufacture lift the engine doesn't have. "
        )
    else:
        finding_lead += (
            "even the gated blend can't pull the headline above baseline — the BACK + "
            "{Lasso,Huber} slice was strong in Phase 2.5 but it didn't survive a clean "
            "walk-forward of the gating rule itself. "
        )
    finding_lead += f"Sharpe (ann.): {', '.join(verdict_bits)}. "

    gc = gate.get("gate_counts") or {}
    n_fire = gc.get("regime_fires") or 0
    n_fall = gc.get("baseline_fallback") or 0
    share  = gc.get("regime_share") or 0.0
    finding_lead += (
        f"Gate routing: {n_fire:,} regime fires / {n_fall:,} baseline fallbacks "
        f"({share * 100:.1f}% of records hit the engine)."
    )

    if gated_beats_base:
        next_line = (
            " <b>Recommend production on <code>PULSE_GATED_BLEND=1</code></b> "
            "and revisit the inventory + vol axes as features inside the pooled "
            "regression rather than as cell splits."
        )
    elif gated_beats_pool:
        next_line = (
            " Pre-flight gate is the right shape but the BACK + {Lasso,Huber} slice "
            "is too narrow to dominate the headline. Next: widen the gate carefully "
            "(add ElasticNet under stricter |z| thresholds, test by-spread gates)."
        )
    else:
        next_line = (
            " The gate doesn't beat baseline in walk-forward. Next: try a wider "
            "feature set inside the pooled regression (EIA inventory surprise, COT "
            "positioning, OVX, term-structure derivatives), or revisit gating "
            "criteria — the Phase 2.5 slice may have been window-specific."
        )

    story.append(Paragraph(finding_lead + next_line, callout))
    story.append(Spacer(1, 4))

    # ── Per-spread breakdown — composite / pooled / gated / baseline ─────
    story.append(Paragraph("Per-spread Sharpe — composite / pooled / gated / baseline (Δ vs baseline)", h2))
    rows = [["Spread", "Comp Shp", "Pool Shp", "Gate Sig", "Gate Shp", "Base Shp", "Δ Gate"]]
    base_by_spread = wf.get("baseline_by_spread") or {}
    comp_by = comp.get("by_spread") or wf.get("by_spread") or {}
    pool_by = pool.get("by_spread") or {}
    gate_by = gate.get("by_spread") or {}
    all_spreads = sorted(set(list(comp_by.keys()) + list(pool_by.keys()) +
                             list(gate_by.keys()) + list(base_by_spread.keys())))
    for sp in all_spreads:
        c = comp_by.get(sp, {}); p = pool_by.get(sp, {})
        g = gate_by.get(sp, {}); b = base_by_spread.get(sp, {})
        rows.append([
            sp,
            _fmt(c.get("sharpe"), 2),
            _fmt(p.get("sharpe"), 2),
            str(g.get("n_signals") or 0),
            _fmt(g.get("sharpe"), 2),
            _fmt(b.get("sharpe"), 2),
            _delta(g.get("sharpe"), b.get("sharpe"), 2),
        ])
    t = Table(rows, colWidths=[1.25*inch, 0.75*inch, 0.75*inch, 0.7*inch, 0.75*inch, 0.75*inch, 0.7*inch])
    _style_table(t)
    story.append(t)
    story.append(Spacer(1, 4))

    # ── Gated-blend slices: which leg fires, and how ──────────────────────
    bs_gated = gate.get("by_source") or {}
    bw_gated = gate.get("by_winner") or {}
    summary_rows = [
        ["Gated-blend slice", "n", "Hit", "μPnL", "Sharpe"],
        *[[f"source={src}", str(m.get("n_signals") or 0), _fmt_pct(m.get("hit_rate")),
           _fmt(m.get("mean_pnl"), 3), _fmt(m.get("sharpe"), 2)]
          for src, m in bs_gated.items()],
        *[[f"winner={w}", str(m.get("n_signals") or 0), _fmt_pct(m.get("hit_rate")),
           _fmt(m.get("mean_pnl"), 3), _fmt(m.get("sharpe"), 2)]
          for w, m in bw_gated.items() if w],
    ]
    story.append(Paragraph("Gated-blend slices — which leg fired (regime vs baseline) and winner mix", h2))
    t3 = Table(summary_rows, colWidths=[1.7*inch, 0.6*inch, 0.65*inch, 0.7*inch, 0.7*inch])
    _style_table(t3)
    story.append(t3)
    story.append(Spacer(1, 4))

    # ── Phase 2.7 — sized-blend comparison ────────────────────────────────
    if sized:
        story.append(Paragraph(
            "Phase 2.7 — sized regime leg vs gated full / baseline",
            h2,
        ))
        sized_rows = [
            ["Metric",            "Gated full",                       "Sized 0.5×",                    "Sized Kelly",                    "Baseline 252d z",                "Δ best vs base"],
            ["Signals fired",     str(go.get("n_signals") or 0),       str(sho.get("n_signals") or 0),  str(sko.get("n_signals") or 0),   str(bo.get("n_signals") or 0),    "—"],
            ["Hit rate",          _fmt_pct(go.get("hit_rate")),        _fmt_pct(sho.get("hit_rate")),   _fmt_pct(sko.get("hit_rate")),    _fmt_pct(bo.get("hit_rate")),     "—"],
            ["Mean PnL ($/bbl)",  _fmt(go.get("mean_pnl"), 3),         _fmt(sho.get("mean_pnl"), 3),    _fmt(sko.get("mean_pnl"), 3),     _fmt(bo.get("mean_pnl"), 3),      "—"],
            ["Total PnL",         _fmt(go.get("total_pnl"), 1),        _fmt(sho.get("total_pnl"), 1),   _fmt(sko.get("total_pnl"), 1),    _fmt(bo.get("total_pnl"), 1),     "—"],
            ["Sharpe (ann.)",     _fmt(go.get("sharpe"), 2),           _fmt(sho.get("sharpe"), 2),      _fmt(sko.get("sharpe"), 2),       _fmt(bo.get("sharpe"), 2),
                _delta(max((x for x in (go.get("sharpe"), sho.get("sharpe"), sko.get("sharpe")) if x is not None), default=None),
                       bo.get("sharpe"), 2)],
            ["Max drawdown",      _fmt(go.get("max_drawdown"), 1),     _fmt(sho.get("max_drawdown"), 1),_fmt(sko.get("max_drawdown"), 1), _fmt(bo.get("max_drawdown"), 1),
                _delta(max((x for x in (go.get("max_drawdown"), sho.get("max_drawdown"), sko.get("max_drawdown")) if x is not None), default=None),
                       bo.get("max_drawdown"), 1)],
            ["Mean regime scale", "1.0",
                _fmt(sized_half.get("mean_regime_scale"), 3),
                _fmt(sized_kelly.get("mean_regime_scale"), 3),
                "—", "—"],
        ]
        ts = Table(sized_rows, colWidths=[1.18*inch, 1.0*inch, 1.0*inch, 1.0*inch, 1.1*inch, 1.05*inch])
        _style_table(ts)
        story.append(ts)
        story.append(Spacer(1, 4))

        # Phase 2.7 verdict callout
        gs = go.get("sharpe"); shs = sho.get("sharpe"); sks = sko.get("sharpe"); bs2 = bo.get("sharpe")
        gd = go.get("max_drawdown"); shd = sho.get("max_drawdown"); skd = sko.get("max_drawdown"); bd = bo.get("max_drawdown")
        best_name, best_sharpe = "gated full", gs
        for nm, val in (("sized 0.5×", shs), ("sized Kelly", sks)):
            if val is not None and (best_sharpe is None or val > best_sharpe):
                best_name, best_sharpe = nm, val
        # Track DD compression on the best Sharpe variant
        best_dd = {"gated full": gd, "sized 0.5×": shd, "sized Kelly": skd}.get(best_name)

        phase27_lead = "<b>Phase 2.7 finding:</b> "
        if best_sharpe is not None and bs2 is not None and best_sharpe >= bs2:
            phase27_lead += (
                f"the <b>{best_name}</b> variant carries the headline at Sharpe "
                f"{best_sharpe:+.2f} (vs baseline {bs2:+.2f})."
            )
        else:
            phase27_lead += (
                f"no sizing mode caught baseline at the headline Sharpe "
                f"(best {best_name} {best_sharpe if best_sharpe is None else f'{best_sharpe:+.2f}'} vs baseline {bs2 if bs2 is None else f'{bs2:+.2f}'})."
            )

        if best_dd is not None and bd is not None:
            phase27_lead += (
                f" Max DD on the best variant: {best_dd:+.1f} vs baseline {bd:+.1f}"
                f" (gated full: {gd:+.1f})."
            )

        klp = sized_summary.get("kelly_per_spread_latest") or {}
        if klp:
            top_klp = ", ".join(f"{sp}={v:.2f}" for sp, v in list(klp.items()))
            phase27_lead += f" Latest per-spread Kelly fractions: {top_klp}."

        story.append(Paragraph(phase27_lead, callout))
        story.append(Spacer(1, 4))

    # ── Phase 2.8.6 — NET (after transaction costs) ────────────────────────
    costs = wf.get("costs") or {}
    if costs:
        story.append(Paragraph(
            "Phase 2.8.6 &mdash; NET headline (after transaction costs)",
            h2,
        ))
        story.append(Paragraph(
            f"<b>Cost model:</b> per-leg per-side $0.0025 commission + half-spread "
            f"slippage ($0.0050 front / $0.0075 deferred). RT cost per spread: "
            f"M1-M2 $0.030, M3-M6 $0.040, fly $0.050.",
            note,
        ))

        base_net = (costs.get("baseline_net") or {}).get("overall") or {}
        pool_net = (costs.get("pooled_net")   or {}).get("overall") or {}
        gate_net = (costs.get("gated_blend_net") or {}).get("overall") or {}
        sbn      = costs.get("sized_blend_net") or {}
        sh_net = (sbn.get("half")  or {}).get("overall") or {}
        sk_net = (sbn.get("kelly") or {}).get("overall") or {}

        def _both(gross, net, key, digits=3):
            g = gross.get(key); n = net.get(key)
            g_s = _fmt(g, digits) if g is not None else "—"
            n_s = _fmt(n, digits) if n is not None else "—"
            return f"{g_s} / {n_s}"

        net_rows = [
            ["Mode",                "Gross / Net Sharpe",                                        "Gross / Net μPnL",                                            "Mean cost / fire", "n fired"],
            ["Baseline 252d z",     _both(bo, base_net, "sharpe", 2),                            _both(bo, base_net, "mean_pnl", 3),                            _fmt(base_net.get("mean_cost"), 4), str(base_net.get("n_signals") or 0)],
            ["Pooled (un-gated)",   _both(po, pool_net, "sharpe", 2),                            _both(po, pool_net, "mean_pnl", 3),                            _fmt(pool_net.get("mean_cost"), 4), str(pool_net.get("n_signals") or 0)],
            ["Gated blend (2.8.3)", _both(go, gate_net, "sharpe", 2),                            _both(go, gate_net, "mean_pnl", 3),                            _fmt(gate_net.get("mean_cost"), 4), str(gate_net.get("n_signals") or 0)],
            ["Sized half",          _both(sho, sh_net, "sharpe", 2),                             _both(sho, sh_net, "mean_pnl", 3),                             _fmt(sh_net.get("mean_cost"), 4),   str(sh_net.get("n_signals") or 0)],
            ["Sized kelly",         _both(sko, sk_net, "sharpe", 2),                             _both(sko, sk_net, "mean_pnl", 3),                             _fmt(sk_net.get("mean_cost"), 4),   str(sk_net.get("n_signals") or 0)],
        ]
        nt = Table(net_rows, colWidths=[1.5*inch, 1.5*inch, 1.5*inch, 1.0*inch, 0.7*inch])
        _style_table(nt)
        story.append(nt)
        story.append(Spacer(1, 4))

        # Per-spread NET Sharpe — gated_blend vs baseline
        gate_net_by_sp = (costs.get("gated_blend_net") or {}).get("by_spread") or {}
        base_net_by_sp = (costs.get("baseline_net")    or {}).get("by_spread") or {}
        net_sp_rows = [["Spread", "Gross Shp (gated)", "Net Shp (gated)", "Net Shp (base)", "Δ Net vs base"]]
        for sp in sorted(set(list(gate_net_by_sp) + list(base_net_by_sp))):
            g_gr = (gate_by.get(sp)         or {}).get("sharpe")
            g_nt = (gate_net_by_sp.get(sp)  or {}).get("sharpe")
            b_nt = (base_net_by_sp.get(sp)  or {}).get("sharpe")
            d = (g_nt - b_nt) if (g_nt is not None and b_nt is not None) else None
            net_sp_rows.append([
                sp,
                _fmt(g_gr, 2),
                _fmt(g_nt, 2),
                _fmt(b_nt, 2),
                _fmt(d, 2),
            ])
        sp_nt = Table(net_sp_rows, colWidths=[1.4*inch, 1.3*inch, 1.3*inch, 1.3*inch, 1.0*inch])
        _style_table(sp_nt)
        story.append(sp_nt)
        story.append(Spacer(1, 4))

        # Phase 2.8.6 finding callout
        gross_sharpes = {"baseline": bo.get("sharpe"), "pooled": po.get("sharpe"),
                         "gated": go.get("sharpe"), "half": sho.get("sharpe"), "kelly": sko.get("sharpe")}
        net_sharpes   = {"baseline": base_net.get("sharpe"), "pooled": pool_net.get("sharpe"),
                         "gated": gate_net.get("sharpe"), "half": sh_net.get("sharpe"), "kelly": sk_net.get("sharpe")}

        cost_drag_baseline = (bo.get("sharpe") or 0) - (base_net.get("sharpe") or 0)
        cost_drag_gated    = (go.get("sharpe") or 0) - (gate_net.get("sharpe") or 0)
        cost_drag_pooled   = (po.get("sharpe") or 0) - (pool_net.get("sharpe") or 0)

        best_net_name, best_net_val = max(
            ((k, v) for k, v in net_sharpes.items() if v is not None),
            key=lambda kv: kv[1],
            default=("none", None),
        )
        gated_vs_base_net = ((gate_net.get("sharpe") or 0) - (base_net.get("sharpe") or 0))

        phase286 = (
            f"<b>Phase 2.8.6 finding:</b> transaction costs erode Sharpe roughly "
            f"uniformly across modes &mdash; baseline drag {cost_drag_baseline:+.2f}, "
            f"pooled {cost_drag_pooled:+.2f}, gated_blend {cost_drag_gated:+.2f}. "
            f"Mean cost per fire sits at $0.039-$0.045/bbl depending on spread mix "
            f"(boosters fire more on the fly which is the most expensive class). "
            f"<b>Best net Sharpe: {best_net_name} at {best_net_val:+.3f}.</b> "
            f"Gated blend net Sharpe ({gate_net.get('sharpe', 0):+.3f}) vs baseline net "
            f"({base_net.get('sharpe', 0):+.3f}) = Δ {gated_vs_base_net:+.3f} &mdash; "
        )
        if gated_vs_base_net >= 0.02:
            phase286 += (
                "the gated blend retains a meaningful net edge over baseline. Costs "
                "do not flip the Phase 2.8.3 verdict."
            )
        elif gated_vs_base_net >= -0.02:
            phase286 += (
                "the gated blend ties baseline at the net headline. The Phase 2.8.3 "
                "&apos;flat headline / improved attribution&apos; verdict holds under costs."
            )
        else:
            phase286 += (
                "the gated blend loses to baseline at the net headline. Transaction "
                "costs widen the gap because the regime fires concentrate on the "
                "fly (highest per-trade cost class)."
            )

        if (pool_net.get("sharpe") or 0) > (base_net.get("sharpe") or 0) + 0.02 and \
           (pool_net.get("sharpe") or 0) > (gate_net.get("sharpe") or 0) + 0.02:
            phase286 += (
                f" <b>Notable side finding</b>: the un-gated pooled engine "
                f"({pool_net.get('sharpe', 0):+.3f} net) now beats both gated_blend "
                f"and baseline under costs &mdash; Phase 2.8.1+2 boosters lifted "
                f"pooled gross enough that the Phase 2.6 gate (added when pooled was "
                f"losing) is over-restrictive. Concrete recommendation: A/B test "
                f"<code>PULSE_REGIME_MODE=pooled</code> against "
                f"<code>PULSE_GATED_BLEND=1</code> in paper before changing default."
            )
        story.append(Paragraph(phase286, callout))
        story.append(Spacer(1, 4))

    story.append(Paragraph("Caveats &amp; next steps", h2))
    tight = ParagraphStyle("Tight", parent=body, fontSize=8, leading=10, spaceAfter=2)
    caveats = [
        "<b>WTI is synthesised</b> — last-1-min midprice per session, not exchange print. Mentor's real WTI C1-C3 daily file slots in without code changes.",
        "<b>Sparse cells (composite only)</b> — 96/162 composite cells (BACK × HIGH, CONTANGO × LOW) stay empty. The pooled grid is dense by construction (3 cells/spread, average ~770 rows/cell vs ~150 composite).",
        "<b>Phase 1 not directly comparable</b> — Phase 1 is a 9-indicator directional Brent signal; the baseline here (regime-unaware 252d z on spreads) is the cleanest test of regime-conditioning value.",
        "<b>Costs modelled (Phase 2.8.6)</b> &mdash; defensible per-spread RT cost ($0.030 M1-M2 / $0.040 M3-M6 / $0.050 fly per bbl) layered on top of gross spread-move PnL. Roll slippage and funding still ignored; live deployment should add a per-spread broker quote where available.",
        "<b>Mode switch</b> — set <code>PULSE_REGIME_MODE=pooled</code> for un-gated pooled inference, <code>PULSE_GATED_BLEND=1</code> (Phase 2.6) for the gated blend, and <code>PULSE_GATED_SIZE=&lt;full|half|kelly&gt;</code> (Phase 2.7) to scale the regime-leg notional. Default is composite + full sizing for back-compat with Sprint 3 dashboard cards.",
        "<b>Gate is conservative by design</b> — Phase 2.5 demonstrated lift only on (BACK regime × {Lasso, Huber} winners). The gated blend codifies exactly that slice; per-spread Sharpe and the regime/baseline split in the headline disclose how often the engine actually fires versus deferring to the baseline.",
        "<b>Phase 2.7 sizing has a Sharpe-vs-DD trade-off</b> — uniform 0.5× halves both mean PnL and max DD on the regime leg; Kelly is per-spread and adaptive but its sample is thin (97 regime fires total). Live deployment should read <code>sized_blend_summary.kelly_per_spread_latest</code> from the walk-forward report — the same numbers shown above — to size at inference time.",
        "<b>Next:</b> fold inventory + vol back in as <i>features</i> inside the pooled regression so they inform fair value without fragmenting the training set; trial 5/60-day horizons (one-line change in <code>walkforward.py</code>); consider per-spread gate thresholds where the per-spread lift table justifies them.",
    ]
    for c in caveats:
        story.append(Paragraph("• " + c, tight))

    doc.build(story)
    return out_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    out = build_pdf()
    print(f"Wrote: {out}  ({out.stat().st_size:,} bytes)")
