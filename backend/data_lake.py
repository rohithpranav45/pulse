"""
Data Lake — institutional-grade historical data loader
======================================================
Lazily loads files from the project-root /Data folder (provided by the desk).
Sprint −1 onwards: backed by Parquet + DuckDB. Source CSV/xlsx are still on
disk (gitignored, unchanged) and `FILES[*]` still points at them so legacy
consumers continue to work. New code should prefer:

  * the public accessors (`get_brent_settlements()`, `load_1min_tail()`, …)
    — these now read Parquet via DuckDB and are ~50× faster on the 1-min files
  * `duckdb_conn()` — get a connection with every parquet file pre-registered
    as a view (`brent_1min`, `wti_1min`, etc.), so you can run direct SQL like
    `SELECT MIN(timestamp), MAX(timestamp) FROM brent_1min`.

Files served
------------
  brent_settlements_c1_to_c31  — daily Brent C1-C31 settlements 2016→latest
  brent_close_c12_15y          — 15-year LCOc12 daily close
  brent_c1_c12_spread_15y      — 15-year M1-M12 spread (for percentile rank)
  brent_daily_ohlcv_multi      — daily OHLCV + buy/sell volume per contract
  brent_1min                   — 5-year Brent M1-M14 1-min mid prices
  brent_1min_volume            — 4-year Brent M1-M14 1-min mid + volume
  wti_1min                     — 5-year WTI M1-M14 1-min mid
  wti_1min_volume              — 4-year WTI M1-M14 1-min mid + volume
  ho_1min                      — 5-year Heating Oil M1-M14 1-min mid
  gasoil_1min                  — 5-year ICE Gasoil M1-M14 1-min mid
  brent_wti_spread_1min        — 5-year WTI-Brent calendar spread 1-min

Public API
----------
  available()                  → bool
  list_files()                 → dict
  get_brent_settlements()      → DataFrame (date-indexed, c1..c31)
  get_c12_15y()                → DataFrame (date-indexed, close)
  get_spread_15y()             → DataFrame (date-indexed, c1, c12, m1_m12)
  get_brent_ohlcv_multi()      → DataFrame (instrument, timestamp, ...)
  load_1min_tail(key, days, contract, field) → DataFrame (timestamp-indexed)
  duckdb_conn()                → duckdb.DuckDBPyConnection
  parquet_path(key)            → Path
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

_BACKEND = Path(__file__).parent
_ROOT    = _BACKEND.parent
_DATA    = _ROOT / "Data"
_PARQUET = _DATA / "parquet"

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
    """True if the /Data directory exists and at least one source file is present."""
    if not _DATA.exists():
        return False
    return any(p.exists() for p in FILES.values())


def parquet_path(key: str) -> Path:
    """Return the parquet file path for a given source key (may or may not exist)."""
    return _PARQUET / f"{key}.parquet"


# ═════════════════════════════════════════════════════════════════════════════
# DuckDB connection — process-wide, lazy
# ═════════════════════════════════════════════════════════════════════════════
_DUCK_LOCK = threading.Lock()
_DUCK: Optional["duckdb.DuckDBPyConnection"] = None  # type: ignore


def duckdb_conn():
    """
    Return a process-wide DuckDB connection with every available parquet file
    pre-registered as a view named after the source key. Examples:

        con = duckdb_conn()
        con.execute("SELECT MAX(timestamp) FROM brent_1min").fetchone()
        con.execute("SELECT * FROM brent_settlements_c1_to_c31 LIMIT 5").df()

    Views are only created for keys whose parquet file currently exists; the
    connection is lazily (re)built the first time it's requested and reused
    thereafter. Use `reset_duckdb()` after a re-conversion to pick up changes.
    """
    global _DUCK
    with _DUCK_LOCK:
        if _DUCK is not None:
            return _DUCK
        try:
            import duckdb
        except ImportError as exc:
            raise RuntimeError(
                "duckdb is required by data_lake; install with "
                "`pip install duckdb` (see requirements.txt)"
            ) from exc
        con = duckdb.connect(database=":memory:")
        # Single-threaded reads are plenty for our workload, and they keep the
        # memory footprint flat under 100 MB.
        con.execute("PRAGMA threads=2")
        for key in FILES:
            pq = parquet_path(key)
            if pq.exists():
                con.execute(
                    f'CREATE OR REPLACE VIEW "{key}" AS '
                    f"SELECT * FROM read_parquet('{pq.as_posix()}')"
                )
        _DUCK = con
        return _DUCK


def reset_duckdb() -> None:
    """Drop the cached connection so the next caller sees newly-written parquet."""
    global _DUCK
    with _DUCK_LOCK:
        if _DUCK is not None:
            try: _DUCK.close()
            except Exception: pass
        _DUCK = None


# ═════════════════════════════════════════════════════════════════════════════
# Daily / weekly files — DuckDB-backed with pandas fallback
# ═════════════════════════════════════════════════════════════════════════════
_cache: dict = {}


def _parquet_or_none(key: str) -> Optional[pd.DataFrame]:
    """Read a parquet file via DuckDB. Returns None if it doesn't exist."""
    pq = parquet_path(key)
    if not pq.exists():
        return None
    con = duckdb_conn()
    return con.execute(f'SELECT * FROM "{key}"').df()


