"""
Products OHLCV feed — RBOB / HO / LGO / LCO / CL continuous contracts.
======================================================================

A desk-supplied **hourly OHLCV** feed of continuous contracts (c1..c12) for the
refined-product + crude complex, on the office share
`I:\\Public\\Summer Interns Energy\\OHLCV` (override with `PULSE_OHLCV_DIR`):

  RBOB → gasoline    (RBc1..RBc12, $/gal)   — full history **2019-01 → 2026-06**
  HO   → US ULSD     (HOc1..,      $/gal)   — 2026-04-30 → 2026-06-26
  LGO  → ICE gasoil  (LGOc1..,     $/tonne) — 2026-04-30 → 2026-06-26
  LCO  → ICE Brent   (LCOc1..,     $/bbl)   — 2026-04-30 → 2026-06-26
  CL   → CME WTI     (CLc1..,      $/bbl)   — 2026-04-30 → 2026-06-26

Two things this unlocks for the geo engine:
  1. **RBOB** is the gasoline curve the lake never had → `rbob_crack` stops being a
     declared GAP node and becomes a real, gradeable node back to 2019.
  2. The crude/distillate products run to **2026-06-26**, *past* the lake's last
     settle (2026-05-26) → the daily node panel can be EXTENDED ~1 month to cover
     the June Iran/Hormuz war, the events the per-node study couldn't grade before.

Daily settle = the **last hourly `Last` per UTC calendar date** (the same
session-end proxy as the synth crude settles; flagged accordingly upstream).

Public API
----------
  OHLCV_DIR / available()                  feed location + presence
  PRODUCTS                                  the 5 product → file-prefix map
  load_continuous(product, n) -> DataFrame  hourly bars for contract c{n}
  daily_curve(product, n_contracts=12)      -> daily date-indexed c1..cN settle frame
  daily_settles()                           -> dict[product -> daily c1..c12 frame]

Run standalone:  python backend/research/news_impact/geo/products_feed.py
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import pandas as pd

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

log = logging.getLogger("pulse.news_impact.geo.products_feed")

# product directory -> contract-file prefix (RBOB files are RBc{n}, the rest match)
PRODUCTS = {"RBOB": "RB", "HO": "HO", "LGO": "LGO", "LCO": "LCO", "CL": "CL"}

_DEFAULT_DIR = r"I:\Public\Summer Interns Energy\OHLCV"


def ohlcv_dir() -> Path:
    return Path(os.getenv("PULSE_OHLCV_DIR", _DEFAULT_DIR))


OHLCV_DIR = ohlcv_dir()


def available(product: str | None = None) -> bool:
    d = ohlcv_dir()
    if product:
        return (d / product).is_dir()
    return d.is_dir() and any((d / p).is_dir() for p in PRODUCTS)


def _contract_path(product: str, n: int) -> Path:
    return ohlcv_dir() / product / f"{PRODUCTS[product]}c{n}.csv"


def load_continuous(product: str, n: int = 1) -> pd.DataFrame | None:
    """Hourly bars for continuous contract c{n} of `product`: a datetime-indexed
    (UTC) frame with open/high/low/last/volume. None if the file is absent."""
    if product not in PRODUCTS:
        raise ValueError(f"unknown product {product!r}")
    p = _contract_path(product, n)
    if not p.exists():
        return None
    df = pd.read_csv(p)
    # tolerate the leading '#' on the first column name (#RIC)
    df.columns = [c.lstrip("#").strip() for c in df.columns]
    if "Date-Time" not in df.columns or "Last" not in df.columns:
        log.warning("products_feed: unexpected columns in %s", p.name)
        return None
    ts = pd.to_datetime(df["Date-Time"], utc=True, errors="coerce")
    # build columns as raw arrays so there's no integer-index to misalign against ts
    def _num(col):
        return pd.to_numeric(df[col], errors="coerce").to_numpy() if col in df.columns else None
    out = pd.DataFrame({
        "open": _num("Open"), "high": _num("High"), "low": _num("Low"),
        "last": _num("Last"), "volume": _num("Volume"),
    }, index=pd.DatetimeIndex(ts))
    out = out[out.index.notna()].dropna(subset=["last"]).sort_index()
    return out if not out.empty else None


def _daily_settle(hourly: pd.DataFrame) -> pd.Series:
    """Last `last` per UTC calendar date → daily settle Series (date-indexed)."""
    s = hourly["last"].copy()
    s.index = pd.DatetimeIndex(s.index).tz_convert("UTC")
    daily = s.groupby(s.index.normalize().tz_localize(None)).last()
    daily.index.name = "date"
    return daily


def daily_curve(product: str, n_contracts: int = 12) -> pd.DataFrame | None:
    """Daily settle frame for `product` with columns c1..cN (date-indexed). Each
    column is the last hourly `Last` per UTC date for that contract. None if the
    product is absent."""
    cols: dict[str, pd.Series] = {}
    for n in range(1, n_contracts + 1):
        h = load_continuous(product, n)
        if h is not None and not h.empty:
            cols[f"c{n}"] = _daily_settle(h)
    if not cols:
        return None
    df = pd.concat(cols, axis=1).sort_index()
    df.index.name = "date"
    return df


def daily_settles(n_contracts: int = 12) -> dict[str, pd.DataFrame]:
    """Every available product → its daily c1..cN settle frame."""
    out: dict[str, pd.DataFrame] = {}
    for product in PRODUCTS:
        df = daily_curve(product, n_contracts)
        if df is not None:
            out[product] = df
    return out


# ── standalone ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    print(f"OHLCV feed dir: {ohlcv_dir()}  available={available()}")
    if not available():
        print("(feed not visible on this machine — set PULSE_OHLCV_DIR)")
        raise SystemExit(0)
    for product in PRODUCTS:
        df = daily_curve(product, 12)
        if df is None:
            print(f"  {product:5s} (absent)")
            continue
        c1 = df["c1"].dropna()
        print(f"  {product:5s} {df.shape[1]:2d} contracts  {len(c1):5d} days  "
              f"({c1.index.min().date()}..{c1.index.max().date()})  "
              f"c1 last={c1.iloc[-1]:.4f}")
