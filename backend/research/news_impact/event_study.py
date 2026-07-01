"""
News event study — what a headline FACTOR is worth, in % of Brent/WTI.
=====================================================================

Sprint 2. The corpus (corpus.py) is a timestamped, classified headline tape; this
module turns it into the empirical heart of the impact model — the same
conditional-reaction thesis as the inventory framework, but the event is a
headline instead of an EIA print:

  1. For every classified, timestamped headline, align the Brent/WTI tape to the
     headline minute and measure the FORWARD return at +1h / +4h / +1d.

  2. Give each headline a signed crude-polarity SENTIMENT in [-1, +1] (+1 =
     bullish *for crude*: draws, outages, sanctions, strong demand; -1 = bearish:
     builds, glut, ceasefires, demand destruction). Deterministic lexicon so the
     event study is reproducible (Groq can refine the *factor*; the polarity here
     stays auditable).

  3. Regress forward return on sentiment, PER FACTOR, gated by the curve regime
     (the inventory-framework move): slope = the per-factor beta — the % Brent
     move per +1 unit of sentiment magnitude — with its t-stat / R² / N.

De-meaning by baseline vol: the forward return is also expressed in vol units
(divided by trailing-20d Brent realised vol scaled to the horizon) so a 0.5% move
in a calm tape and a 0.5% move in a wild one aren't read as equal impact. The
headline beta stays in raw % (interpretable on a desk); the vol-normalised column
is reported alongside.

Honesty: most factors will NOT clear significance on a few-hundred-headline tape
with a noisy keyword sentiment — that's expected and reported as such (impact.py
falls back to a labelled prior when the measured beta isn't significant, exactly
like the per-spread gate). Where a factor *does* clear it (typically GEOPOLITICAL
/ SUPPLY_OPEC in the right regime), the beta is the tradeable read.

Public API
----------
  signed_sentiment(title)                 -> float in [-1, +1]
  build_event_panel(headlines=, frames=)  -> pd.DataFrame   one row per headline
  factor_betas(panel, horizon=, asset=)   -> dict           per-factor OLS betas
  factor_table(panel, horizon=)           -> list[dict]      tidy per-factor table
  compute_and_cache(force_refresh=)       -> dict            betas json (persisted)
  load_cached()                           -> dict | None

Run standalone:  python -m backend.research.news_impact.event_study
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

log = logging.getLogger("pulse.news_impact.event_study")

_CACHE = Path(__file__).parent.parent.parent / "data" / "research" / "news_impact"
_CACHE.mkdir(parents=True, exist_ok=True)
_BETAS_JSON = _CACHE / "news_impact_betas.json"

# forward windows after the headline minute
HORIZONS = ["1h", "4h", "1d"]
_HORIZON_TD = {"1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4), "1d": pd.Timedelta(days=1)}
_HORIZON_FRAC_DAY = {"1h": 1 / 24.0, "4h": 4 / 24.0, "1d": 1.0}   # for vol scaling
ASSETS = ["brent", "wti"]

# significance / sample floors used to *report* a beta as measured (impact.py gate)
MIN_N = 12
T_MIN = 2.0


# ── signed crude-polarity sentiment (deterministic lexicon) ───────────────────
# +weight = bullish for crude price (tightening / risk); -weight = bearish (easing
# / loosening). Whole-word matched with light inflection so "cut" catches "cuts".
_BULL_TERMS: tuple[str, ...] = (
    "draw", "drawdown", "deficit", "shortage", "outage", "disruption", "halt",
    "shutdown", "shut", "attack", "strike", "sanction", "embargo", "war",
    "escalation", "escalate", "cut", "curb", "force majeure", "blockade",
    "tighten", "tight", "surge", "rally", "jump", "spike", "soar", "climb",
    "rebound", "stimulus", "robust", "strong", "beat", "boost", "recovery",
    "freeze", "hurricane", "cold", "cyclone", "halts", "drone", "missile",
    "houthi", "tanker", "invasion", "wildfire", "explosion", "fire",
)
_BEAR_TERMS: tuple[str, ...] = (
    "build", "glut", "oversupply", "surplus", "ramp", "increase", "hike",
    "raise", "return", "resume", "restart", "ease", "eases", "ceasefire",
    "truce", "deal", "agreement", "recession", "slowdown", "slow", "weak",
    "weaken", "destruction", "slump", "plunge", "fall", "drop", "decline",
    "tumble", "slide", "bearish", "downgrade", "lockdown", "glutted", "flood",
    "ample", "record output", "record production", "overhang", "demand fears",
)


def _kw_hit(text: str, kw: str) -> bool:
    return re.search(r"\b" + re.escape(kw) + r"(?:s|es|d|ed|ing)?\b", text) is not None


def signed_sentiment(title: str) -> float:
    """
    Map a headline to a signed crude-polarity in [-1, +1]. +1 = bullish for crude
    (supply tightening / demand strength / risk premium); -1 = bearish (supply
    easing / demand weakness). 0 when the lexicon finds nothing either way.

    A deliberately simple, auditable proxy — the event-study sentiment-magnitude.
    NOT a learned sentiment model; impact.py is honest that this is a lexicon.
    """
    t = (title or "").lower()
    if not t:
        return 0.0
    bull = sum(1 for k in _BULL_TERMS if _kw_hit(t, k))
    bear = sum(1 for k in _BEAR_TERMS if _kw_hit(t, k))
    net = bull - bear
    if net == 0:
        return 0.0
    return float(np.tanh(0.5 * net))


# ── price tape ─────────────────────────────────────────────────────────────────
_FRAMES_CACHE: dict | None = None


def _load_price_frames(force_refresh: bool = False) -> dict:
    """
    Load the Brent/WTI tape once (cached): a 5-min intraday front-mid series per
    asset (for +1h/+4h), the daily Brent/WTI front settlement series (for +1d),
    a Brent c1/c2/c3 daily curve frame (curve regime), and trailing-20d Brent
    realised daily vol (baseline vol). All intraday series are UTC-indexed.
    """
    global _FRAMES_CACHE
    if _FRAMES_CACHE is not None and not force_refresh:
        return _FRAMES_CACHE

    import data_lake as dl
    con = dl.duckdb_conn()

    def _intraday(view: str) -> pd.Series:
        q = f'''
            SELECT time_bucket(INTERVAL '5 minutes', timestamp) AS ts,
                   last("c1||weighted_mid" ORDER BY timestamp) AS c1
            FROM {view}
            WHERE "c1||weighted_mid" IS NOT NULL
            GROUP BY 1 ORDER BY 1
        '''
        df = con.execute(q).df()
        idx = pd.to_datetime(df["ts"], utc=True)
        return pd.Series(df["c1"].astype(float).values, index=idx).sort_index()

    brent_intraday = _intraday("brent_1min")
    wti_intraday = _intraday("wti_1min")

    bd = con.execute(
        "SELECT date, c1, c2, c3 FROM brent_settlements_c1_to_c31 ORDER BY date"
    ).df()
    bd["date"] = pd.to_datetime(bd["date"])
    bd = bd.set_index("date")
    brent_daily = bd["c1"].astype(float)
    brent_curve = bd[["c1", "c2", "c3"]].astype(float)
    # trailing 20d realised vol of Brent front, in daily % units
    rvol = (brent_daily.pct_change() * 100.0).rolling(20).std()

    wti_settl = dl.get_wti_settlements()
    if wti_settl is not None and "c1" in wti_settl.columns:
        wti_daily = wti_settl["c1"].astype(float)
        wti_daily.index = pd.to_datetime(wti_daily.index)
    else:
        wti_daily = pd.Series(dtype=float)

    _FRAMES_CACHE = {
        "brent_intraday": brent_intraday,
        "wti_intraday": wti_intraday,
        "brent_daily": brent_daily,
        "wti_daily": wti_daily,
        "brent_curve": brent_curve,
        "rvol": rvol,
    }
    return _FRAMES_CACHE


def _asof(s: pd.Series, ts: pd.Timestamp, max_gap_min: int = 90) -> float | None:
    """Last value at index <= ts, but only if that bar is within max_gap_min of ts
    (so a headline in an overnight/weekend gap returns None rather than a stale mid)."""
    if s is None or len(s) == 0:
        return None
    pos = s.index.searchsorted(ts, side="right") - 1
    if pos < 0:
        return None
    idx = s.index[pos]
    if (ts - idx) > pd.Timedelta(minutes=max_gap_min):
        return None
    return float(s.iloc[pos])


def _fwd_intraday(s: pd.Series, t: pd.Timestamp, h: str) -> float | None:
    """Forward % return on an intraday series from t to t+h (both asof-matched)."""
    p0 = _asof(s, t)
    p1 = _asof(s, t + _HORIZON_TD[h])
    if p0 is None or p1 is None or p0 == 0:
        return None
    return (p1 / p0 - 1.0) * 100.0


def _fwd_daily(daily: pd.Series, t: pd.Timestamp) -> float | None:
    """+1d return: close-to-close across the headline day (prior settle → next settle).

    anchor = last settlement strictly before the headline's UTC date; post = first
    settlement on/after it. Captures the move over the headline day (or the next
    session if the headline lands on a weekend/holiday). None if either side is
    missing or the gap exceeds 4 calendar days (no nearby trading day)."""
    if daily is None or len(daily) == 0:
        return None
    d = pd.Timestamp(t.tz_convert("UTC").date()) if t.tzinfo else pd.Timestamp(t.date())
    idx = daily.index
    post_pos = idx.searchsorted(d, side="left")
    prior_pos = post_pos - 1
    if prior_pos < 0 or post_pos >= len(idx):
        return None
    pre, post = float(daily.iloc[prior_pos]), float(daily.iloc[post_pos])
    if (idx[post_pos] - d).days > 4 or (d - idx[prior_pos]).days > 4 or pre == 0:
        return None
    return (post / pre - 1.0) * 100.0


def _curve_regime(curve: pd.DataFrame, t: pd.Timestamp) -> str:
    """Brent curve regime at the headline date: BACK if front (c1) > c3, else
    CONTANGO. Uses the last settled curve on/before the headline's date."""
    if curve is None or len(curve) == 0:
        return "CONTANGO"
    d = pd.Timestamp(t.tz_convert("UTC").date()) if t.tzinfo else pd.Timestamp(t.date())
    pos = curve.index.searchsorted(d, side="right") - 1
    if pos < 0:
        return "CONTANGO"
    row = curve.iloc[pos]
    return "BACK" if float(row["c1"]) > float(row["c3"]) else "CONTANGO"


