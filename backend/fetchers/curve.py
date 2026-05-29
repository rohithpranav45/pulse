"""
Futures curve fetcher for WTI and Brent (M1-M12).
Computes M1-M2 spread, overall slope, contango / backwardation label.

Data strategy
-------------
  Brent  — ICE LCO settlement xlsx (authoritative, full M1-M12)
  WTI    — M1 from CL=F live price; M2-M12 derived from Brent curve shape
            adjusted by the live Brent-WTI spread at M1.
            Yahoo Finance does not serve deferred individual NYMEX contracts.

Analytics helpers (build on top of fetch_curve):
  get_curve_metrics()  — enriched single-curve metrics dict
  get_both_curves()    — WTI + Brent side-by-side with comparison block
"""

import os
import sys
from datetime import datetime

import numpy as np
from dotenv import load_dotenv
import yfinance as yf

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

load_dotenv()


def _get_brent_strip_prices(n: int = 12) -> list[float | None]:
    """Return list of n Brent prices (M1…Mn) from ICE LCO xlsx."""
    try:
        from fetchers.multi_curve import get_brent_strip
        return [s["price"] for s in get_brent_strip(n)]
    except Exception:
        return [None] * n


def _get_wti_m1() -> float | None:
    """Return latest WTI front-month price from CL=F continuous contract."""
    try:
        hist  = yf.Ticker("CL=F").history(period="3d", auto_adjust=True)
        close = hist["Close"].dropna() if "Close" in hist.columns else None
        if close is None or close.empty:
            return None
        return round(float(close.iloc[-1]), 3)
    except Exception:
        return None


def _build_result(key: str, prices_12: list, symbols: list) -> dict:
    """Shared helper: turn a list of prices into the standard curve dict."""
    curve   = {}
    details = []
    for i, price in enumerate(prices_12):
        if price is None:
            continue
        label = f"M{i + 1}"
        curve[label] = price
        details.append({"label": label, "cal_label": label,
                         "symbol": symbols[i], "price": price})

    labels = list(curve.keys())
    prices = list(curve.values())

    if len(prices) < 2:
        return {
            "commodity": key, "curve": curve, "contracts": details,
            "spread_m1_m2": None, "slope": None, "structure": "unknown",
        }

    spread_m1_m2 = round(prices[0] - prices[1], 3)
    slope        = round(prices[0] - prices[-1], 3)

    if slope > 0.20:
        structure = "backwardation"
    elif slope < -0.20:
        structure = "contango"
    else:
        structure = "flat"

    return {
        "commodity":    key,
        "curve":        curve,
        "contracts":    details,
        "spread_m1_m2": spread_m1_m2,
        "slope":        slope,
        "structure":    structure,
        "first_label":  labels[0],
        "last_label":   labels[-1],
    }


def fetch_curve(commodity: str = "WTI") -> dict:
    """
    Fetch the futures curve for WTI or Brent.

    Brent: ICE LCO settlement xlsx — authoritative M1-M12 daily settlements.
    WTI:   M1 live from CL=F; M2-M12 synthesised from Brent curve shape
           adjusted by the live Brent-WTI spread at M1 (basis-adjusted).

    Returns
    -------
    {
      "commodity":    "WTI" | "BRENT",
      "curve":        {"M1": 96.60, "M2": 93.09, ...},
      "contracts":    [{"label", "cal_label", "symbol", "price"}, ...],
      "spread_m1_m2": float | None,
      "slope":        float | None,   # first - last  (positive = backwardation)
      "structure":    "contango" | "backwardation" | "flat" | "unknown",
      "first_label":  "M1",
      "last_label":   "M12",
    }
    """
    key = commodity.upper()
    n   = 12

    if key == "BRENT":
        prices  = _get_brent_strip_prices(n)
        symbols = [f"LCO-c{i+1}" for i in range(n)]
        return _build_result("BRENT", prices, symbols)

    elif key == "WTI":
        brent_prices = _get_brent_strip_prices(n)
        wti_m1       = _get_wti_m1()

        if wti_m1 is None:
            # Absolute fallback — return empty curve
            return {
                "commodity": "WTI", "curve": {}, "contracts": [],
                "spread_m1_m2": None, "slope": None, "structure": "unknown",
            }

        # Basis spread at M1 (Brent premium over WTI — typically +$3-6)
        bw_spread = (brent_prices[0] - wti_m1) if brent_prices[0] else 3.5

        # Build WTI M1-M12: M1 live, M2-M12 from Brent shape minus basis spread
        prices  = [wti_m1]
        symbols = ["CL=F"]
        for i in range(1, n):
            bp = brent_prices[i]
            prices.append(round(bp - bw_spread, 3) if bp is not None else None)
            symbols.append(f"CL~M{i+1}")

        return _build_result("WTI", prices, symbols)

    else:
        raise ValueError(f"Unknown commodity '{commodity}'. Use 'WTI' or 'Brent'.")


