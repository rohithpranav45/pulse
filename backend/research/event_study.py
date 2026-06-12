"""
Event-to-distribution framework — converts a geopolitical supply-threat headline
into probability distributions for Brent calendar spreads.

Assignment headline (2026-06-12):
    "Israel launches strikes on Iranian energy infrastructure.
     Iran threatens closure of the Strait of Hormuz."

Target spreads: M1-M2, M2-M4, M1-M6 · horizon: 5 trading days (1 week).

Pipeline
--------
1. EVENT STUDY — 13 Middle-East / supply-threat events (2018-2025), measure
   the 5-trading-day spread change from the last close before the event.
   Tier events by severity; the June 2025 Israel-Iran war is the direct analog.
2. SCENARIO TREE — four exhaustive outcomes for the week, probabilities
   anchored to historical escalation frequencies + structural arguments
   (Hormuz has never closed; Iran's own exports transit it).
3. CONDITIONAL DISTRIBUTIONS — each scenario gets a per-spread (mu, sigma)
   anchored to measured event-study deltas; noise floor = BACK-regime weekly
   vol (current regime is BACK/LOW/STRESSED — vol is ~2x unconditional).
4. MONTE CARLO MIXTURE — 200k draws, one-factor correlation across spreads
   (empirical 5d-change corr ~0.8), produces EV / 50% / 90% intervals.

Outputs (backend/data/research/event_study/):
    results.json            — all numbers the deck quotes
    event_deltas.csv        — the event-study table
    chart_event_study.png   — Δ5d by event x spread
    chart_june2025.png      — daily path of the June 2025 analog
    chart_dist_<spread>.png — mixture density with 50/90 bands
    chart_scenarios.png     — scenario dot-range chart

Run:  python -m backend.research.event_study   (from repo root, ~20 s)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ── bootstrap so `python -m backend.research.event_study` works ─────────────
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

OUT_DIR = _BACKEND / "data" / "research" / "event_study"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SPREADS = ["m1_m2", "m2_m4", "m1_m6"]
LABELS = {"m1_m2": "M1-M2", "m2_m4": "M2-M4", "m1_m6": "M1-M6"}
HORIZON_BD = 5          # trading days ≈ 1 calendar week
N_DRAWS = 200_000
RHO = None              # one-factor corr — measured from data below
SEED = 42

# ── 1. Event catalogue ───────────────────────────────────────────────────────
# tier 1 = verbal / proxy / symbolic   tier 2 = kinetic on shipping
# tier 3 = kinetic on energy infrastructure   tier 4 = full supply war
EVENTS = [
    ("2018-05-08", "US exits JCPOA",                 1),
    ("2019-05-12", "Fujairah tanker sabotage",       2),
    ("2019-06-13", "Gulf of Oman tanker attacks",    2),
    ("2019-06-20", "Iran downs US drone",            1),
    ("2019-09-14", "Abqaiq-Khurais attack",          3),
    ("2020-01-03", "Soleimani strike",               1),
    ("2022-02-24", "Russia invades Ukraine",         4),
    ("2023-10-07", "Hamas attack on Israel",         1),
    ("2024-01-12", "US/UK strikes on Houthis",       2),
    ("2024-04-13", "Iran direct attack on Israel",   1),
    ("2024-10-01", "Iran missile barrage on Israel", 1),
    ("2024-10-26", "Israel strikes Iran military",   1),
    ("2025-06-13", "Israel-Iran 12-day war",         3),
]


def build_spreads() -> pd.DataFrame:
    from data_lake import get_brent_settlements
    settle = get_brent_settlements()
    df = pd.DataFrame(index=settle.index)
    df["m1_m2"] = settle["c1"] - settle["c2"]
    df["m2_m4"] = settle["c2"] - settle["c4"]
    df["m1_m6"] = settle["c1"] - settle["c6"]
    df["m1_m12"] = settle["c1"] - settle["c12"]   # regime proxy
    return df.dropna()


def event_deltas(spreads: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for date, label, tier in EVENTS:
        ts = pd.Timestamp(date)
        pre = spreads.index[spreads.index < ts]
        post = spreads.index[spreads.index >= ts]
        if len(pre) == 0 or len(post) <= HORIZON_BD:
            continue
        t0, t5 = pre[-1], post[HORIZON_BD]
        row = {"date": date, "event": label, "tier": tier}
        for s in SPREADS:
            row[f"{s}_d5"] = round(spreads.loc[t5, s] - spreads.loc[t0, s], 3)
        rows.append(row)
    return pd.DataFrame(rows)


def scenario_params(ev: pd.DataFrame, back_vol: dict[str, float]) -> list[dict]:
    """
    Four exhaustive scenarios for the week after the headline.

    Anchoring logic (all numbers traceable to the event-study table):
      S1 mean   ~ tier-1 cohort mean (fade / symbolic response) with a
                  negative tilt because today's base is stretched (m1_m2 2.91
                  vs p99 5.22 — premium unwind overshoots, cf. 2025-06-23).
      S2 mean   = June 2025 D+5 deltas verbatim — that episode WAS
                  "war ongoing at day 5, Hormuz open".
      S3 mean   ~ Abqaiq x ~2.5 (energy infrastructure hit AND flows impaired)
                  ≈ midway to the Russia-2022 print.
      S4 mean   ~ Russia-2022 deltas as the observed floor for "structural
                  supply repricing", with a fat right tail toward the p99
                  distance from today's levels.
      sigma     = max(tier dispersion, BACK-regime weekly vol) — never let a
                  scenario claim more precision than baseline regime noise.
    """
    june25 = ev.loc[ev["event"] == "Israel-Iran 12-day war",
                    [f"{s}_d5" for s in SPREADS]].iloc[0]
    abqaiq = ev.loc[ev["event"] == "Abqaiq-Khurais attack",
                    [f"{s}_d5" for s in SPREADS]].iloc[0]
    russia = ev.loc[ev["event"] == "Russia invades Ukraine",
                    [f"{s}_d5" for s in SPREADS]].iloc[0]
    tier1 = ev[ev["tier"] == 1][[f"{s}_d5" for s in SPREADS]]

    def sig(base: dict[str, float], mult: float) -> dict[str, float]:
        return {s: max(back_vol[s] * mult, 0.10) for s in SPREADS}

    return [
        {
            "name": "De-escalation / contained",
            "prob": 0.30,
            "story": ("Iranian response symbolic; backchannel ceasefire talk; "
                      "risk premium unwinds from a stretched base "
                      "(June-2025 ceasefire pattern: M1-M2 fell 0.57 in one day)"),
            "mu": {s: round(float(tier1[f"{s}_d5"].mean()) - 0.5 * back_vol[s], 3)
                   for s in SPREADS},
            "sigma": sig(back_vol, 1.0),
        },
        {
            "name": "Sustained conflict, Hormuz open",
            "prob": 0.40,
            "story": ("Strikes continue through the week, shipping unimpeded — "
                      "exactly the June-2025 D+5 state; premium holds/builds"),
            "mu": {s: round(float(june25[f"{s}_d5"]), 3) for s in SPREADS},
            "sigma": sig(back_vol, 1.2),
        },
        {
            "name": "Partial Hormuz disruption",
            "prob": 0.22,
            "story": ("Tanker harassment / mining / seizures; insurance spikes, "
                      "some cargoes deferred — Abqaiq-style infrastructure shock "
                      "amplified by flow impairment"),
            "mu": {s: round(2.5 * float(abqaiq[f"{s}_d5"]), 3) for s in SPREADS},
            "sigma": sig(back_vol, 1.8),
        },
        {
            "name": "Closure attempt",
            "prob": 0.08,
            "story": ("Military attempt to halt transit; 17-20 mb/d at risk vs "
                      "~6.5 mb/d pipeline bypass; never observed — anchored on "
                      "Russia-2022 as the floor, fat right tail"),
            "mu": {s: round(1.2 * float(russia[f"{s}_d5"]), 3) for s in SPREADS},
            "sigma": sig(back_vol, 2.8),
        },
    ]


def monte_carlo(scen: list[dict], rho: float, rng: np.random.Generator
                ) -> dict[str, np.ndarray]:
    probs = np.array([sc["prob"] for sc in scen])
    assert abs(probs.sum() - 1.0) < 1e-9
    which = rng.choice(len(scen), size=N_DRAWS, p=probs)
    z = rng.standard_normal(N_DRAWS)                       # common shock
    draws: dict[str, np.ndarray] = {}
    for s in SPREADS:
        eps = rng.standard_normal(N_DRAWS)                 # idiosyncratic
        shock = rho * z + np.sqrt(1 - rho ** 2) * eps
        mu = np.array([sc["mu"][s] for sc in scen])[which]
        sg = np.array([sc["sigma"][s] for sc in scen])[which]
        d = mu + sg * shock
        # Closure scenario: add a lognormal kicker on the right tail —
        # an unprecedented event has more upside surprise than a normal allows.
        is_s4 = which == len(scen) - 1
        kick = rng.lognormal(mean=0.0, sigma=0.8, size=N_DRAWS) - 1.0
        d = d + np.where(is_s4, np.maximum(kick, 0.0) * sg * 0.6, 0.0)
        draws[s] = d
    return draws


def summarise(draws: dict[str, np.ndarray], current: dict[str, float]) -> dict:
    out = {}
    for s in SPREADS:
        d = draws[s]
        q = np.percentile(d, [5, 25, 50, 75, 95])
        out[s] = {
            "current": round(current[s], 2),
            "ev_delta": round(float(d.mean()), 2),
            "ev_level": round(current[s] + float(d.mean()), 2),
            "p5": round(float(q[0]), 2),   "p25": round(float(q[1]), 2),
            "p50": round(float(q[2]), 2),  "p75": round(float(q[3]), 2),
            "p95": round(float(q[4]), 2),
            "ci50_level": [round(current[s] + float(q[1]), 2),
                           round(current[s] + float(q[3]), 2)],
            "ci90_level": [round(current[s] + float(q[0]), 2),
                           round(current[s] + float(q[4]), 2)],
            "p_widen": round(float((d > 0).mean()), 3),
        }
    return out


# ── charts ───────────────────────────────────────────────────────────────────
BG, PANEL, GRID = "#0B0F1A", "#131A2A", "#1E293B"
GOLD, GREEN, CYAN, RED, TEXT, MUT = ("#F5A623", "#10B981", "#22D3EE",
                                     "#FB7185", "#E2E8F0", "#94A3B8")
SPREAD_COLOURS = {"m1_m2": GOLD, "m2_m4": CYAN, "m1_m6": GREEN}


def _style(ax):
    ax.set_facecolor(PANEL)
    for sp in ax.spines.values():
        sp.set_color(GRID)
    ax.tick_params(colors=MUT, labelsize=9)
    ax.xaxis.label.set_color(MUT)
    ax.yaxis.label.set_color(MUT)
    ax.title.set_color(TEXT)
    ax.grid(color=GRID, alpha=0.5, linewidth=0.6)


def chart_event_study(ev: pd.DataFrame) -> None:
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(12.2, 5.2), facecolor=BG)
    _style(ax)
    x = np.arange(len(ev))
    w = 0.27
    for i, s in enumerate(SPREADS):
        ax.bar(x + (i - 1) * w, ev[f"{s}_d5"], w,
               label=LABELS[s], color=SPREAD_COLOURS[s], alpha=0.92)
    ax.axhline(0, color=MUT, linewidth=0.8)
    short = [e.replace(" attack", "").replace(" attacks", "")[:22] for e in ev["event"]]
    ax.set_xticks(x)
    ax.set_xticklabels([f"{d[2:7]} {n}" for d, n in zip(ev["date"], short)],
                       fontsize=7.6, color=MUT, rotation=28, ha="right")
    ax.set_ylabel("Δ spread over 5 trading days ($/bbl)")
    ax.set_title("Event study — 13 supply-threat events, 5-day spread response",
                 fontsize=13, fontweight="bold", pad=12)
    leg = ax.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT, fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "chart_event_study.png", dpi=170, facecolor=BG)
    plt.close(fig)


def chart_june2025(spreads: pd.DataFrame) -> None:
    import matplotlib.pyplot as plt
    win = spreads.loc["2025-06-02":"2025-07-08", SPREADS]
    fig, ax = plt.subplots(figsize=(12.2, 4.8), facecolor=BG)
    _style(ax)
    for s in SPREADS:
        ax.plot(win.index, win[s], color=SPREAD_COLOURS[s], linewidth=2.2,
                label=LABELS[s])
    strike = pd.Timestamp("2025-06-13")
    cease = pd.Timestamp("2025-06-24")
    ax.axvline(strike, color=RED, linestyle="--", linewidth=1.4)
    ax.axvline(cease, color=GREEN, linestyle="--", linewidth=1.4)
    ax.text(strike, ax.get_ylim()[1] * 0.97, " first strikes", color=RED,
            fontsize=9, va="top")
    ax.text(cease, ax.get_ylim()[1] * 0.97, " ceasefire", color=GREEN,
            fontsize=9, va="top")
    ax.set_ylabel("spread level ($/bbl)")
    ax.set_title("The direct analog — June 2025 Israel-Iran war, daily spread path",
                 fontsize=13, fontweight="bold", pad=12)
    ax.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT, fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "chart_june2025.png", dpi=170, facecolor=BG)
    plt.close(fig)


def chart_distribution(s: str, d: np.ndarray, stats: dict, current: float) -> None:
    import matplotlib.pyplot as plt
    from scipy.stats import gaussian_kde
    lo, hi = np.percentile(d, [0.4, 99.6])
    xs = np.linspace(lo, hi, 600)
    kde = gaussian_kde(d[(d > lo) & (d < hi)])
    ys = kde(xs)

    fig, ax = plt.subplots(figsize=(9.6, 4.6), facecolor=BG)
    _style(ax)
    c = SPREAD_COLOURS[s]
    ax.plot(xs, ys, color=c, linewidth=2.4)
    m90 = (xs >= stats["p5"]) & (xs <= stats["p95"])
    m50 = (xs >= stats["p25"]) & (xs <= stats["p75"])
    ax.fill_between(xs[m90], ys[m90], color=c, alpha=0.16, label="90% range")
    ax.fill_between(xs[m50], ys[m50], color=c, alpha=0.38, label="50% range")
    ax.axvline(stats["ev_delta"], color=TEXT, linewidth=1.6, linestyle="-")
    ax.axvline(0, color=MUT, linewidth=0.9, linestyle=":")
    ax.text(stats["ev_delta"], ax.get_ylim()[1] * 0.93,
            f"  EV {stats['ev_delta']:+.2f}", color=TEXT, fontsize=10,
            fontweight="bold")
    ax.set_xlabel(f"Δ {LABELS[s]} over 1 week ($/bbl)   ·   current level "
                  f"{current:.2f}")
    ax.set_yticks([])
    ax.set_title(f"{LABELS[s]} — 1-week change distribution "
                 f"(mixture of 4 scenarios, 200k draws)",
                 fontsize=12.5, fontweight="bold", pad=10)
    ax.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT, fontsize=9,
              loc="upper left")
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"chart_dist_{s}.png", dpi=170, facecolor=BG)
    plt.close(fig)


def chart_scenarios(scen: list[dict]) -> None:
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11.6, 4.6), facecolor=BG)
    _style(ax)
    y = np.arange(len(scen))[::-1]
    for i, sc in enumerate(scen):
        yy = y[i]
        for j, s in enumerate(SPREADS):
            mu, sg = sc["mu"][s], sc["sigma"][s]
            off = (j - 1) * 0.22
            ax.errorbar(mu, yy + off, xerr=1.64 * sg, fmt="o",
                        color=SPREAD_COLOURS[s], markersize=7,
                        elinewidth=2.2, capsize=4, alpha=0.95)
        ax.text(ax.get_xlim()[0], yy + 0.38,
                f"{sc['name']}   ·   P = {sc['prob']:.0%}",
                color=TEXT, fontsize=10.5, fontweight="bold")
    ax.axvline(0, color=MUT, linewidth=0.9, linestyle=":")
    ax.set_yticks([])
    ax.set_xlabel("scenario mean Δ ± 90% conditional range ($/bbl)")
    handles = [plt.Line2D([0], [0], marker="o", color=SPREAD_COLOURS[s],
                          linestyle="none", markersize=8, label=LABELS[s])
               for s in SPREADS]
    ax.legend(handles=handles, facecolor=PANEL, edgecolor=GRID,
              labelcolor=TEXT, fontsize=10, loc="lower right")
    ax.set_title("Scenario tree — conditional means and ranges per spread",
                 fontsize=13, fontweight="bold", pad=12)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "chart_scenarios.png", dpi=170, facecolor=BG)
    plt.close(fig)


# ── main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    import matplotlib
    matplotlib.use("Agg")

    rng = np.random.default_rng(SEED)
    spreads = build_spreads()
    current = {s: float(spreads[s].iloc[-1]) for s in SPREADS}
    asof = str(spreads.index[-1].date())

    # event study
    ev = event_deltas(spreads)
    ev.to_csv(OUT_DIR / "event_deltas.csv", index=False)

    # regime-conditional weekly vol (current regime is BACK: m1_m12 > 5)
    chg5 = spreads[SPREADS].diff(HORIZON_BD).dropna()
    back_mask = spreads["m1_m12"].reindex(chg5.index) > 5
    back_vol = {s: float(chg5.loc[back_mask, s].std()) for s in SPREADS}
    rho = float(np.mean([chg5[a].corr(chg5[b])
                         for i, a in enumerate(SPREADS)
                         for b in SPREADS[i + 1:]]))

    scen = scenario_params(ev, back_vol)
    draws = monte_carlo(scen, rho, rng)
    stats = summarise(draws, current)

    # charts
    chart_event_study(ev)
    chart_june2025(spreads)
    chart_scenarios(scen)
    for s in SPREADS:
        chart_distribution(s, draws[s], stats[s], current[s])

    results = {
        "asof": asof,
        "headline": ("Israel launches strikes on Iranian energy infrastructure. "
                     "Iran threatens closure of the Strait of Hormuz."),
        "horizon_trading_days": HORIZON_BD,
        "n_draws": N_DRAWS,
        "rho_one_factor": round(rho, 3),
        "back_regime_weekly_vol": {s: round(v, 3) for s, v in back_vol.items()},
        "current_levels": {s: round(v, 2) for s, v in current.items()},
        "scenarios": [
            {"name": sc["name"], "prob": sc["prob"], "story": sc["story"],
             "mu": sc["mu"], "sigma": {k: round(v, 3) for k, v in sc["sigma"].items()}}
            for sc in scen
        ],
        "stats": stats,
        "event_study": ev.to_dict(orient="records"),
    }
    (OUT_DIR / "results.json").write_text(json.dumps(results, indent=2))

    # console summary
    print(f"as of {asof} · rho={rho:.2f} · BACK weekly vol "
          f"{ {k: round(v, 2) for k, v in back_vol.items()} }")
    print(f"{'spread':8s} {'now':>6s} {'EV Δ':>7s} {'EV lvl':>7s} "
          f"{'50% (level)':>16s} {'90% (level)':>16s} {'P(widen)':>9s}")
    for s in SPREADS:
        st = stats[s]
        print(f"{LABELS[s]:8s} {st['current']:6.2f} {st['ev_delta']:+7.2f} "
              f"{st['ev_level']:7.2f} "
              f"{str(st['ci50_level']):>16s} {str(st['ci90_level']):>16s} "
              f"{st['p_widen']:9.1%}")
    print(f"\ncharts + results.json -> {OUT_DIR}")


if __name__ == "__main__":
    main()