def _baseline_vol(rvol: pd.Series, t: pd.Timestamp) -> float | None:
    if rvol is None or len(rvol) == 0:
        return None
    d = pd.Timestamp(t.tz_convert("UTC").date()) if t.tzinfo else pd.Timestamp(t.date())
    pos = rvol.index.searchsorted(d, side="right") - 1
    if pos < 0:
        return None
    v = rvol.iloc[pos]
    return float(v) if pd.notna(v) and v > 0 else None


# ── the panel ────────────────────────────────────────────────────────────────
def _load_classified_headlines() -> list[dict]:
    """Classified headlines with a usable timestamp, from the corpus."""
    from . import corpus
    rows = corpus.recent(limit=500000)
    return [r for r in rows
            if r.get("factor") and r.get("published_at")]


def build_event_panel(headlines: list[dict] | None = None,
                      frames: dict | None = None) -> pd.DataFrame:
    """
    One row per classified, timestamped headline. Columns:
      published_at, factor, factor_conf, sentiment,
      curve {BACK,CONTANGO}, baseline_vol,
      fwd_<asset>_<h>      raw forward % return  (asset∈{brent,wti}, h∈HORIZONS)
      vn_<asset>_<h>       vol-normalised forward return (move / horizon-scaled vol)

    `headlines` / `frames` are injectable for hermetic tests; default to the live
    corpus + /Data tape.
    """
    if headlines is None:
        headlines = _load_classified_headlines()
    if frames is None:
        frames = _load_price_frames()

    bi, wi = frames["brent_intraday"], frames["wti_intraday"]
    bdaily, wdaily = frames["brent_daily"], frames["wti_daily"]
    curve, rvol = frames["brent_curve"], frames["rvol"]
    intraday = {"brent": bi, "wti": wi}
    daily = {"brent": bdaily, "wti": wdaily}

    rows = []
    for r in headlines:
        ts = pd.to_datetime(r["published_at"], utc=True, errors="coerce")
        if pd.isna(ts):
            continue
        rec: dict = {
            "published_at": ts,
            "factor": r["factor"],
            "factor_conf": r.get("factor_conf"),
            "sentiment": signed_sentiment(r.get("title", "")),
            "curve": _curve_regime(curve, ts),
            "baseline_vol": _baseline_vol(rvol, ts),
        }
        any_ret = False
        for asset in ASSETS:
            for h in HORIZONS:
                ret = (_fwd_daily(daily[asset], ts) if h == "1d"
                       else _fwd_intraday(intraday[asset], ts, h))
                rec[f"fwd_{asset}_{h}"] = ret
                vol = rec["baseline_vol"]
                if ret is not None and vol:
                    scale = vol * np.sqrt(_HORIZON_FRAC_DAY[h])
                    rec[f"vn_{asset}_{h}"] = ret / scale if scale else None
                else:
                    rec[f"vn_{asset}_{h}"] = None
                any_ret = any_ret or ret is not None
        if any_ret:
            rows.append(rec)

    panel = pd.DataFrame(rows)
    if not panel.empty:
        panel = panel.set_index("published_at").sort_index()
    return panel


