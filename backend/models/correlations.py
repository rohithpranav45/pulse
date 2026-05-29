"""
Correlation analysis for the PULSE dashboard.

Three public functions:
  get_correlation_matrix()    — 30-day vs 252-day cross-asset correlation with
                                interpretation for five key pairs
  get_curve_correlation()     — Brent vs WTI futures-curve shape correlation
  get_brent_wti_analysis()    — Brent-WTI spread z-score and regime detection

Historical data note:
  load_historical() uses title-case keys: 'Brent', 'WTI', 'HH', 'DXY', 'SPX'.
  All output dicts use lowercase snake_case keys.
"""
import os as _os, sys as _sys
_BACKEND = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))
if _BACKEND not in _sys.path:
    _sys.path.insert(0, _BACKEND)

import sys
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# ── internal key mapping: historical title-case → output snake_case ──────────
_HIST_TO_SNAKE = {
    "Brent": "brent",
    "WTI":   "wti",
    "HH":    "hh",
    "DXY":   "dxy",
    "SPX":   "spx",
}

# ── pair interpretation rules ─────────────────────────────────────────────────
# Each pair maps to:
#   "normal_range": (lo, hi)         — expected historical correlation range
#   "rules": [(predicate, status, interpretation), ...]
#             Evaluated in order; first matching predicate wins.
#
# Predicate signature: (current_corr: float, hist_corr: float) -> bool

PAIR_INTERPRETATIONS = {
    ("brent", "dxy"): {
        "normal_range": (-0.80, -0.50),
        "rules": [
            (lambda c, h: c > -0.30,
             "BROKEN",
             "Oil rising WITH dollar — supply shock overriding FX relationship"),
            (lambda c, h: c > -0.45,
             "DRIFTING",
             "Dollar-oil inverse link weakening — monitor closely"),
            (lambda c, h: True,
             "NORMAL",
             "Dollar-oil inverse relationship intact and functioning"),
        ],
    },
    ("brent", "spx"): {
        "normal_range": (0.40, 0.80),
        "rules": [
            (lambda c, h: c < 0.20,
             "BROKEN",
             "Oil decoupled from equities — commodity-specific driver dominant"),
            (lambda c, h: c > 0.90,
             "BROKEN",
             "Unusually high correlation — macro risk driving everything together"),
            (lambda c, h: True,
             "NORMAL",
             "Oil tracking equity risk sentiment normally"),
        ],
    },
    ("brent", "wti"): {
        "normal_range": (0.85, 0.99),
        "rules": [
            (lambda c, h: c < 0.80,
             "BROKEN",
             "Unusual Brent-WTI divergence — regional supply driver active"),
            (lambda c, h: True,
             "NORMAL",
             "Brent and WTI moving in sync — no regional signal"),
        ],
    },
    ("brent", "hh"): {
        "normal_range": (0.10, 0.50),
        "rules": [
            (lambda c, h: c > 0.60,
             "DRIFTING",
             "Oil-gas correlation elevated — unified energy demand driver"),
            (lambda c, h: c < -0.10,
             "DRIFTING",
             "Oil and gas moving inversely — fuel switching signal"),
            (lambda c, h: True,
             "NORMAL",
             "Oil-gas correlation within normal range"),
        ],
    },
    ("dxy", "spx"): {
        "normal_range": (-0.70, -0.30),
        "rules": [
            (lambda c, h: c > 0.10,
             "BROKEN",
             "Dollar rising WITH stocks — unusual, suggests non-US risk driver"),
            (lambda c, h: True,
             "NORMAL",
             "Dollar-equity inverse relationship normal (risk-off = strong USD)"),
        ],
    },
}


def _corr_matrix_to_dict(df: pd.DataFrame) -> dict:
    """Convert a pandas correlation DataFrame to a nested plain dict."""
    return {
        row: {col: round(float(df.loc[row, col]), 4)
              for col in df.columns if col != row}
        for row in df.index
    }


# ─────────────────────────────────────────────────────────────────────────────
# FUNCTION 1 — Cross-asset correlation matrix
# ─────────────────────────────────────────────────────────────────────────────

