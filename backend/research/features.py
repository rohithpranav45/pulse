"""
Point-in-time feature matrix for the regime regressions.

Two-tier feature set so Brent cells aren't artificially shortened to the WTI
date range (Brent settle file: 2016-2026; WTI synth: 2021-2026):

  BRENT_FEATURES — Brent-cell predictors (curve + macro + seasonality
                   + lagged spreads + Phase 2.8.2 alpha features).
  WTI_EXTRA_FEATURES — additional WTI-specific predictors appended for
                       the 3 WTI spread cells.

`predictors_for(target_spread)` returns the right slice with the target's
own lag1 removed to prevent self-leakage.

Regime label is COMPOSITE 3-axis (curve / inv / vol) — see regimes.py.
The 4-bucket legacy label is also surfaced as `regime_legacy` for the
existing UI scatter / drill modal, and the curve-only pooled label as
`regime_pooled` for Phase 2.5.

Phase 2.8.2 — added alpha-bearing features so the per-cell competition has
more to work with:
  curvature        : c1 - 2*c6 + c12 (fly-specific curve information)
  inv_surprise     : weekly inventory Δ minus its 4-week MA (alpha is in
                     the surprise, not the level)
  cot_mm_pct_156w  : Managed-money net positioning percentile (rolling
                     156-week window) — crowdedness contrarian indicator
  crack_321        : 3-2-1 refining margin proxy (RBOB/HO crack)
  gasoline_crack   : RBOB - WTI gasoline margin
  wti_brent_spread : Atlantic-basin arb width
  real_rate        : 10y nominal minus 5y breakeven (storage-economics
                     proxy; carry is a function of real rates)
  ovx_vix_ratio    : crude IV / equity IV — risk-premium signal
  days_to_expiry   : business days to front-month roll

Public API
----------
  build_features() → pd.DataFrame indexed by date, all feature cols + 'regime'
  predictors_for(spread) → list[str]
  BRENT_FEATURES, WTI_EXTRA_FEATURES → list[str]
"""

from __future__ import annotations

import os, sys
import numpy as np
import pandas as pd

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# Brent-cell predictors. Phase 2.8.2 additions in trailing block.
BRENT_FEATURES = [
    # Curve shape
    "m1_m12", "m1_m12_sq", "curvature",
    # Front-month state
    "brent_close", "brent_ret_5d",
    # Realised vol
    "realised_vol_20d",
    # Inventory (level + surprise)
    "inv_vs_5yr_pct", "inv_surprise",
    # Seasonality
    "sin_doy", "cos_doy",
    # Lagged spreads
    "m1_m2_lag1", "m3_m6_lag1", "fly_lag1",
    # Phase 2.8.2 alpha features
    "cot_mm_pct_156w",
    "crack_321", "gasoline_crack",
    "wti_brent_spread",
    "real_rate", "ovx_vix_ratio",
    "days_to_expiry",
]

WTI_EXTRA_FEATURES = [
    "wti_m1_m12", "wti_close",
    "wti_m1_m2_lag1", "wti_m3_m6_lag1", "wti_fly_lag1",
]

# Mapping from target spread → its own lag1 column (dropped to avoid self-leakage)
_SELF_LAGS = {
    "brent_m1_m2":   "m1_m2_lag1",
    "brent_m3_m6":   "m3_m6_lag1",
    "brent_fly_123": "fly_lag1",
    "wti_m1_m2":     "wti_m1_m2_lag1",
    "wti_m3_m6":     "wti_m3_m6_lag1",
    "wti_fly_123":   "wti_fly_lag1",
}


def _days_to_front_expiry(idx: pd.DatetimeIndex) -> pd.Series:
    """
    Business days to the next front-month Brent roll. Brent contracts expire
    on the last business day of the second month preceding the delivery
    month — but for a feature we only need a *consistent* roll proxy. We use
    the 25th of each calendar month as an approximate expiry; on/after the
    25th the active front contract has rolled, so we measure to the 25th of
    the following month. Returned in trading days (np.busday_count).
    """
    out = []
    idx = pd.DatetimeIndex(idx)
    for d in idx:
        py, pm = d.year, d.month
        if d.day < 25:
            ey, em = py, pm
        else:
            if pm == 12:
                ey, em = py + 1, 1
            else:
                ey, em = py, pm + 1
        expiry = pd.Timestamp(year=ey, month=em, day=25)
        try:
            bd = np.busday_count(d.date(), expiry.date())
        except Exception:
            bd = max(0, (expiry - d).days)
        out.append(int(max(0, bd)))
    return pd.Series(out, index=idx, dtype="float64")


