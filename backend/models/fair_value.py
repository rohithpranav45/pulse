"""
Fair Value model — theoretical Brent crude price with factor decomposition.

Methodology: Cost-of-Carry base (spot × e^((r+c-y)×T)) adjusted by four
fundamental drivers, each expressed in dollar terms so the contribution of
every factor is immediately readable on the dashboard.

Four adjustments applied on top of the cost-of-carry base:
  1. Inventory tightness  — deviation of crude stocks from 5-yr seasonal avg
  2. OPEC compliance      — under/over-production vs stated quota
  3. DXY deviation        — dollar strength/weakness vs 30-day average
  4. Geo-risk premium     — composite geopolitical risk index above neutral

Public API:
  get_fed_rate()                        → float (decimal, e.g. 0.0533)
  get_dxy_deviation()                   → float (current DXY − 30d avg)
  calculate_convenience_yield(pct)      → float (clamped 0 – 0.08)
  calculate_fair_value(asset="brent")   → dict
"""
import os as _os, sys as _sys
_BACKEND = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))
if _BACKEND not in _sys.path:
    _sys.path.insert(0, _BACKEND)

import math
import os
import pickle
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
FRED_KEY = os.getenv("FRED_API_KEY")

# ── cache for FRED rate (refresh once per week) ───────────────────────────────
_FRED_CACHE_FILE = Path(__file__).parent.parent / "data" / "cache" / "fred_rate.pkl"
_FRED_CACHE_MAX_AGE_S = 7 * 24 * 3600   # 1 week


# ── FUNCTION 1 — Fed Funds Rate ───────────────────────────────────────────────

def get_fed_rate() -> float:
    """
    Fetch the most-recent effective Fed Funds Rate from FRED.

    Caches to disk for 7 days to avoid hammering the API.
    Falls back to 0.053 (5.3%) if the API is unreachable or the key is missing.

    Returns
    -------
    float  — rate as decimal  (e.g. 5.33% → 0.0533)
    """
    # ── check disk cache ──────────────────────────────────────────────────────
    if _FRED_CACHE_FILE.exists():
        age_s = time.time() - _FRED_CACHE_FILE.stat().st_mtime
        if age_s < _FRED_CACHE_MAX_AGE_S:
            with open(_FRED_CACHE_FILE, "rb") as f:
                cached = pickle.load(f)
            return cached["rate"]

    # ── fetch from FRED ───────────────────────────────────────────────────────
    _FALLBACK = 0.053
    if not FRED_KEY:
        return _FALLBACK

    try:
        r = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id":    "FEDFUNDS",
                "api_key":      FRED_KEY,
                "file_type":    "json",
                "limit":        1,
                "sort_order":   "desc",
            },
            timeout=10,
        )
        r.raise_for_status()
        obs = r.json()["observations"]
        if not obs:
            return _FALLBACK

        rate = float(obs[0]["value"]) / 100.0   # percent → decimal

        # ── persist to cache ──────────────────────────────────────────────────
        _FRED_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_FRED_CACHE_FILE, "wb") as f:
            pickle.dump({"rate": rate, "fetched": datetime.now(timezone.utc).isoformat()}, f)

        return rate

    except Exception:
        return _FALLBACK


# ── FUNCTION 2 — DXY deviation from 30-day average ───────────────────────────

def get_dxy_deviation() -> float:
    """
    Compute how far the current DXY sits above or below its 30-day average.

    Uses closing prices from the shared historical cache (no new download).

    Returns
    -------
    float  — current_dxy − 30d_average
             Positive → dollar stronger than recent avg (bearish crude)
             Negative → dollar weaker (bullish crude)
    """
    from fetchers.historical import load_historical

    hist = load_historical()
    dxy_close = hist["DXY"]["Close"].dropna()

    if len(dxy_close) < 2:
        return 0.0

    current    = float(dxy_close.iloc[-1])
    avg_30d    = float(dxy_close.iloc[-30:].mean()) if len(dxy_close) >= 30 \
                 else float(dxy_close.mean())

    return round(current - avg_30d, 4)


# ── FUNCTION 3 — Convenience yield ───────────────────────────────────────────

def calculate_convenience_yield(inv_deviation_pct: float) -> float:
    """
    Estimate convenience yield from inventory deviation vs seasonal average.

    Tight inventories (negative deviation) → higher convenience yield.
    Ample inventories (positive deviation) → lower convenience yield.

    Parameters
    ----------
    inv_deviation_pct : float
        % deviation of crude stocks from 5-year seasonal average.
        Negative means below-average (tight); positive means above-average.

    Returns
    -------
    float  — annualised convenience yield, clamped to [0.00, 0.08]
    """
    base_yield = 0.02
    adjustment = -inv_deviation_pct / 100.0 * 0.02
    y = base_yield + adjustment
    return max(0.0, min(y, 0.08))