def get_curve_metrics(asset: str = "wti") -> dict:
    """
    Enriched single-curve metrics for WTI or Brent.

    Parameters
    ----------
    asset : "wti" or "brent" (case-insensitive)

    Returns
    -------
    {
      "commodity":      str,    e.g. "WTI"
      "m1_price":       float,  first available contract price
      "m2_price":       float,  second available contract price
      "m1_m2_spread":   float,  M1 - M2  (positive = backwardation)
      "curve_slope":    float,  last contract - first contract price
                                (positive = backwardation, negative = contango)
      "shape":          str,    "CONTANGO" | "BACKWARDATION" | "FLAT" | "UNKNOWN"
      "steepness":      str,    "STEEP" | "MODERATE" | "FLAT"
      "contango_depth": float,  m1_m2_spread / m1_price * 100 (signed %)
      "n_contracts":    int,    number of tenors with live prices
      "contracts":      list,   raw contract detail from fetch_curve
    }
    """
    raw = fetch_curve(asset.upper())

    prices = list(raw["curve"].values())
    n      = len(prices)

    if n < 2:
        return {
            "commodity":      raw["commodity"],
            "m1_price":       prices[0] if n == 1 else None,
            "m2_price":       None,
            "m1_m2_spread":   None,
            "curve_slope":    None,
            "shape":          "UNKNOWN",
            "steepness":      "UNKNOWN",
            "contango_depth": None,
            "n_contracts":    n,
            "contracts":      raw["contracts"],
        }

    m1 = prices[0]
    m2 = prices[1]

    m1_m2_spread   = round(m1 - m2, 3)
    curve_slope    = round(prices[-1] - prices[0], 3)   # negative = backwardation
    contango_depth = round(m1_m2_spread / m1 * 100, 3) if m1 else None

    # Shape — mirror fetch_curve's own logic but uppercase for public API
    shape = raw["structure"].upper()

    # Steepness — based on absolute M1-M2 spread
    abs_spread = abs(m1_m2_spread)
    if abs_spread > 1.0:
        steepness = "STEEP"
    elif abs_spread > 0.4:
        steepness = "MODERATE"
    else:
        steepness = "FLAT"

    return {
        "commodity":      raw["commodity"],
        "m1_price":       m1,
        "m2_price":       m2,
        "m1_m2_spread":   m1_m2_spread,
        "curve_slope":    curve_slope,
        "shape":          shape,
        "steepness":      steepness,
        "contango_depth": contango_depth,
        "n_contracts":    n,
        "contracts":      raw["contracts"],
    }