def build_features() -> pd.DataFrame:
    """
    Return point-in-time feature matrix indexed by Brent settle dates.

    WTI columns are NaN before 2021 (WTI 1-min file starts then) — rows
    where WTI features are needed (i.e. training a WTI cell) drop those.
    Brent-only cells keep the full 2016+ history.

    Phase 2.8.2 features (COT, cracks, real rate, ovx_vix, etc.) are
    forward-filled from their weekly/daily sources, with early rows missing
    these features being dropped. Net effect on usable rows is small because
    the COT and cracks history both start ≤ 2014.
    """
    from data_lake import get_brent_settlements, get_wti_settlements
    from research.regimes         import classify_composite_series, classify_series, classify_pooled_series
    from research.spread_universe import build_spread_series
    from research.inventory_history import get_crude_stocks_history
    from research.cot_history       import get_cot_history
    from research.external_history  import get_external_history

    settle = get_brent_settlements()
    if settle is None or settle.empty:
        raise RuntimeError("Brent settlements missing")

    spreads = build_spread_series()
    df = pd.DataFrame(index=settle.index)

    # ── Brent curve features ────────────────────────────────────────────
    df["m1_m12"]    = settle["c1"] - settle["c12"]
    df["m1_m12_sq"] = df["m1_m12"] ** 2
    # Phase 2.8.2: butterfly-style curvature — captures kink information
    # that flat M1-M12 misses, useful for fly-specific cells.
    if "c6" in settle.columns:
        df["curvature"] = settle["c1"] - 2 * settle["c6"] + settle["c12"]
    else:
        df["curvature"] = float("nan")

    df["brent_close"]  = settle["c1"]
    df["brent_ret_5d"] = settle["c1"].pct_change(5)

    log_ret = np.log(settle["c1"] / settle["c1"].shift(1))
    df["realised_vol_20d"] = log_ret.rolling(20).std() * np.sqrt(252)

    day_of_year = pd.Series(df.index.dayofyear, index=df.index)
    df["sin_doy"] = np.sin(2 * np.pi * day_of_year / 365.25)
    df["cos_doy"] = np.cos(2 * np.pi * day_of_year / 365.25)

    df["m1_m2_lag1"] = spreads["brent_m1_m2"].shift(1)
    df["m3_m6_lag1"] = spreads["brent_m3_m6"].shift(1)
    df["fly_lag1"]   = spreads["brent_fly_123"].shift(1)

    # ── Days to front-month expiry (Phase 2.8.2) ────────────────────────
    df["days_to_expiry"] = _days_to_front_expiry(df.index)

    # ── WTI features (NaN pre-2021) ─────────────────────────────────────
    wti = get_wti_settlements()
    if wti is not None and not wti.empty:
        wti_aligned = wti.reindex(df.index)
        df["wti_close"]  = wti_aligned["c1"]
        df["wti_m1_m12"] = wti_aligned["c1"] - wti_aligned["c6"]  # WTI synth tops at c6
        df["wti_m1_m2_lag1"] = spreads["wti_m1_m2"].shift(1)
        df["wti_m3_m6_lag1"] = spreads["wti_m3_m6"].shift(1)
        df["wti_fly_lag1"]   = spreads["wti_fly_123"].shift(1)
        for col in WTI_EXTRA_FEATURES:
            df[col] = df[col].ffill(limit=3)
    else:
        for col in WTI_EXTRA_FEATURES:
            df[col] = float("nan")

    # ── Inventory level + surprise from EIA weekly history ──────────────
    inv = get_crude_stocks_history()
    if inv is not None and not inv.empty:
        inv_local = inv.copy()
        inv_local["weekly_delta"] = inv_local["crude_stocks"].diff()
        # 4-week mean of the prior changes (shift 1 to exclude current week
        # so the feature is purely point-in-time at the release date).
        inv_local["expected_delta"] = inv_local["weekly_delta"].shift(1).rolling(4).mean()
        inv_local["inv_surprise"]   = inv_local["weekly_delta"] - inv_local["expected_delta"]
        # Forward-fill weekly observations onto daily Brent index.
        inv_daily_pct = inv_local["vs_5yr_pct"].reindex(df.index, method="ffill")
        inv_daily_surp = inv_local["inv_surprise"].reindex(df.index, method="ffill")
        df["inv_vs_5yr_pct"] = inv_daily_pct
        df["inv_surprise"]   = inv_daily_surp
    else:
        df["inv_vs_5yr_pct"] = float("nan")
        df["inv_surprise"]   = float("nan")

    # ── COT managed-money percentile (Phase 2.8.2) ──────────────────────
    cot = get_cot_history()
    if cot is not None and not cot.empty:
        cot_pct = cot["cot_mm_pct_156w"].reindex(df.index, method="ffill")
        df["cot_mm_pct_156w"] = cot_pct
    else:
        df["cot_mm_pct_156w"] = float("nan")

    # ── External history: crack, wti_brent, real_rate, ovx_vix ─────────
    ext = get_external_history()
    if ext is not None and not ext.empty:
        for col in ("crack_321", "gasoline_crack", "wti_brent_spread",
                    "real_rate", "ovx_vix_ratio"):
            if col in ext.columns:
                df[col] = ext[col].reindex(df.index, method="ffill")
            else:
                df[col] = float("nan")
    else:
        for col in ("crack_321", "gasoline_crack", "wti_brent_spread",
                    "real_rate", "ovx_vix_ratio"):
            df[col] = float("nan")

    # ── Composite regime label (3-axis) + legacy 4-bucket label ─────────
    df["regime"] = classify_composite_series(
        df["m1_m12"],
        df["inv_vs_5yr_pct"],
        df["realised_vol_20d"],
    )
    df["regime_pooled"] = classify_pooled_series(df["m1_m12"])
    df["regime_legacy"] = classify_series(df["m1_m12"])

    # ── Drop early rows missing the Brent base features ─────────────────
    # Phase 2.8.2 adds features whose history is bounded by external
    # series start dates (COT 2014, FRED T5YIE 2003, OVX 2007). The Brent
    # settle file starts 2016 so the binding constraint is COT (156-week
    # rolling percentile requires ~3y of data → first valid date ≈ 2017).
    # Drop here so downstream training doesn't lose rows silently.
    df = df.dropna(subset=BRENT_FEATURES)
    # Composite regime requires inv + vol both known
    df = df[df["regime"].apply(lambda s: "UNKNOWN" not in s)]
    return df