# ── FUNCTION 4 — Fair value calculator ───────────────────────────────────────

def calculate_fair_value(asset: str = "brent") -> dict:
    """
    Calculate theoretical fair value for an energy asset.

    Methodology
    -----------
    1. Cost-of-carry base:   spot × exp((r + c − y) × T)
       r = Fed Funds rate  |  c = storage cost (0.6% pa)  |  y = convenience yield
       T = 30/365 (front-month approximation)

    2. Inventory adjustment: −(inv_dev_pct / 100) × $30 per bbl
       Stocks 10% below avg → +$3.00 (tightness premium)

    3. OPEC compliance:      (compliance − 1.0) × $7.50
       100% compliant → $0; 80% compliant → −$1.50 (over-production discount)

    4. DXY adjustment:       −dxy_deviation × 0.60
       DXY +1 vs 30d avg → −$0.60 (stronger dollar = lower oil)

    5. Geo-risk premium:     max(0, (geo_index − 30) × 0.08)
       Index of 30 = neutral; each point above adds $0.08

    Parameters
    ----------
    asset : str  — "brent" or "wti" (must be a key in get_live_prices())

    Returns
    -------
    See module docstring for full schema.
    """
    from fetchers.prices    import get_live_prices
    from fetchers.eia       import get_inventory_vs_seasonal
    from fetchers.opec      import get_compliance_table
    from fetchers.geo_risk  import calculate_geo_risk

    # ── Step 1 — gather inputs ────────────────────────────────────────────────
    prices   = get_live_prices()
    spot     = float(prices[asset]["price"])

    r        = get_fed_rate()
    c        = 0.006                    # storage cost per month, annualised

    inv      = get_inventory_vs_seasonal()
    inv_dev_pct = inv["crude_stocks"].get("deviation_pct") or 0.0

    y        = calculate_convenience_yield(inv_dev_pct)
    T        = 30.0 / 365.0            # front-month approximation

    opec     = get_compliance_table()
    compliance = opec["overall_compliance_rate"]

    dxy_dev  = get_dxy_deviation()

    geo      = calculate_geo_risk()
    geo_index = int(geo["index"])

    # ── Step 2 — cost-of-carry base ───────────────────────────────────────────
    base_fv  = spot * math.exp((r + c - y) * T)
    base_detail = (
        f"Spot ${spot:.2f} x e^(r={r:.4f} + c={c:.3f} - y={y:.4f}) x T={T:.4f}"
    )

    # ── Step 3 — fundamental adjustments ─────────────────────────────────────
    inv_adj    = -(inv_dev_pct / 100.0) * 30.0
    inv_detail = (
        f"Crude {inv_dev_pct:+.1f}% vs seasonal avg → ${inv_adj:+.2f}"
    )

    opec_adj    = (compliance - 1.0) * 7.5
    opec_detail = (
        f"OPEC compliance {compliance * 100:.0f}% → ${opec_adj:+.2f}"
    )

    dxy_adj    = -dxy_dev * 0.60
    dxy_detail = (
        f"DXY {dxy_dev:+.2f} vs 30d avg → ${dxy_adj:+.2f}"
    )

    geo_premium = max(0.0, (geo_index - 30) * 0.08)
    geo_detail  = (
        f"Geo index {geo_index}/100 → ${geo_premium:+.2f}"
    )

    # ── Step 4 — combine ──────────────────────────────────────────────────────
    fair_value = base_fv + inv_adj + opec_adj + dxy_adj + geo_premium

    deviation_pct = (spot - fair_value) / fair_value * 100.0

    if deviation_pct > 8:
        deviation_label = "EXTREME OVERVALUE"
    elif deviation_pct > 4:
        deviation_label = "OVEREXTENDED"
    elif deviation_pct > -4:
        deviation_label = "FAIR"
    elif deviation_pct > -8:
        deviation_label = "UNDERVALUED"
    else:
        deviation_label = "DEEPLY UNDERVALUED"

    return {
        "asset":           asset.upper(),
        "live_price":      round(spot,       2),
        "fair_value":      round(fair_value, 2),
        "deviation_pct":   round(deviation_pct, 2),
        "deviation_label": deviation_label,
        "components": {
            "base_cost_of_carry":   {"value": round(base_fv,     2), "detail": base_detail},
            "inventory_adjustment": {"value": round(inv_adj,     2), "detail": inv_detail},
            "opec_adjustment":      {"value": round(opec_adj,    2), "detail": opec_detail},
            "dxy_adjustment":       {"value": round(dxy_adj,     2), "detail": dxy_detail},
            "geo_premium":          {"value": round(geo_premium, 2), "detail": geo_detail},
        },
        "inputs": {
            "spot":               round(spot,        2),
            "fed_rate":           round(r,           4),
            "storage_cost":       c,
            "convenience_yield":  round(y,           4),
            "inv_deviation_pct":  round(inv_dev_pct, 2),
            "opec_compliance":    round(compliance,  4),
            "dxy_deviation_30d":  round(dxy_dev,     4),
            "geo_index":          geo_index,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# ── __main__ — formatted decomposition printout ───────────────────────────────

if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("\nCalculating fair value model...\n")
    result = calculate_fair_value("brent")

    c   = result["components"]
    inp = result["inputs"]

    RULE = "━" * 44   # ━━━━ (heavy horizontal)

    base  = c["base_cost_of_carry"]
    inv   = c["inventory_adjustment"]
    opec  = c["opec_adjustment"]
    dxy   = c["dxy_adjustment"]
    geo   = c["geo_premium"]

    # ── heading ───────────────────────────────────────────────────────────────
    print(f"  FAIR VALUE DECOMPOSITION — {result['asset']} CRUDE")
    print(f"  {RULE}")

    # ── cost-of-carry base ────────────────────────────────────────────────────
    r_pct = inp["fed_rate"]    * 100
    c_pct = inp["storage_cost"]* 100
    y_pct = inp["convenience_yield"] * 100
    print(
        f"  {'Cost of Carry Base:':<32} ${base['value']:>7.2f}"
        f"    (r={r_pct:.2f}%, c={c_pct:.1f}%, y={y_pct:.2f}%)"
    )

    # ── four adjustments ─────────────────────────────────────────────────────
    def _adj_line(label: str, value: float, detail: str) -> None:
        sign     = "+" if value >= 0 else "-"
        amt_sign = "+" if value >= 0 else "-"
        print(f"  {sign} {label:<30} {amt_sign}${abs(value):.2f}"
              f"    ({detail})")

    inv_detail_short  = f"{inp['inv_deviation_pct']:+.1f}% vs seasonal avg"
    geo_detail_short  = f"Geo Index: {inp['geo_index']}"
    dxy_detail_short  = f"DXY {inp['dxy_deviation_30d']:+.2f} vs 30d avg"
    opec_detail_short = f"{inp['opec_compliance']*100:.0f}% compliance"

    _adj_line("Inventory Tightness:",  inv["value"],  inv_detail_short)
    _adj_line("Geopolitical Premium:", geo["value"],  geo_detail_short)
    _adj_line("Dollar Headwind:",      dxy["value"],  dxy_detail_short)
    _adj_line("OPEC Adjustment:",      opec["value"], opec_detail_short)

    # ── totals ────────────────────────────────────────────────────────────────
    print(f"  {RULE}")
    print(f"  {'FAIR VALUE:':<32} ${result['fair_value']:>7.2f}")
    print(f"  {'LIVE PRICE:':<32} ${result['live_price']:>7.2f}")

    dev   = result["deviation_pct"]
    label = result["deviation_label"]
    sign  = "+" if dev >= 0 else ""
    print(f"  {'DEVIATION:':<32}  {sign}{dev:.1f}%  —  {label}")
    print(f"  {RULE}")

    # ── full inputs table ─────────────────────────────────────────────────────
    print(f"\n  Inputs used:")
    print(f"    {'Spot price:':<28} ${inp['spot']:.2f}")
    print(f"    {'Fed Funds Rate:':<28}  {inp['fed_rate']*100:.2f}%")
    print(f"    {'Storage cost (ann.):':<28}  {inp['storage_cost']*100:.1f}%")
    print(f"    {'Convenience yield (ann.):':<28}  {inp['convenience_yield']*100:.2f}%")
    print(f"    {'Inv. dev. vs 5yr avg:':<28}  {inp['inv_deviation_pct']:+.1f}%")
    print(f"    {'OPEC compliance:':<28}  {inp['opec_compliance']*100:.1f}%")
    print(f"    {'DXY dev. vs 30d avg:':<28}  {inp['dxy_deviation_30d']:+.3f}")
    print(f"    {'Geo-risk index:':<28}  {inp['geo_index']} / 100")
    print(f"\n  Timestamp: {result['timestamp']}")
    print()