def get_both_curves() -> dict:
    """
    Fetch WTI and Brent simultaneously and compare their curve shapes.

    Returns
    -------
    {
      "wti":    fetch_curve("WTI") result,
      "brent":  fetch_curve("BRENT") result,
      "comparison": {
        "correlation":     float,  numpy corrcoef on aligned price lists
        "avg_spread":      float,  mean(brent - wti) across shared tenors
        "spread_std":      float,  std(brent - wti) — curve divergence signal
        "brent_slope":     float,  last - first brent price
        "wti_slope":       float,  last - first wti price
        "interpretation":  str,    signal label
        "tenor_spreads":   dict,   {label: brent_price - wti_price}
      }
    }
    """
    wti_raw   = fetch_curve("WTI")
    brent_raw = fetch_curve("BRENT")

    wti_curve   = wti_raw["curve"]     # {label: price}
    brent_curve = brent_raw["curve"]

    # Align on shared tenor labels (e.g. M3, M4, …)
    shared_labels = [lbl for lbl in wti_curve if lbl in brent_curve]

    if len(shared_labels) < 2:
        return {
            "wti":   wti_raw,
            "brent": brent_raw,
            "comparison": {
                "correlation":    None,
                "avg_spread":     None,
                "spread_std":     None,
                "brent_slope":    None,
                "wti_slope":      None,
                "interpretation": "Insufficient shared tenors to compare",
                "tenor_spreads":  {},
            },
        }

    wti_prices   = np.array([wti_curve[l]   for l in shared_labels])
    brent_prices = np.array([brent_curve[l] for l in shared_labels])
    spreads      = brent_prices - wti_prices          # Brent premium at each tenor

    correlation = round(float(np.corrcoef(wti_prices, brent_prices)[0, 1]), 4)
    avg_spread  = round(float(spreads.mean()), 3)
    spread_std  = round(float(spreads.std()), 3)

    # Slopes use the full (unaligned) per-commodity curve
    wti_vals   = list(wti_curve.values())
    brent_vals = list(brent_curve.values())
    wti_slope   = round(wti_vals[-1]   - wti_vals[0],   3)
    brent_slope = round(brent_vals[-1] - brent_vals[0], 3)

    # Interpretation
    if spread_std > 0.8 and brent_slope < wti_slope:
        interpretation = "Brent flatter — Middle East tightness regional"
    elif spread_std > 0.8 and wti_slope < brent_slope:
        interpretation = "WTI flatter — US domestic tightening"
    elif correlation > 0.98:
        interpretation = "Curves parallel — global dynamics uniform"
    else:
        interpretation = "Minor divergence — monitor for regional signal"

    tenor_spreads = {
        lbl: round(float(brent_curve[lbl] - wti_curve[lbl]), 3)
        for lbl in shared_labels
    }

    return {
        "wti":   wti_raw,
        "brent": brent_raw,
        "comparison": {
            "correlation":    correlation,
            "avg_spread":     avg_spread,
            "spread_std":     spread_std,
            "brent_slope":    brent_slope,
            "wti_slope":      wti_slope,
            "interpretation": interpretation,
            "tenor_spreads":  tenor_spreads,
        },
    }


if __name__ == "__main__":
    # ── get_curve_metrics ─────────────────────────────────────────────────────
    print("=" * 58)
    print("  get_curve_metrics()  — per-asset enriched metrics")
    print("=" * 58)

    for asset in ["wti", "brent"]:
        m = get_curve_metrics(asset)
        print(f"\n  {m['commodity']} ({m['n_contracts']} live contracts)")
        print(f"  {'-' * 44}")
        print(f"  M1 price       : ${m['m1_price']:>9.3f}")
        print(f"  M2 price       : ${m['m2_price']:>9.3f}")
        print(f"  M1-M2 spread   :  {m['m1_m2_spread']:>+9.3f}  "
              f"({'backwardation' if m['m1_m2_spread'] > 0 else 'contango'})")
        print(f"  Curve slope    :  {m['curve_slope']:>+9.3f}  "
              f"(last - first contract)")
        print(f"  Shape          :  {m['shape']}")
        print(f"  Steepness      :  {m['steepness']}")
        print(f"  Contango depth :  {m['contango_depth']:>+8.3f}%  "
              f"(M1-M2 / M1 * 100)")

    # ── get_both_curves ───────────────────────────────────────────────────────
    print(f"\n\n{'=' * 58}")
    print("  get_both_curves()  — cross-commodity comparison")
    print("=" * 58)

    both = get_both_curves()
    cmp  = both["comparison"]

    # Side-by-side tenor table
    wti_curve   = both["wti"]["curve"]
    brent_curve = both["brent"]["curve"]
    all_labels  = sorted(
        set(wti_curve) | set(brent_curve),
        key=lambda x: int(x[1:])
    )

    print(f"\n  {'Tenor':<6}  {'WTI':>9}  {'Brent':>9}  {'Spread (B-W)':>13}")
    print(f"  {'-' * 44}")
    for lbl in all_labels:
        w = wti_curve.get(lbl)
        b = brent_curve.get(lbl)
        if w is None or b is None:
            continue
        spread = cmp["tenor_spreads"].get(lbl, float("nan"))
        print(f"  {lbl:<6}  ${w:>8.3f}  ${b:>8.3f}  {spread:>+12.3f}")

    print(f"\n  {'Metric':<22}  {'WTI':>10}  {'Brent':>10}")
    print(f"  {'-' * 48}")
    print(f"  {'Slope (last-first)':<22}  {cmp['wti_slope']:>+10.3f}  {cmp['brent_slope']:>+10.3f}")
    print(f"  {'Avg B-W spread':<22}  {cmp['avg_spread']:>+10.3f}")
    print(f"  {'Spread std dev':<22}  {cmp['spread_std']:>10.3f}")
    print(f"  {'Correlation':<22}  {cmp['correlation']:>10.4f}")
    print(f"\n  Signal: {cmp['interpretation']}")
