"""
Data Lake — institutional-grade historical data loader
======================================================
Lazily loads files from the project-root /Data folder (provided by the desk).
All files cache as in-process pandas frames on first access.

Files served
------------
  brent_settlements_c1_to_c31  — daily Brent C1-C31 settlements 2016→latest (CSV, ~1MB)
  brent_close_c12_15y          — 15-year LCOc12 daily close (xlsx, ~70 KB)
  brent_c1_c12_spread_15y      — 15-year M1-M12 spread (xlsx, ~146 KB) — for percentile rank
  brent_daily_ohlcv_multi      — daily OHLCV + buy/sell volume per contract (xlsx, ~140 KB)
  brent_1min                   — 5-year Brent M1-M14 1-min mid prices (CSV, ~600 MB)
  brent_1min_volume            — 4-year Brent M1-M14 1-min mid + volume (CSV, ~520 MB)
  wti_1min                     — 5-year WTI M1-M14 1-min mid (CSV, ~550 MB)
  wti_1min_volume              — 4-year WTI M1-M14 1-min mid + volume (CSV, ~540 MB)
  ho_1min                      — 5-year Heating Oil M1-M14 1-min mid (CSV, ~495 MB)
  gasoil_1min                  — 5-year ICE Gasoil M1-M14 1-min mid (CSV, ~509 MB)
  brent_wti_spread_1min        — 5-year WTI-Brent calendar spread 1-min (CSV, ~550 MB)

The 1-min files are NOT loaded eagerly. Helpers below pull only the last
N days (or a specific contract column) so working set stays manageable.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
_BACKEND = Path(__file__).parent
_ROOT    = _BACKEND.parent
_DATA    = _ROOT / "Data"

FILES = {
    "brent_settlements_c1_to_c31": _DATA / "LCO_Brent_daily_settlement_c1_to_c31_2016_2026.csv",
    "brent_close_c12_15y":         _DATA / "LCO_Brent_daily_close_c12_2011_2026.xlsx",
    "brent_c1_c12_spread_15y":     _DATA / "LCO_Brent_daily_close_c1_c12_spread_2011_2026.xlsx",
    "brent_daily_ohlcv_multi":     _DATA / "LCO_Brent_daily_OHLCV_buysell_volume_multi_contract.xlsx",
    "brent_1min":                  _DATA / "LCO_Brent_1min_outrights_midprice_2021_2026.csv",
    "brent_1min_volume":           _DATA / "LCO_Brent_1min_outrights_midprice_volume_2022_2026.csv",
    "wti_1min":                    _DATA / "CL_WTI_1min_outrights_midprice_2021_2026.csv",
    "wti_1min_volume":             _DATA / "CL_WTI_1min_outrights_midprice_volume_2022_2026.csv",
    "ho_1min":                     _DATA / "HO_HeatingOil_1min_outrights_midprice_2021_2026.csv",
    "gasoil_1min":                 _DATA / "LGO_Gasoil_1min_outrights_midprice_2021_2026.csv",
    "brent_wti_spread_1min":       _DATA / "WTCL_LCO_Spread_1min_outrights_2021_2026.csv",
}


def available() -> bool:
    """True if the /Data directory exists and at least one file is present."""
    if not _DATA.exists():
        return False
    return any(p.exists() for p in FILES.values())


# ═════════════════════════════════════════════════════════════════════════════
# Daily / weekly files — load eagerly (small)
# ═════════════════════════════════════════════════════════════════════════════

_cache: dict = {}


def _load_settlements_c1_to_c31() -> Optional[pd.DataFrame]:
    """
    Brent C1-C31 daily settlements.

    File layout: 62 columns (LCOc1, LCOc1.1, LCOc2, LCOc2.1, …) — every
    contract has two columns (Timestamp, SETTLE) repeated.

    Returns a DataFrame indexed by date with columns c1 … c31 (float).
    """
    path = FILES["brent_settlements_c1_to_c31"]
    if not path.exists():
        log.warning("brent_settlements_c1_to_c31 not found at %s", path)
        return None

    # Row 0 is the header (LCOc1 / LCOc1.1 / …), row 1 says "Timestamp / SETTLE",
    # data starts row 2. We just read raw and use positional column indices.
    raw = pd.read_csv(path, header=None, skiprows=2, dtype=str)

    records = []
    for _, row in raw.iterrows():
        first_ts = row.iloc[0]
        if pd.isna(first_ts) or not str(first_ts).strip():
            continue
        # File uses DD-MM-YY (e.g. "26-05-26" = 26 May 2026, "05-01-16" = 5 Jan 2016)
        try:
            d = pd.to_datetime(str(first_ts).strip(), format="%d-%m-%y", errors="coerce")
            if pd.isna(d):
                continue
        except Exception:
            continue
        rec = {"date": d}
        for i in range(1, 32):
            col_idx = 1 + (i - 1) * 2  # SETTLE column for contract i
            if col_idx >= len(row):
                rec[f"c{i}"] = np.nan
                continue
            try:
                v = float(row.iloc[col_idx])
            except (TypeError, ValueError):
                v = np.nan
            rec[f"c{i}"] = v
        records.append(rec)

    if not records:
        return None
    df = pd.DataFrame(records).set_index("date").sort_index()
    log.info("data_lake: loaded Brent C1-C31 settlements — %d rows, %s → %s",
             len(df), df.index[0].date(), df.index[-1].date())
    return df


def _load_close_c12_15y() -> Optional[pd.DataFrame]:
    """15-year LCOc12 daily close — DataFrame indexed by date, column close."""
    path = FILES["brent_close_c12_15y"]
    if not path.exists():
        return None
    df = pd.read_excel(path, sheet_name=0)
    df = df.rename(columns={df.columns[0]: "date", df.columns[1]: "close"})
    df = df[pd.to_datetime(df["date"], errors="coerce").notna()]
    df["date"]  = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["close"]).set_index("date").sort_index()
    return df


def _load_c1_c12_spread_15y() -> Optional[pd.DataFrame]:
    """
    15-year Brent M1-M12 spread — DataFrame with columns c1, c12, m1_m12.
    Positive m1_m12 = backwardation. Used for percentile / regime classification.
    """
    path = FILES["brent_c1_c12_spread_15y"]
    if not path.exists():
        return None
    df = pd.read_excel(path, sheet_name=0)
    df = df.rename(columns={
        df.columns[0]: "date",
        df.columns[1]: "c1",
        df.columns[2]: "c12",
        df.columns[3]: "m1_m12",
    })
    df = df[pd.to_datetime(df["date"], errors="coerce").notna()]
    df["date"] = pd.to_datetime(df["date"])
    for c in ("c1", "c12", "m1_m12"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["m1_m12"]).set_index("date").sort_index()
    return df


def _load_brent_daily_ohlcv_multi() -> Optional[pd.DataFrame]:
    """
    Daily OHLCV + buy/sell volume per Brent contract.
    Columns: instrument, timestamp, open, high, low, close, volume,
             buyvolume, sellvolume, expiry.
    """
    path = FILES["brent_daily_ohlcv_multi"]
    if not path.exists():
        return None
    df = pd.read_excel(path, sheet_name=0)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    # Drop accidental duplicates (instrument + day)
    df = df.drop_duplicates(subset=["instrument", "timestamp"], keep="last")
    df = df.sort_values(["timestamp", "instrument"])
    return df


# Public accessors with caching
def get_brent_settlements() -> Optional[pd.DataFrame]:
    if "settlements" not in _cache:
        _cache["settlements"] = _load_settlements_c1_to_c31()
    return _cache["settlements"]


def get_c12_15y() -> Optional[pd.DataFrame]:
    if "c12_15y" not in _cache:
        _cache["c12_15y"] = _load_close_c12_15y()
    return _cache["c12_15y"]


def get_spread_15y() -> Optional[pd.DataFrame]:
    if "spread_15y" not in _cache:
        _cache["spread_15y"] = _load_c1_c12_spread_15y()
    return _cache["spread_15y"]


def get_brent_ohlcv_multi() -> Optional[pd.DataFrame]:
    if "ohlcv_multi" not in _cache:
        _cache["ohlcv_multi"] = _load_brent_daily_ohlcv_multi()
    return _cache["ohlcv_multi"]


# ═════════════════════════════════════════════════════════════════════════════
# 1-min files — lazy slice loader (NEVER load full files into memory)
# ═════════════════════════════════════════════════════════════════════════════

def load_1min_tail(
    key: str,
    days: int = 30,
    contract: str = "c1",
    field: str = "weighted_mid",
) -> Optional[pd.DataFrame]:
    """
    Load only the last `days` of one column from a 1-min file.

    Implementation: reads in chunks from end of file using tail-style read.
    For these CSVs the rows are time-ordered so we can read the entire file
    column-pruned with pandas (only the timestamp + the one column we need),
    then slice the tail. That keeps memory in the low-MB range.

    Returns a DataFrame with a single column named `field`, indexed by
    timestamp (UTC). None if file missing.
    """
    if key not in FILES:
        return None
    path = FILES[key]
    if not path.exists():
        log.warning("1-min file missing: %s", path)
        return None

    col_name = f"{contract}||{field}"

    # Read only the timestamp + the target column. The file has a meta-comment
    # row at line 0 (`#meta:1min||...`) — skip it.
    try:
        df = pd.read_csv(
            path,
            skiprows=1,
            usecols=["timestamp", col_name],
            engine="c",
        )
    except ValueError:
        # column doesn't exist in this file
        log.warning("Column %s not in %s", col_name, path.name)
        return None

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp"]).set_index("timestamp").sort_index()
    df = df.rename(columns={col_name: field})

    cutoff = df.index.max() - pd.Timedelta(days=days)
    return df[df.index >= cutoff]


def list_files() -> dict:
    """Return {key: {path, exists, size_mb}} for diagnostics."""
    out = {}
    for k, p in FILES.items():
        out[k] = {
            "path": str(p),
            "exists": p.exists(),
            "size_mb": round(p.stat().st_size / 1024 / 1024, 2) if p.exists() else 0.0,
        }
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print("Data lake at:", _DATA)
    print("Available:", available())
    for k, info in list_files().items():
        flag = "✓" if info["exists"] else "✗"
        print(f"  {flag} {k:30s} {info['size_mb']:>8.2f} MB")

    print("\n=== Brent settlements (latest 3) ===")
    df = get_brent_settlements()
    if df is not None:
        print(df.tail(3)[["c1", "c2", "c12", "c24"]])

    print("\n=== 15y M1-M12 spread (latest 3) ===")
    s = get_spread_15y()
    if s is not None:
        print(s.tail(3))

    print("\n=== Brent OHLCV multi (CO1 latest 3) ===")
    o = get_brent_ohlcv_multi()
    if o is not None:
        print(o[o["instrument"] == "CO1"].tail(3))

    print("\n=== Brent 1-min tail (last 1 day, c1 mid) ===")
    t = load_1min_tail("brent_1min", days=1, contract="c1", field="weighted_mid")
    if t is not None:
        print(f"rows: {len(t)}, range: {t.index.min()} → {t.index.max()}")
        print(t.head(3))