def predictors_for(target_spread: str) -> list[str]:
    """
    Predictor column list for a target spread.

    Brent spreads: BRENT_FEATURES minus self-lag.
    WTI spreads:   BRENT_FEATURES + WTI_EXTRA_FEATURES minus self-lag.
    """
    if target_spread.startswith("wti_"):
        base = BRENT_FEATURES + WTI_EXTRA_FEATURES
    else:
        base = list(BRENT_FEATURES)
    self_lag = _SELF_LAGS.get(target_spread)
    if self_lag in base:
        base = [c for c in base if c != self_lag]
    return base


if __name__ == "__main__":
    df = build_features()
    print(f"Feature matrix: {df.shape[0]} rows x {df.shape[1]} cols")
    print(f"Date range: {df.index.min().date()} to {df.index.max().date()}")
    print()
    print("Columns:", list(df.columns))
    print()
    # NaN audit per feature
    print("=== NaN audit (post-build) ===")
    nans = df[BRENT_FEATURES + WTI_EXTRA_FEATURES].isna().sum()
    for col in BRENT_FEATURES + WTI_EXTRA_FEATURES:
        n = int(nans.get(col, 0))
        if n > 0:
            print(f"  {col:<22} {n:>5} NaN ({n/len(df)*100:.1f}%)")
    print()
    print("Top 10 composite regimes by count:")
    for r, n in df["regime"].value_counts().head(10).items():
        print(f"  {r:<25} {n:>5}")
    print()
    print(f"Total composite cells populated: {df['regime'].nunique()}")
    print()
    print("Latest row:")
    for k, v in df.iloc[-1].to_dict().items():
        if isinstance(v, float):
            v = round(v, 3)
        print(f"  {k:<22} {v}")