def get_correlation_matrix() -> dict:
    """
    Compare 30-day and 252-day cross-asset return correlations and flag
    pairs whose recent behaviour deviates significantly from history.

    Assets: Brent, WTI, Henry Hub (HH), DXY, S&P 500 (SPX).

    Returns
    -------
    {
      "matrix":             dict  — 30-day pairwise correlations
      "historical_matrix":  dict  — 252-day pairwise correlations
      "pairs": {
        "brent_dxy": {
          "current":          float,
          "historical":       float,
          "deviation":        float,
          "status":           str,   NORMAL / DRIFTING / BROKEN
          "interpretation":   str,
          "significant_change": bool,
        }, ...
      },
      "alerts":     list[str]  — pair keys whose status == "BROKEN"
      "timestamp":  str
    }
    """
    from fetchers.historical import load_historical

    hist = load_historical()

    # ── build aligned returns DataFrame ──────────────────────────────────────
    returns_dict = {}
    for hist_key, snake_key in _HIST_TO_SNAKE.items():
        series = hist[hist_key]["Close"].pct_change().dropna()
        returns_dict[snake_key] = series

    returns_df = pd.DataFrame(returns_dict).dropna()

    # ── correlation matrices ──────────────────────────────────────────────────
    current_corr_df = returns_df.tail(30).corr()
    hist_corr_df    = returns_df.tail(252).corr()

    matrix            = _corr_matrix_to_dict(current_corr_df)
    historical_matrix = _corr_matrix_to_dict(hist_corr_df)

    # ── per-pair analysis ─────────────────────────────────────────────────────
    pairs  = {}
    alerts = []

    for (a, b), cfg in PAIR_INTERPRETATIONS.items():
        try:
            current_val = float(current_corr_df.loc[a, b])
            hist_val    = float(hist_corr_df.loc[a, b])
        except KeyError:
            continue

        deviation = round(current_val - hist_val, 4)

        # Apply rules — first matching wins
        status = "NORMAL"
        interpretation = ""
        for predicate, s, interp in cfg["rules"]:
            if predicate(current_val, hist_val):
                status        = s
                interpretation = interp
                break

        pair_key = f"{a}_{b}"
        pairs[pair_key] = {
            "current":            round(current_val, 4),
            "historical":         round(hist_val, 4),
            "deviation":          deviation,
            "status":             status,
            "interpretation":     interpretation,
            "significant_change": abs(deviation) > 0.20,
        }

        if status == "BROKEN":
            alerts.append(pair_key)

    return {
        "matrix":             matrix,
        "historical_matrix":  historical_matrix,
        "pairs":              pairs,
        "alerts":             alerts,
        "timestamp":          datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# FUNCTION 2 — Curve-shape correlation (Brent vs WTI futures strip)
# ─────────────────────────────────────────────────────────────────────────────

def get_curve_correlation() -> dict:
    """
    Compare the shape of the Brent and WTI futures curves (M1-M12).

    Uses the ordered price lists from each curve to measure how similarly
    the two strips are pricing future supply.

    Returns
    -------
    {
      "curve_correlation": float,
      "brent_slope":       float,   last_price - first_price
      "wti_slope":         float,
      "avg_spread":        float,   mean(brent - wti) across tenors
      "spread_std":        float,   std of tenor spreads
      "spreads_by_tenor":  list[dict],  {tenor, brent, wti, spread}
      "interpretation":    str,
      "timestamp":         str,
    }
    """
    from fetchers.curve import get_both_curves

    curves = get_both_curves()

    brent_curve = curves["brent"]["curve"]   # {tenor_label: price}
    wti_curve   = curves["wti"]["curve"]

    # Align on shared tenor labels (both ordered dicts, built in parallel)
    shared_labels = [lbl for lbl in brent_curve if lbl in wti_curve]

    brent_prices = [brent_curve[lbl] for lbl in shared_labels]
    wti_prices   = [wti_curve[lbl]   for lbl in shared_labels]

    if len(brent_prices) < 2:
        return {
            "curve_correlation": None,
            "brent_slope": None,
            "wti_slope":   None,
            "avg_spread":  None,
            "spread_std":  None,
            "spreads_by_tenor": [],
            "interpretation": "Insufficient curve data",
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    correlation  = float(np.corrcoef(brent_prices, wti_prices)[0, 1])
    spreads      = [b - w for b, w in zip(brent_prices, wti_prices)]
    spread_std   = float(np.std(spreads))
    spread_mean  = float(np.mean(spreads))
    brent_slope  = brent_prices[-1] - brent_prices[0]
    wti_slope    = wti_prices[-1]   - wti_prices[0]

    # ── interpretation ────────────────────────────────────────────────────────
    if spread_std > 0.8 and brent_slope < wti_slope:
        interpretation = (
            "Brent curve significantly flatter than WTI — "
            "Middle East supply tightness is regional, not global"
        )
    elif spread_std > 0.8 and wti_slope < brent_slope:
        interpretation = (
            "WTI curve flatter than Brent — "
            "US domestic supply tightening relative to global"
        )
    elif correlation > 0.98:
        interpretation = (
            "Curves highly correlated and parallel — "
            "global supply dynamics uniform across regions"
        )
    else:
        interpretation = (
            "Minor curve divergence — "
            "monitor for regional supply development"
        )

    spreads_by_tenor = [
        {
            "tenor":  lbl,
            "brent":  round(bp, 3),
            "wti":    round(wp, 3),
            "spread": round(bp - wp, 3),
        }
        for lbl, bp, wp in zip(shared_labels, brent_prices, wti_prices)
    ]

    return {
        "curve_correlation":  round(correlation, 4),
        "brent_slope":        round(brent_slope,  3),
        "wti_slope":          round(wti_slope,    3),
        "avg_spread":         round(spread_mean,  3),
        "spread_std":         round(spread_std,   3),
        "spreads_by_tenor":   spreads_by_tenor,
        "interpretation":     interpretation,
        "timestamp":          datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# FUNCTION 3 — Brent-WTI spread regime analysis
# ─────────────────────────────────────────────────────────────────────────────

def get_brent_wti_analysis() -> dict:
    """
    Analyse the Brent-WTI cash spread using z-score vs 252-day history
    and a 30-day rolling correlation to detect regional divergence.

    Returns
    -------
    {
      "current_spread":    float,   today's Brent − WTI
      "mean_252d":         float,   252-day average spread
      "std_252d":          float,   252-day std dev of spread
      "z_score":           float,   (current − mean) / std
      "rolling_30d_corr":  float,   30-day return correlation
      "hist_avg_corr":     float,   long-run average of 30d rolling corr
      "interpretation":    str,
      "alert":             bool,    True if |z_score| > 1.5 or corr < 0.80
      "timestamp":         str,
    }
    """
    from fetchers.historical import load_historical

    hist = load_historical()

    brent_close = hist["Brent"]["Close"].dropna()
    wti_close   = hist["WTI"]["Close"].dropna()

    # Align on common dates
    combined     = pd.DataFrame({"brent": brent_close, "wti": wti_close}).dropna()
    brent_close  = combined["brent"]
    wti_close    = combined["wti"]

    spread_series = brent_close - wti_close
    current       = float(spread_series.iloc[-1])
    tail_252      = spread_series.tail(252)
    mean_252      = float(tail_252.mean())
    std_252       = float(tail_252.std())
    z_score       = (current - mean_252) / std_252 if std_252 else 0.0

    # Rolling 30-day return correlation
    brent_ret     = brent_close.pct_change().dropna()
    wti_ret       = wti_close.pct_change().dropna()
    rolling_corr_series = brent_ret.rolling(30).corr(wti_ret).dropna()
    rolling_corr  = float(rolling_corr_series.iloc[-1])
    hist_avg_corr = float(rolling_corr_series.mean())

    # ── interpretation ────────────────────────────────────────────────────────
    if z_score > 2.0:
        interpretation = (
            f"Spread {z_score:.1f}s above average — "
            "extreme Brent premium, likely Middle East supply disruption"
        )
    elif z_score > 1.5:
        interpretation = (
            f"Spread {z_score:.1f}s above average — "
            "Brent carrying regional risk premium, monitor Hormuz/Suez"
        )
    elif z_score < -2.0:
        interpretation = (
            f"Spread {z_score:.1f}s below average — "
            "WTI unusually expensive, US supply tightness or export surge"
        )
    elif z_score < -1.5:
        interpretation = (
            f"Spread {z_score:.1f}s below average — "
            "WTI at premium, check Cushing inventory levels"
        )
    elif rolling_corr < 0.80:
        interpretation = (
            f"Correlation dropped to {rolling_corr:.2f} — "
            "unusual divergence, investigate regional driver"
        )
    else:
        interpretation = (
            "Brent-WTI relationship normal — "
            "no regional supply signal detected"
        )

    alert = abs(z_score) > 1.5 or rolling_corr < 0.80

    return {
        "current_spread":    round(current,       2),
        "mean_252d":         round(mean_252,       2),
        "std_252d":          round(std_252,        3),
        "z_score":           round(z_score,        2),
        "rolling_30d_corr":  round(rolling_corr,  4),
        "hist_avg_corr":     round(hist_avg_corr, 4),
        "interpretation":    interpretation,
        "alert":             alert,
        "timestamp":         datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# __main__ — formatted output for all three functions
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    RULE = "─" * 56

    # ── 1. Correlation matrix ─────────────────────────────────────────────────
    print("\n" + "=" * 56)
    print("  [1]  CROSS-ASSET CORRELATION MATRIX  (30d vs 252d)")
    print("=" * 56)

    cm = get_correlation_matrix()

    # Print current 30d matrix
    assets = ["brent", "wti", "hh", "dxy", "spx"]
    header = f"  {'':10}" + "".join(f"  {a.upper():>6}" for a in assets)
    print(f"\n  30-day return correlations:")
    print(header)
    print("  " + RULE)
    for row_a in assets:
        row_cells = []
        for col_a in assets:
            if row_a == col_a:
                row_cells.append(f"  {'1.000':>6}")
            else:
                val = cm["matrix"].get(row_a, {}).get(col_a)
                row_cells.append(f"  {val:>6.3f}" if val is not None else "     N/A")
        print(f"  {row_a.upper():<10}" + "".join(row_cells))

    # Pair analysis
    print(f"\n  Pair analysis  (30d vs 252d):")
    print(f"  {'Pair':<12} {'30d':>6} {'252d':>6} {'Dev':>7}  {'Status':<10}  Note")
    print("  " + RULE)

    status_icons = {"NORMAL": " ", "DRIFTING": "~", "BROKEN": "!"}
    for pk, pd_data in cm["pairs"].items():
        icon  = status_icons.get(pd_data["status"], " ")
        chg   = " *" if pd_data["significant_change"] else "  "
        print(f"  [{icon}] {pk:<10}  {pd_data['current']:>6.3f}  "
              f"{pd_data['historical']:>6.3f}  "
              f"{pd_data['deviation']:>+7.3f}  "
              f"{pd_data['status']:<10}{chg}  "
              f"{pd_data['interpretation'][:42]}")

    if cm["alerts"]:
        print(f"\n  *** ALERTS: {', '.join(cm['alerts'])} ***")
    else:
        print(f"\n  No correlation breaks detected.")

    # ── 2. Curve correlation ──────────────────────────────────────────────────
    print("\n\n" + "=" * 56)
    print("  [2]  BRENT vs WTI CURVE SHAPE CORRELATION")
    print("=" * 56)

    cc = get_curve_correlation()

    print(f"\n  Curve correlation : {cc['curve_correlation']:.4f}")
    print(f"  Brent slope (M1→last): {cc['brent_slope']:+.2f}")
    print(f"  WTI   slope (M1→last): {cc['wti_slope']:+.2f}")
    print(f"  Avg B-W spread        : ${cc['avg_spread']:.2f}")
    print(f"  Spread std dev        : ${cc['spread_std']:.3f}")
    print(f"\n  Interpretation: {cc['interpretation']}")

    print(f"\n  Tenor-by-tenor spread:")
    print(f"  {'Tenor':<10} {'Brent':>8} {'WTI':>8} {'Spread':>8}")
    print("  " + "─" * 36)
    for row in cc["spreads_by_tenor"]:
        print(f"  {row['tenor']:<10} "
              f"{row['brent']:>8.2f} "
              f"{row['wti']:>8.2f} "
              f"{row['spread']:>+8.3f}")

    # ── 3. Brent-WTI spread analysis ──────────────────────────────────────────
    print("\n\n" + "=" * 56)
    print("  [3]  BRENT-WTI CASH SPREAD ANALYSIS")
    print("=" * 56)

    bw = get_brent_wti_analysis()

    alert_flag = "  *** ALERT ***" if bw["alert"] else ""
    print(f"\n  Current spread  : ${bw['current_spread']:.2f}{alert_flag}")
    print(f"  252d mean       : ${bw['mean_252d']:.2f}")
    print(f"  252d std dev    : ${bw['std_252d']:.3f}")
    print(f"  Z-score         :  {bw['z_score']:+.2f}")
    print(f"  30d return corr :  {bw['rolling_30d_corr']:.4f}  "
          f"(hist avg: {bw['hist_avg_corr']:.4f})")
    print(f"\n  Interpretation: {bw['interpretation']}")
    print(f"  Timestamp     : {bw['timestamp']}")
    print()