# ── regressions ──────────────────────────────────────────────────────────────
def _ols(x: np.ndarray, y: np.ndarray, min_n: int = 8) -> dict | None:
    """OLS slope of y~x with t-stat, R², corr. None when too few points / no x var."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    n = len(x)
    if n < min_n or np.std(x) == 0:
        return None
    sx, sy = x - x.mean(), y - y.mean()
    slope = float((sx * sy).sum() / (sx ** 2).sum())
    intercept = float(y.mean() - slope * x.mean())
    yhat = intercept + slope * x
    ss_res = float(((y - yhat) ** 2).sum())
    ss_tot = float((sy ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    se = float(np.sqrt(ss_res / (n - 2) / (sx ** 2).sum())) if n > 2 else np.nan
    t = slope / se if se and se > 0 else np.nan
    corr = float(np.corrcoef(x, y)[0, 1]) if np.std(y) > 0 else 0.0
    return {"slope": round(slope, 4), "t": round(t, 2) if np.isfinite(t) else None,
            "r2": round(r2, 3), "n": n, "corr": round(corr, 3)}


def factor_betas(panel: pd.DataFrame, horizon: str = "1d", asset: str = "brent") -> dict:
    """
    Per-factor OLS of forward return on sentiment, overall + by curve regime.
    Each entry also carries the sentiment-aligned mean move + hit-rate (a robust
    cross-check that doesn't lean on the regression slope).
    """
    out: dict = {}
    if panel is None or panel.empty:
        return out
    col = f"fwd_{asset}_{horizon}"
    if col not in panel.columns:
        return out
    for factor in sorted(panel["factor"].dropna().unique()):
        sub = panel[panel["factor"] == factor]
        entry = {"overall": _ols(sub["sentiment"].values, sub[col].values, MIN_N)}
        # sentiment-aligned mean move (sign of sentiment × move) — direction-free magnitude
        aligned = (np.sign(sub["sentiment"].values) * sub[col].values)
        finite = aligned[np.isfinite(aligned)]
        entry["aligned_mean_move"] = round(float(np.mean(finite)), 4) if len(finite) else None
        entry["aligned_hit_rate"] = round(float(np.mean(finite > 0)), 3) if len(finite) else None
        entry["n_total"] = int(sub[col].notna().sum())
        for reg in ("BACK", "CONTANGO"):
            rs = sub[sub["curve"] == reg]
            entry[reg] = _ols(rs["sentiment"].values, rs[col].values, MIN_N)
        out[factor] = entry
    return out


def factor_table(panel: pd.DataFrame, horizon: str = "1d") -> list[dict]:
    """
    Tidy per-factor row for the API / standalone: the Brent beta + significance,
    the WTI beta, the sentiment-aligned magnitude, and the curve-regime split.
    """
    bb = factor_betas(panel, horizon, "brent")
    wb = factor_betas(panel, horizon, "wti")
    rows = []
    for factor in sorted(bb):
        e = bb[factor]
        o = e.get("overall") or {}
        we = (wb.get(factor) or {}).get("overall") or {}
        t = o.get("t")
        rows.append({
            "factor": factor,
            "horizon": horizon,
            "n": e.get("n_total", 0),
            "beta_brent_pct": o.get("slope"),
            "t_brent": t,
            "r2_brent": o.get("r2"),
            "beta_wti_pct": we.get("slope"),
            "t_wti": we.get("t"),
            "aligned_mean_move": e.get("aligned_mean_move"),
            "aligned_hit_rate": e.get("aligned_hit_rate"),
            "significant": bool(t is not None and abs(t) >= T_MIN and e.get("n_total", 0) >= MIN_N),
            "by_curve": {
                "BACK": (e.get("BACK") or {}),
                "CONTANGO": (e.get("CONTANGO") or {}),
            },
        })
    # most significant / highest-|beta| first
    rows.sort(key=lambda r: (r["significant"], abs(r["t_brent"] or 0)), reverse=True)
    return rows


# ── cache (the API reads this; recompute via standalone / compute_and_cache) ──
def compute_and_cache(force_refresh: bool = False, horizon: str = "1d") -> dict:
    """Build the panel from the live corpus + tape, compute the per-factor table at
    each horizon, and persist to news_impact_betas.json for the API to serve."""
    panel = build_event_panel(frames=_load_price_frames(force_refresh))
    tables = {h: factor_table(panel, h) for h in HORIZONS}
    span = None
    if not panel.empty:
        span = [str(panel.index.min().date()), str(panel.index.max().date())]
    by_factor = (panel["factor"].value_counts().to_dict() if not panel.empty else {})
    out = {
        "available": not panel.empty,
        "n_headlines": int(len(panel)),
        "span": span,
        "by_factor": {k: int(v) for k, v in by_factor.items()},
        "headline_horizon": horizon,
        "horizons": HORIZONS,
        "min_n": MIN_N,
        "t_min": T_MIN,
        "tables": tables,
        "factors": tables.get(horizon, []),
        "source": "backend/research/news_impact/event_study",
    }
    try:
        _BETAS_JSON.write_text(json.dumps(out, indent=2))
    except Exception as exc:
        log.warning("could not cache news betas: %s", exc)
    return out


def load_cached() -> dict | None:
    if not _BETAS_JSON.exists():
        return None
    try:
        return json.loads(_BETAS_JSON.read_text())
    except Exception:
        return None


# ── standalone ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    pd.set_option("display.width", 180)
    pd.set_option("display.max_columns", 30)

    print("Building news event panel (corpus × /Data tape)…")
    panel = build_event_panel()
    if panel.empty:
        print("EMPTY panel — corpus has no classified, timestamped headlines with "
              "price coverage yet. Run the backfill + classify first.")
        raise SystemExit(0)

    print(f"\nHeadlines in panel: {len(panel)}  "
          f"({panel.index.min().date()} .. {panel.index.max().date()})")
    print("by factor:")
    for f, n in panel["factor"].value_counts().items():
        print(f"  {f:18s} {n}")

    def _f(v, fmt="{:+.3f}"):
        return fmt.format(v) if isinstance(v, (int, float)) else "  n/a"

    for h in HORIZONS:
        print(f"\n=== Per-factor beta: sentiment → Brent {h} forward return (%) ===")
        tbl = factor_table(panel, h)
        for r in tbl:
            sig = "  *SIGNIFICANT*" if r["significant"] else ""
            print(f"  {r['factor']:18s} n={r['n']:4d}  "
                  f"β={_f(r['beta_brent_pct'])}%/unit  t={r['t_brent']}  r²={r['r2_brent']}  "
                  f"aligned={_f(r['aligned_mean_move'])}% hit={r['aligned_hit_rate']}{sig}")

    out = compute_and_cache()
    print(f"\ncached -> {_BETAS_JSON}  (available={out['available']}, n={out['n_headlines']})")
