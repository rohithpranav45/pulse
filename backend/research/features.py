"""
Point-in-time feature matrix for the regime regressions (Sprint 3).

Two-tier feature set so Brent cells aren't artificially shortened to the WTI
date range (Brent settle file: 2016-2026; WTI synth: 2021-2026):

  BRENT_FEATURES (10) — used for the 3 Brent spread cells
    m1_m12, m1_m12_sq, brent_close, brent_ret_5d, realised_vol_20d,
    inv_vs_5yr_pct, sin_doy, cos_doy,
    m1_m2_lag1, m3_m6_lag1, fly_lag1

  WTI_EXTRA_FEATURES (5) — appended for the 3 WTI spread cells
    wti_m1_m12, wti_close, wti_m1_m2_lag1, wti_m3_m6_lag1, wti_fly_lag1

`predictors_for(target_spread)` returns the right slice with the target's
own lag1 removed to prevent self-leakage.

Regime label is now COMPOSITE 3-axis (curve/inv/vol) — see regimes.py.
The 4-bucket legacy label is also surfaced as `regime_legacy` for the
existing UI scatter / drill modal.

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


BRENT_FEATURES = [
    "m1_m12", "m1_m12_sq",
    "brent_close", "brent_ret_5d",
    "realised_vol_20d",
    "inv_vs_5yr_pct",
    "sin_doy", "cos_doy",
    "m1_m2_lag1", "m3_m6_lag1", "fly_lag1",
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


def build_features() -> pd.DataFrame:
    """
    Return point-in-time feature matrix indexed by Brent settle dates.

    WTI columns are NaN before 2021 (WTI 1-min file starts then) — rows
    where WTI features are needed (i.e. training a WTI cell) drop those.
    Brent-only cells keep the full 2016+ history.
    """
    from data_lake import get_brent_settlements, get_wti_settlements
    from research.regimes         import classify_composite_series, classify_series, classify_pooled_series
    from research.spread_universe import build_spread_series
    from research.inventory_history import get_crude_stocks_history

    settle = get_brent_settlements()
    if settle is None or settle.empty:
        raise RuntimeError("Brent settlements missing")

    spreads = build_spread_series()
    df = pd.DataFrame(index=settle.index)

    # ── Brent curve features ────────────────────────────────────────────
    df["m1_m12"]    = settle["c1"] - settle["c12"]
    df["m1_m12_sq"] = df["m1_m12"] ** 2
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

    # ── WTI features (NaN pre-2021) ─────────────────────────────────────
    wti = get_wti_settlements()
    if wti is not None and not wti.empty:
        wti_aligned = wti.reindex(df.index)
        df["wti_close"]  = wti_aligned["c1"]
        df["wti_m1_m12"] = wti_aligned["c1"] - wti_aligned["c6"]  # WTI synth tops at c6
        df["wti_m1_m2_lag1"] = spreads["wti_m1_m2"].shift(1)
        df["wti_m3_m6_lag1"] = spreads["wti_m3_m6"].shift(1)
        df["wti_fly_lag1"]   = spreads["wti_fly_123"].shift(1)
        # Forward-fill WTI columns by ≤3 business days so live inference still
        # works when WTI synth data lags Brent's latest print by a session.
        for col in WTI_EXTRA_FEATURES:
            df[col] = df[col].ffill(limit=3)
    else:
        for col in WTI_EXTRA_FEATURES:
            df[col] = float("nan")

    # ── Inventory axis from EIA weekly history, forward-filled to daily ─
    inv = get_crude_stocks_history()
    if inv is not None and not inv.empty:
        inv_daily = inv["vs_5yr_pct"].reindex(df.index, method="ffill")
        df["inv_vs_5yr_pct"] = inv_daily
    else:
        df["inv_vs_5yr_pct"] = float("nan")

    # ── Composite regime label (3-axis) + legacy 4-bucket label ─────────
    # `regime`         — composite 3-axis (curve / inv / vol), Sprint 3 default
    # `regime_pooled`  — curve axis only, Phase 2.5 pooled mode
    # `regime_legacy`  — 4-bucket curve-only, retained for drill modal scatter
    df["regime"] = classify_composite_series(
        df["m1_m12"],
        df["inv_vs_5yr_pct"],
        df["realised_vol_20d"],
    )
    df["regime_pooled"] = classify_pooled_series(df["m1_m12"])
    df["regime_legacy"] = classify_series(df["m1_m12"])

    # ── Drop early rows missing the Brent base features ─────────────────
    # (WTI rows can stay NaN — they get filtered per-spread in training.)
    df = df.dropna(subset=BRENT_FEATURES)
    # Composite regime requires inv + vol both known
    df = df[df["regime"].apply(lambda s: "UNKNOWN" not in s)]
    return df


def predictors_for(target_spread: str) -> list[str]:
    """
    Predictor column list for a target spread.

    Brent spreads: BRENT_FEATURES minus self-lag.
    WTI spreads:   BRENT_FEATURES + WTI_EXTRA_FEATURES minus self-lag.

    Rationale: Brent cells train on 2016-2026 (~2,500 rows). WTI cells
    are inherently 2021-2026 (~1,400 rows) because the synth data starts
    then — including the wider WTI feature set doesn't cost extra rows.
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
    print("Top 10 composite regimes by count:")
    for r, n in df["regime"].value_counts().head(10).items():
        print(f"  {r:<25} {n:>5}")
    print()
    print(f"Total composite cells populated: {df['regime'].nunique()}")
    print()
    print("Latest row:")
    print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in df.iloc[-1].to_dict().items()})
