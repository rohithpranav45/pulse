"""
Charts for the Inventory Surprise Impact deck. PULSE dark theme.

    python -m backend.research.inventory_impact.charts

Writes PNGs to backend/data/research/inventory_impact/:
    chart_when_it_mattered.png   regime-conditional beta + |t| (the centerpiece)
    chart_era_scatter.png        surprise vs reaction, glut vs tight, with fit lines
    chart_quality.png            quality-of-draw vs headline surprise (divergence)
    chart_decay_placebo.png      release-day vol vs placebo, by window width
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import data_lake as dl  # noqa: E402
from research.inventory_impact import eia_report, regime_conditioning  # noqa: E402

OUT = Path(__file__).parent.parent.parent / "data" / "research" / "inventory_impact"
OUT.mkdir(parents=True, exist_ok=True)

# PULSE palette
BG, PANEL, GRID = "#0B0F1A", "#131A2A", "#1E293B"
GOLD, GREEN, CYAN, RED, TEXT, MUT = ("#F5A623", "#10B981", "#22D3EE", "#FB7185", "#E2E8F0", "#94A3B8")


def _style(ax):
    ax.set_facecolor(PANEL)
    for sp in ax.spines.values():
        sp.set_color(GRID)
    ax.tick_params(colors=MUT, labelsize=9)
    ax.xaxis.label.set_color(MUT)
    ax.yaxis.label.set_color(MUT)
    ax.title.set_color(TEXT)
    ax.grid(color=GRID, alpha=0.5, linewidth=0.6)


def chart_when_it_mattered(panel: pd.DataFrame) -> None:
    """The centerpiece: beta (bars) + |t| significance (markers) by regime."""
    import matplotlib.pyplot as plt

    tbl = regime_conditioning.conditional_table(panel, "ret")
    order = ["HIGH stocks", "above 5yr (glut)", "contango front", "AVG stocks",
             "all releases", "backwardated front", "below 5yr (tight)", "LOW stocks"]
    tbl = tbl.set_index("regime").reindex([r for r in order if r in set(tbl["regime"])]).reset_index()

    fig, ax = plt.subplots(figsize=(11.5, 5.6), facecolor=BG)
    _style(ax)
    y = np.arange(len(tbl))[::-1]
    betas = tbl["beta"].values
    sig = tbl["t"].abs().values >= 2.0
    colors = [GREEN if s else MUT for s in sig]
    ax.barh(y, betas, color=colors, alpha=0.9, height=0.62)
    for yi, (b, t, n, s) in zip(y, zip(tbl["beta"], tbl["t"], tbl["n"], sig)):
        ax.text(b - 0.03 if b < 0 else b + 0.03, yi,
                f"β={b:+.2f}  t={t:+.1f}  n={int(n)}" + ("  ★" if s else ""),
                va="center", ha="right" if b < 0 else "left",
                color=TEXT if s else MUT, fontsize=8.6, fontweight="bold" if s else "normal")
    ax.set_yticks(y)
    ax.set_yticklabels(tbl["regime"], color=TEXT, fontsize=9.5)
    ax.axvline(0, color=MUT, linewidth=0.9)
    ax.set_xlabel("surprise→Brent release-day return  (% per 1σ surprise)")
    ax.set_title("WHEN INVENTORIES MATTERED  —  green ★ = statistically significant (|t|≥2), 2015-2026, n=535",
                 fontsize=11, pad=12)
    ax.set_xlim(min(betas) - 0.55, max(betas) + 0.35)
    fig.tight_layout()
    fig.savefig(OUT / "chart_when_it_mattered.png", dpi=170, facecolor=BG)
    plt.close(fig)


def chart_era_scatter(panel: pd.DataFrame) -> None:
    """Surprise vs reaction scatter, glut (HIGH/contango) vs tight, with fit lines."""
    import matplotlib.pyplot as plt

    glut = panel[panel["inv_pct"] > 0]
    tight = panel[panel["inv_pct"] <= 0]
    fig, ax = plt.subplots(figsize=(9.6, 6.0), facecolor=BG)
    _style(ax)

    def scatter_fit(sub, color, label):
        x, y = sub["surprise_z"].values, sub["ret"].values
        m = np.isfinite(x) & np.isfinite(y)
        x, y = x[m], y[m]
        ax.scatter(x, y, s=16, color=color, alpha=0.55, edgecolors="none", label=f"{label} (n={len(x)})")
        b, a = np.polyfit(x, y, 1)
        xs = np.linspace(x.min(), x.max(), 50)
        ax.plot(xs, a + b * xs, color=color, linewidth=2.4)
        return b

    b_glut = scatter_fit(glut, GOLD, "glut: stocks > 5yr")
    b_tight = scatter_fit(tight, CYAN, "tight: stocks ≤ 5yr")
    ax.axhline(0, color=MUT, linewidth=0.7)
    ax.axvline(0, color=MUT, linewidth=0.7)
    ax.set_xlabel("inventory surprise  (σ; negative = bullish / tighter than expected)")
    ax.set_ylabel("Brent front return on release day  (%)")
    ax.set_title(f"Surprise bites in a glut (slope {b_glut:+.2f}), not when tight (slope {b_tight:+.2f})",
                 fontsize=11, pad=10)
    ax.set_ylim(-6, 6)
    leg = ax.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT, fontsize=9.5, loc="upper right")
    leg.get_frame().set_alpha(0.9)
    fig.tight_layout()
    fig.savefig(OUT / "chart_era_scatter.png", dpi=170, facecolor=BG)
    plt.close(fig)


def chart_quality(n_weeks: int = 120) -> None:
    """Quality-of-draw vs headline surprise — the divergence map."""
    import matplotlib.pyplot as plt

    dec = eia_report.decomposition()
    sp = eia_report.surprise_series("crude_ex_spr")
    df = dec.join(sp[["surprise_z"]]).dropna(subset=["quality_of_draw", "surprise_z"]).tail(n_weeks)

    fig, ax = plt.subplots(figsize=(9.6, 6.0), facecolor=BG)
    _style(ax)
    headline_bull = -df["surprise_z"].values    # +ve = bullish headline
    quality = df["quality_of_draw"].values
    # colour: agree (both same sign) vs divergent
    agree = np.sign(headline_bull) == np.sign(quality)
    ax.scatter(headline_bull[agree], quality[agree], s=26, color=GREEN, alpha=0.6, label="headline & quality agree")
    ax.scatter(headline_bull[~agree], quality[~agree], s=34, color=RED, alpha=0.8,
               label="DIVERGENT — headline lies (fade)")
    ax.axhline(0, color=MUT, linewidth=0.7)
    ax.axvline(0, color=MUT, linewidth=0.7)
    ax.set_xlabel("headline surprise  (+ = bullish draw vs expected)")
    ax.set_ylabel("quality-of-draw  (+ = demand-led / coherent)")
    ax.set_title("Don't trust the headline: top-left & bottom-right = bullish draw, weak internals",
                 fontsize=10.5, pad=10)
    leg = ax.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT, fontsize=9.5, loc="upper left")
    leg.get_frame().set_alpha(0.9)
    fig.tight_layout()
    fig.savefig(OUT / "chart_quality.png", dpi=170, facecolor=BG)
    plt.close(fig)


def chart_decay_placebo() -> None:
    """Release-day vol vs a non-release placebo, by window width (the null)."""
    import matplotlib.pyplot as plt

    panel = pd.read_parquet(OUT / "event_panel.parquet")
    rel = set(str(pd.Timestamp(t).tz_convert("America/New_York").date()) for t in panel.index)
    con = dl.duckdb_conn()
    widths = [("10:31", 10, 31, 32, "2m"), ("10:34", 10, 34, 35, "5m"),
              ("10:39", 10, 39, 40, "10m"), ("11:00", 11, 0, 1, "30m"), ("12:30", 12, 29, 30, "2h")]
    rel_v, norm_v, labels = [], [], []
    for _, h, mlo, mhi, lab in widths:
        q = f'''WITH base AS (SELECT (timestamp AT TIME ZONE 'America/New_York') et, "c1||weighted_mid" c1 FROM wti_1min)
        SELECT CAST(et AS DATE) d,
          max(CASE WHEN EXTRACT(hour FROM et)=10 AND EXTRACT(minute FROM et)=29 THEN c1 END) p0,
          max(CASE WHEN EXTRACT(hour FROM et)={h} AND EXTRACT(minute FROM et) BETWEEN {mlo} AND {mhi} THEN c1 END) p1
        FROM base GROUP BY 1'''
        d = con.execute(q).df()
        d["mv"] = (d["p1"] / d["p0"] - 1).abs() * 100
        d = d.dropna(subset=["mv"])
        d["rel"] = d["d"].astype(str).isin(rel)
        rel_v.append(d[d.rel].mv.mean())
        norm_v.append(d[~d.rel].mv.mean())
        labels.append(lab)

    fig, ax = plt.subplots(figsize=(9.6, 5.4), facecolor=BG)
    _style(ax)
    x = np.arange(len(labels))
    w = 0.38
    ax.bar(x - w / 2, rel_v, w, color=GOLD, alpha=0.92, label="EIA release day")
    ax.bar(x + w / 2, norm_v, w, color=MUT, alpha=0.7, label="normal weekday (placebo)")
    for xi, (r, n) in enumerate(zip(rel_v, norm_v)):
        ax.text(xi, max(r, n) + 0.01, f"{r/n:.2f}×", ha="center", color=TEXT, fontsize=9, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([f"10:29→{lab}" for lab in labels], color=TEXT, fontsize=9)
    ax.set_ylabel("mean |WTI move|  (%)")
    ax.set_title("The 2021-26 print is NOT even a vol event: ~1.0× a normal day at every horizon",
                 fontsize=10.5, pad=10)
    leg = ax.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT, fontsize=9.5)
    leg.get_frame().set_alpha(0.9)
    fig.tight_layout()
    fig.savefig(OUT / "chart_decay_placebo.png", dpi=170, facecolor=BG)
    plt.close(fig)


def main():
    panel = regime_conditioning.build_daily_panel("seasonal")
    print("chart 1/4 — when it mattered …"); chart_when_it_mattered(panel)
    print("chart 2/4 — era scatter …"); chart_era_scatter(panel)
    print("chart 3/4 — quality divergence …"); chart_quality()
    print("chart 4/4 — decay / placebo …"); chart_decay_placebo()
    print(f"\nPNGs -> {OUT}")


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    main()
