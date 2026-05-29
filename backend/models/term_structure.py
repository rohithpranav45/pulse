"""
Term Structure Model
====================
Computes:
  1. 5×5 cross-product correlation matrix (90-day M1 daily log returns)
  2. Per-product M1-M12 price strip + spread chain (M1-M3, M3-M6, M6-M12)
  3. Contango depth score per product (steepness of the full curve)

Products
--------
  brent       (ICE LCO xlsx)
  wti         (CL=F)
  rbob        (RB=F)
  heating_oil (HO=F)
  henry_hub   (NG=F)

Public API
----------
  get_term_structure() → dict
    {
      "correlation_matrix": {
        "labels":  ["Brent","WTI","RBOB","HO","NG"],
        "matrix":  [[1.0, 0.95, ...], ...],    # 5×5, row=product, col=product
        "data_days": int,                       # actual days used for corr
        "error":   False,
      },
      "strips": {
        "brent":       { "prices": [...], "spreads": {...}, "contango_score": float },
        "wti":         { ... },
        "rbob":        { ... },
        "heating_oil": { ... },
        "henry_hub":   { ... },
      },
      "timestamp": str,
    }

Contango depth score
--------------------
  score = (M12 - M1) / M1 * 100   → positive = contango, negative = backwardation
  Capped to [-30, +30] for display purposes.

Spread chain
------------
  "m1_m3":  M1 price − M3 price
  "m3_m6":  M3 price − M6 price
  "m6_m12": M6 price − M12 price
  (positive = backwardation in that segment)
"""

import os as _os, sys as _sys
_BACKEND = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))
if _BACKEND not in _sys.path:
    _sys.path.insert(0, _BACKEND)

import logging
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

# ── Product display labels (order matters for matrix) ─────────────────────────
_PRODUCTS = ["brent", "wti", "rbob", "heating_oil", "henry_hub"]
_LABELS   = ["Brent", "WTI", "RBOB", "Heat Oil", "Nat Gas"]


# ══════════════════════════════════════════════════════════════════════════════
# Correlation matrix
# ══════════════════════════════════════════════════════════════════════════════