def _load_settlements_c1_to_c31() -> Optional[pd.DataFrame]:
    """
    Brent C1-C31 daily settlements.
    Returns a DataFrame indexed by date with columns c1 … c31 (float).
    """
    df = _parquet_or_none("brent_settlements_c1_to_c31")
    if df is not None:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        log.info("data_lake: loaded Brent C1-C31 settlements from parquet - "
                 "%d rows, %s to %s", len(df), df.index[0].date(), df.index[-1].date())
        return df

    path = FILES["brent_settlements_c1_to_c31"]
    if not path.exists():
        log.warning("brent_settlements_c1_to_c31 not found at %s", path)
        return None
    raw = pd.read_csv(path, header=None, skiprows=2, dtype=str)
    records = []
    for _, row in raw.iterrows():
        first_ts = row.iloc[0]
        if pd.isna(first_ts) or not str(first_ts).strip():
            continue
        try:
            d = pd.to_datetime(str(first_ts).strip(), format="%d-%m-%y", errors="coerce")
            if pd.isna(d):
                continue
        except Exception:
            continue
        rec = {"date": d}
        for i in range(1, 32):
            col_idx = 1 + (i - 1) * 2
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
    log.info("data_lake: loaded Brent C1-C31 settlements from csv (slow path) — "
             "%d rows", len(df))
    return df


def _load_close_c12_15y() -> Optional[pd.DataFrame]:
    """15-year LCOc12 daily close — DataFrame indexed by date, column close."""
    df = _parquet_or_none("brent_close_c12_15y")
    if df is not None:
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date").sort_index()

    path = FILES["brent_close_c12_15y"]
    if not path.exists():
        return None
    df = pd.read_excel(path, sheet_name=0)
    df = df.rename(columns={df.columns[0]: "date", df.columns[1]: "close"})
    df = df[pd.to_datetime(df["date"], errors="coerce").notna()]
    df["date"]  = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.dropna(subset=["close"]).set_index("date").sort_index()


def _load_c1_c12_spread_15y() -> Optional[pd.DataFrame]:
    """
    15-year Brent M1-M12 spread — DataFrame with columns c1, c12, m1_m12.
    Positive m1_m12 = backwardation. Used for percentile / regime classification.
    """
    df = _parquet_or_none("brent_c1_c12_spread_15y")
    if df is not None:
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date").sort_index()

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
    return df.dropna(subset=["m1_m12"]).set_index("date").sort_index()