def _build_correlation_matrix(histories: dict, days: int = 90) -> dict:
    """
    Build 5×5 Pearson correlation matrix of daily log-returns from M1 histories.

    histories: dict of {product_key: pd.Series}
    Returns:
    {
      "labels":    list[str],
      "matrix":    list[list[float]],   # 5×5
      "data_days": int,
      "error":     bool,
    }
    """
    series_list = []
    for prod in _PRODUCTS:
        s = histories.get(prod, pd.Series(dtype=float))
        series_list.append(s.rename(prod))

    # Align on common dates
    df = pd.concat(series_list, axis=1)
    df = df.sort_index().dropna(how="all")

    # Log returns
    log_ret = np.log(df / df.shift(1)).dropna(how="all")

    # Use last `days` rows
    log_ret = log_ret.tail(days)

    n_days = len(log_ret)
    if n_days < 10:
        log.warning("Insufficient data for correlation matrix (%d rows)", n_days)
        identity = np.eye(5).tolist()
        return {
            "labels":    _LABELS,
            "matrix":    identity,
            "data_days": n_days,
            "error":     True,
        }

    # Correlation for each pair — use available data per pair
    n = len(_PRODUCTS)
    matrix = np.ones((n, n))
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            col_i = _PRODUCTS[i]
            col_j = _PRODUCTS[j]
            if col_i not in log_ret.columns or col_j not in log_ret.columns:
                matrix[i][j] = np.nan
                continue
            pair = log_ret[[col_i, col_j]].dropna()
            if len(pair) < 10:
                matrix[i][j] = np.nan
                continue
            corr = float(pair[col_i].corr(pair[col_j]))
            matrix[i][j] = round(corr, 3) if not np.isnan(corr) else np.nan

    # Replace NaN with None for JSON serialisation
    matrix_list = [
        [None if np.isnan(v) else v for v in row]
        for row in matrix.tolist()
    ]

    return {
        "labels":    _LABELS,
        "matrix":    matrix_list,
        "data_days": n_days,
        "error":     False,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Strip enrichment — spreads + contango score
# ══════════════════════════════════════════════════════════════════════════════

def _enrich_strip(strip: list[dict]) -> dict:
    """
    Given a list of {"month": "M1", "price": float|None} items,
    compute spread chain and contango score.

    Returns:
    {
      "prices":         [{"month":"M1","price":float|None}, ...],
      "spreads": {
        "m1_m3":  float|None,
        "m3_m6":  float|None,
        "m6_m12": float|None,
        "m1_m12": float|None,
      },
      "contango_score": float|None,   # (M12-M1)/M1*100, capped [-30,+30]
      "structure":      str,          # "CONTANGO" / "BACKWARDATION" / "FLAT"
    }
    """
    prices = {item["month"]: item["price"] for item in strip}

    def _spread(a: str, b: str) -> Optional[float]:
        pa, pb = prices.get(a), prices.get(b)
        if pa is None or pb is None:
            return None
        return round(pa - pb, 4)

    def _score() -> Optional[float]:
        p1  = prices.get("M1")
        p12 = prices.get("M12")
        if p1 is None or p12 is None or p1 == 0:
            return None
        raw = (p12 - p1) / p1 * 100
        return round(max(-30.0, min(30.0, raw)), 2)

    score = _score()
    if score is None:
        structure = "UNKNOWN"
    elif score > 1.0:
        structure = "CONTANGO"
    elif score < -1.0:
        structure = "BACKWARDATION"
    else:
        structure = "FLAT"

    return {
        "prices":  strip,
        "spreads": {
            "m1_m3":  _spread("M1", "M3"),
            "m3_m6":  _spread("M3", "M6"),
            "m6_m12": _spread("M6", "M12"),
            "m1_m12": _spread("M1", "M12"),
        },
        "contango_score": score,
        "structure":      structure,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Calendar Spread Matrix
# ══════════════════════════════════════════════════════════════════════════════

def _build_calendar_spread_matrix(lco_df: "pd.DataFrame", days: int = 90) -> dict:
    """
    Build the calendar spread matrix for Brent using LCO xlsx history.

    lco_df : DataFrame with columns c1..c12 (float), indexed by date, newest first.
    days   : number of recent trading days to use.

    Returns
    -------
    {
      "labels"   : ["M1-M2", "M2-M3", ..., "M11-M12"],   # 11 spread labels
      "matrix"   : [[1.0, 0.92, ...], ...],               # 11×11 correlation
      "data_days": int,
    }
    """
    # Sort ascending, take last `days` rows
    df = lco_df.sort_index().tail(days)

    # Build spread time-series: Mn - M(n+1)
    spread_cols = []
    spread_labels = []
    for n in range(1, 12):
        col_a = f"c{n}"
        col_b = f"c{n + 1}"
        if col_a in df.columns and col_b in df.columns:
            s = (df[col_a] - df[col_b]).dropna()
            s.name = f"M{n}-M{n+1}"
            spread_cols.append(s)
            spread_labels.append(f"M{n}-M{n+1}")

    if len(spread_cols) < 2:
        n = len(spread_labels) or 11
        return {"labels": spread_labels, "matrix": [], "data_days": 0}

    spread_df = pd.concat(spread_cols, axis=1).dropna(how="all")
    n_days = len(spread_df)

    if n_days < 5:
        return {"labels": spread_labels, "matrix": [], "data_days": n_days}

    n = len(spread_labels)
    matrix = np.ones((n, n))
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            pair = spread_df.iloc[:, [i, j]].dropna()
            if len(pair) < 5:
                matrix[i][j] = np.nan
                continue
            c = float(pair.iloc[:, 0].corr(pair.iloc[:, 1]))
            matrix[i][j] = round(c, 3) if not np.isnan(c) else np.nan

    matrix_list = [
        [None if np.isnan(v) else v for v in row]
        for row in matrix.tolist()
    ]
    return {"labels": spread_labels, "matrix": matrix_list, "data_days": n_days}


def get_calendar_spreads(strips: dict) -> dict:
    """
    Compute current M1-M12 consecutive calendar spreads for Brent and WTI,
    plus a Brent spread correlation matrix (11×11) from LCO history.

    Parameters
    ----------
    strips : enriched_strips dict from get_term_structure (already computed)

    Returns
    -------
    {
      "brent": [{"label":"M1-M2","spread":float,"structure":"BACK"|"CONT"|"FLAT"}, ...],
      "wti":   [...],
      "brent_corr_matrix": {"labels":[...], "matrix":[...], "data_days": int},
    }
    """
    from fetchers.multi_curve import load_lco_history

    result: dict = {}

    for prod in ("brent", "wti"):
        strip_info = strips.get(prod, {})
        prices_list = strip_info.get("prices", [])
        prices = {item["month"]: item["price"] for item in prices_list}

        spreads = []
        for n in range(1, 12):
            ma = f"M{n}"
            mb = f"M{n + 1}"
            pa = prices.get(ma)
            pb = prices.get(mb)
            if pa is not None and pb is not None:
                val = round(pa - pb, 3)
                if val > 0.10:
                    struct = "BACK"
                elif val < -0.10:
                    struct = "CONT"
                else:
                    struct = "FLAT"
                spreads.append({"label": f"{ma}-{mb}", "spread": val, "structure": struct})
            else:
                spreads.append({"label": f"{ma}-{mb}", "spread": None, "structure": "N/A"})
        result[prod] = spreads

    # Brent spread correlation matrix from LCO xlsx history
    try:
        lco_df = load_lco_history()
        result["brent_corr_matrix"] = _build_calendar_spread_matrix(lco_df, days=90)
    except Exception as exc:
        log.warning("Calendar spread matrix failed: %s", exc)
        result["brent_corr_matrix"] = {"labels": [], "matrix": [], "data_days": 0}

    return result


# ══════════════════════════════════════════════════════════════════════════════
# Main public function
# ══════════════════════════════════════════════════════════════════════════════

def get_term_structure() -> dict:
    """
    Compute full term structure data for all five products.

    Returns the combined dict described in the module docstring.
    """
    from fetchers.multi_curve import get_all_strips, get_m1_history_all

    # ── Forward curve strips ──────────────────────────────────────────────────
    log.info("Fetching all forward curve strips …")
    raw_strips = get_all_strips(n=12)
    timestamp  = raw_strips.pop("timestamp", datetime.now(timezone.utc).isoformat(timespec="seconds"))

    enriched_strips: dict = {}
    for prod in _PRODUCTS:
        strip_list = raw_strips.get(prod, [])
        enriched_strips[prod] = _enrich_strip(strip_list)

    # ── M1 histories for correlation ──────────────────────────────────────────
    log.info("Fetching M1 histories for correlation matrix …")
    histories = get_m1_history_all(days=90)

    # ── Correlation matrix ────────────────────────────────────────────────────
    log.info("Building 5×5 correlation matrix …")
    corr = _build_correlation_matrix(histories, days=90)

    # ── Calendar spread matrix (M1-M2 … M11-M12) ─────────────────────────────
    log.info("Building calendar spread matrix …")
    cal_spreads = get_calendar_spreads(enriched_strips)

    return {
        "correlation_matrix": corr,
        "strips":             enriched_strips,
        "calendar_spreads":   cal_spreads,
        "timestamp":          timestamp,
    }


# ── __main__ — quick CLI test ─────────────────────────────────────────────────
if __name__ == "__main__":
    import json

    print("\nComputing term structure …\n")
    ts = get_term_structure()

    # Correlation matrix
    cm = ts["correlation_matrix"]
    print(f"=== CORRELATION MATRIX ({cm['data_days']} days) ===")
    header = f"{'':>12}" + "".join(f"{l:>10}" for l in cm["labels"])
    print(header)
    for i, (row, label) in enumerate(zip(cm["matrix"], cm["labels"])):
        cells = "".join(
            f"{v:>10.3f}" if v is not None else f"{'N/A':>10}"
            for v in row
        )
        print(f"  {label:>10}{cells}")

    # Strips
    print("\n=== FORWARD CURVE STRIPS ===")
    labels_map = dict(zip(_PRODUCTS, _LABELS))
    for prod in _PRODUCTS:
        info = ts["strips"][prod]
        p_list = [f"{p['price']:.2f}" if p["price"] else "N/A"
                  for p in info["prices"][:6]]
        score  = info["contango_score"]
        struct = info["structure"]
        print(f"\n  {labels_map[prod]} ({struct}, score={score})")
        print(f"    Strip: {' | '.join(p_list)} …")
        sp = info["spreads"]
        print(f"    M1-M3={sp['m1_m3']}  M3-M6={sp['m3_m6']}  "
              f"M6-M12={sp['m6_m12']}  M1-M12={sp['m1_m12']}")