def _load_brent_daily_ohlcv_multi() -> Optional[pd.DataFrame]:
    """
    Daily OHLCV + buy/sell volume per Brent contract.
    Columns: instrument, timestamp, open, high, low, close, volume,
             buyvolume, sellvolume, expiry.
    """
    df = _parquet_or_none("brent_daily_ohlcv_multi")
    if df is not None:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df.sort_values(["timestamp", "instrument"]).reset_index(drop=True)

    path = FILES["brent_daily_ohlcv_multi"]
    if not path.exists():
        return None
    df = pd.read_excel(path, sheet_name=0)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    df = df.drop_duplicates(subset=["instrument", "timestamp"], keep="last")
    return df.sort_values(["timestamp", "instrument"]).reset_index(drop=True)


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
# 1-min files — DuckDB-backed slice loader
# ═════════════════════════════════════════════════════════════════════════════
def load_1min_tail(
    key: str,
    days: int = 30,
    contract: str = "c1",
    field: str = "weighted_mid",
) -> Optional[pd.DataFrame]:
    """
    Load the last `days` of one column from a 1-min file.

    With Parquet present, this is a pushdown predicate scan that touches only
    the trailing row groups — typically <500 ms even for 5 years of data and
    <100 MB peak RAM. Without parquet it falls back to a column-pruned CSV
    read (the original behaviour).

    Returns a DataFrame with a single column named `field`, indexed by
    timestamp (UTC). None if file/column missing.
    """
    if key not in FILES:
        return None

    col_name = f"{contract}||{field}"
    pq = parquet_path(key)

    if pq.exists():
        con = duckdb_conn()
        # Column presence check
        cols = [r[0] for r in con.execute(
            f"SELECT column_name FROM (DESCRIBE SELECT * FROM \"{key}\")"
        ).fetchall()]
        if col_name not in cols:
            log.warning("Column %s not in parquet %s", col_name, pq.name)
            return None

        # Use INTERVAL on the file's own max timestamp so historical files
        # (where 'now' is well past the last data point) still return tails.
        sql = f"""
            WITH bounds AS (
                SELECT MAX(timestamp) AS max_ts FROM "{key}"
            )
            SELECT timestamp, "{col_name}" AS {field}
            FROM "{key}", bounds
            WHERE timestamp >= bounds.max_ts - INTERVAL {days} DAY
            ORDER BY timestamp
        """
        df = con.execute(sql).df()
        if df.empty:
            return df
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df.set_index("timestamp")

    # ── Fallback: column-pruned CSV read ─────────────────────────────────────
    path = FILES[key]
    if not path.exists():
        log.warning("1-min file missing: %s", path)
        return None
    try:
        df = pd.read_csv(
            path,
            skiprows=1,
            usecols=["timestamp", col_name],
            engine="c",
        )
    except ValueError:
        log.warning("Column %s not in %s", col_name, path.name)
        return None
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp"]).set_index("timestamp").sort_index()
    df = df.rename(columns={col_name: field})
    cutoff = df.index.max() - pd.Timedelta(days=days)
    return df[df.index >= cutoff]


def list_files() -> dict:
    """Return {key: {path, exists, size_mb, parquet_mb}} for diagnostics."""
    out = {}
    for k, p in FILES.items():
        pq = parquet_path(k)
        out[k] = {
            "path": str(p),
            "exists": p.exists(),
            "size_mb": round(p.stat().st_size / 1024 / 1024, 2) if p.exists() else 0.0,
            "parquet_exists": pq.exists(),
            "parquet_mb": round(pq.stat().st_size / 1024 / 1024, 2) if pq.exists() else 0.0,
        }
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print("Data lake at:", _DATA)
    print("Parquet at: ", _PARQUET)
    print("Available: ", available())
    for k, info in list_files().items():
        flag = "ok" if info["exists"] else "--"
        pq   = "pq" if info["parquet_exists"] else "  "
        print(f"  [{flag}/{pq}] {k:30s} src={info['size_mb']:>7.2f}MB  "
              f"parquet={info['parquet_mb']:>6.2f}MB")

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
        print(f"rows: {len(t)}, range: {t.index.min()} to {t.index.max()}")
        print(t.head(3))
