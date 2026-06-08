"""
Sprint −1 — One-time /Data → Parquet converter
=================================================
Idempotent. Compares source mtime against the existing Parquet mtime and only
re-converts files whose source has changed since the last conversion. Source
CSV/xlsx are NEVER deleted — Parquet sits alongside as a fast query layer.

Usage:
    python -m backend.scripts.convert_data_lake          # convert what's stale
    python -m backend.scripts.convert_data_lake --force  # rebuild everything
    python -m backend.scripts.convert_data_lake --check  # report only, no work

Output:
    Data/parquet/<key>.parquet for each entry in data_lake.FILES

Daily/small files (settlements, spreads, OHLCV) are converted via pandas using
the same parsing logic that data_lake.py already uses — preserving the cleaned
schema (date index + c1..c31, etc.) rather than the messy 2-row header.

1-min files are streamed by DuckDB's COPY ... TO PARQUET (ZSTD), which never
loads the whole CSV into memory. Each 1-min CSV is ~600 MB; Parquet output
is typically 60–80 MB.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger("pulse.convert_data_lake")

_HERE    = Path(__file__).resolve().parent
_BACKEND = _HERE.parent
_ROOT    = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_DATA    = _ROOT / "Data"
_PARQUET = _DATA / "parquet"


# ─────────────────────────────────────────────────────────────────────────────
# File registry — single source of truth for source → parquet mapping
# ─────────────────────────────────────────────────────────────────────────────
SOURCES = {
    # daily / small — converted via pandas + existing loader logic
    "brent_settlements_c1_to_c31": {
        "src":  _DATA / "LCO_Brent_daily_settlement_c1_to_c31_2016_2026.csv",
        "kind": "settlements_c1_to_c31",
    },
    "brent_close_c12_15y": {
        "src":  _DATA / "LCO_Brent_daily_close_c12_2011_2026.xlsx",
        "kind": "close_c12",
    },
    "brent_c1_c12_spread_15y": {
        "src":  _DATA / "LCO_Brent_daily_close_c1_c12_spread_2011_2026.xlsx",
        "kind": "spread_c1_c12",
    },
    "brent_daily_ohlcv_multi": {
        "src":  _DATA / "LCO_Brent_daily_OHLCV_buysell_volume_multi_contract.xlsx",
        "kind": "ohlcv_multi",
    },
    # 1-min files — streamed via DuckDB COPY (CSV → parquet, no full load)
    "brent_1min": {
        "src":  _DATA / "LCO_Brent_1min_outrights_midprice_2021_2026.csv",
        "kind": "1min_csv",
    },
    "brent_1min_volume": {
        "src":  _DATA / "LCO_Brent_1min_outrights_midprice_volume_2022_2026.csv",
        "kind": "1min_csv",
    },
    "wti_1min": {
        "src":  _DATA / "CL_WTI_1min_outrights_midprice_2021_2026.csv",
        "kind": "1min_csv",
    },
    "wti_1min_volume": {
        "src":  _DATA / "CL_WTI_1min_outrights_midprice_volume_2022_2026.csv",
        "kind": "1min_csv",
    },
    "ho_1min": {
        "src":  _DATA / "HO_HeatingOil_1min_outrights_midprice_2021_2026.csv",
        "kind": "1min_csv",
    },
    "gasoil_1min": {
        "src":  _DATA / "LGO_Gasoil_1min_outrights_midprice_2021_2026.csv",
        "kind": "1min_csv",
    },
    "brent_wti_spread_1min": {
        "src":  _DATA / "WTCL_LCO_Spread_1min_outrights_2021_2026.csv",
        "kind": "1min_csv",
    },
}


def parquet_path(key: str) -> Path:
    return _PARQUET / f"{key}.parquet"


def is_stale(key: str) -> Optional[str]:
    """
    Return None if parquet is fresh enough; otherwise a short reason string.
    A parquet file is fresh when it exists and its mtime is >= source mtime.
    """
    src = SOURCES[key]["src"]
    pq  = parquet_path(key)
    if not src.exists():
        return "source missing"
    if not pq.exists():
        return "no parquet yet"
    if pq.stat().st_mtime < src.stat().st_mtime:
        return "source newer than parquet"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Converters per kind
# ─────────────────────────────────────────────────────────────────────────────
def _convert_settlements_c1_to_c31(src: Path, dst: Path) -> int:
    """Brent C1-C31 settlement file → clean (date, c1..c31) parquet."""
    import numpy as np
    import pandas as pd

    raw = pd.read_csv(src, header=None, skiprows=2, dtype=str)
    records = []
    for _, row in raw.iterrows():
        first_ts = row.iloc[0]
        if pd.isna(first_ts) or not str(first_ts).strip():
            continue
        d = pd.to_datetime(str(first_ts).strip(), format="%d-%m-%y", errors="coerce")
        if pd.isna(d):
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
    df = pd.DataFrame(records).sort_values("date").reset_index(drop=True)
    df.to_parquet(dst, engine="pyarrow", compression="zstd", index=False)
    return len(df)


def _convert_close_c12(src: Path, dst: Path) -> int:
    import pandas as pd

    df = pd.read_excel(src, sheet_name=0)
    df = df.rename(columns={df.columns[0]: "date", df.columns[1]: "close"})
    df = df[pd.to_datetime(df["date"], errors="coerce").notna()]
    df["date"]  = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
    df.to_parquet(dst, engine="pyarrow", compression="zstd", index=False)
    return len(df)


def _convert_spread_c1_c12(src: Path, dst: Path) -> int:
    import pandas as pd

    df = pd.read_excel(src, sheet_name=0)
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
    df = df.dropna(subset=["m1_m12"]).sort_values("date").reset_index(drop=True)
    df.to_parquet(dst, engine="pyarrow", compression="zstd", index=False)
    return len(df)


def _convert_ohlcv_multi(src: Path, dst: Path) -> int:
    import pandas as pd

    df = pd.read_excel(src, sheet_name=0)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    df = df.drop_duplicates(subset=["instrument", "timestamp"], keep="last")
    df = df.sort_values(["timestamp", "instrument"]).reset_index(drop=True)
    df.to_parquet(dst, engine="pyarrow", compression="zstd", index=False)
    return len(df)


def _convert_1min_csv(src: Path, dst: Path) -> int:
    """
    Stream a 1-min CSV (~600 MB) → ZSTD parquet via DuckDB COPY.
    The file's first line is a `#meta:` comment row; skip it with skip=1.
    """
    import duckdb

    con = duckdb.connect()
    try:
        con.execute(f"""
            COPY (
                SELECT * FROM read_csv_auto(
                    '{src.as_posix()}',
                    header=true,
                    skip=1,
                    sample_size=-1
                )
            )
            TO '{dst.as_posix()}'
            (FORMAT PARQUET, COMPRESSION ZSTD)
        """)
        n = con.execute(
            f"SELECT COUNT(*) FROM read_parquet('{dst.as_posix()}')"
        ).fetchone()[0]
    finally:
        con.close()
    return int(n)


_CONVERTERS = {
    "settlements_c1_to_c31": _convert_settlements_c1_to_c31,
    "close_c12":             _convert_close_c12,
    "spread_c1_c12":         _convert_spread_c1_c12,
    "ohlcv_multi":           _convert_ohlcv_multi,
    "1min_csv":              _convert_1min_csv,
}


# ─────────────────────────────────────────────────────────────────────────────
# Public driver
# ─────────────────────────────────────────────────────────────────────────────
def convert_one(key: str) -> dict:
    """Convert a single registry entry. Returns a result dict."""
    meta = SOURCES[key]
    src  = meta["src"]
    dst  = parquet_path(key)
    kind = meta["kind"]
    t0   = time.perf_counter()

    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".parquet.tmp")
    try:
        rows = _CONVERTERS[kind](src, tmp)
        tmp.replace(dst)
    except Exception as exc:
        if tmp.exists():
            try: tmp.unlink()
            except OSError: pass
        return {"key": key, "ok": False, "error": str(exc)}

    elapsed = time.perf_counter() - t0
    return {
        "key": key,
        "ok": True,
        "rows": rows,
        "src_mb": round(src.stat().st_size / 1024 / 1024, 2),
        "dst_mb": round(dst.stat().st_size / 1024 / 1024, 2),
        "elapsed_s": round(elapsed, 2),
    }


def convert_all(force: bool = False) -> list[dict]:
    """Convert every entry whose parquet is stale (or all if force=True)."""
    results = []
    for key in SOURCES:
        src = SOURCES[key]["src"]
        if not src.exists():
            results.append({"key": key, "ok": False, "skipped": True,
                            "error": "source missing"})
            continue
        reason = is_stale(key)
        if reason is None and not force:
            results.append({"key": key, "ok": True, "skipped": True,
                            "reason": "up to date"})
            continue
        log.info("convert %s (%s)", key, "forced" if force else reason)
        results.append(convert_one(key))
    return results


def any_stale() -> bool:
    """Cheap predicate for start.py — true if any source needs conversion."""
    for key in SOURCES:
        if SOURCES[key]["src"].exists() and is_stale(key):
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def _print_report(results: list[dict]) -> None:
    ok = sum(1 for r in results if r.get("ok") and not r.get("skipped"))
    sk = sum(1 for r in results if r.get("skipped"))
    bad = sum(1 for r in results if not r.get("ok"))
    print(f"\nConverted: {ok}   Skipped (fresh): {sk}   Failed: {bad}\n")
    for r in results:
        key = r["key"]
        if r.get("skipped"):
            msg = r.get("reason") or r.get("error") or "skipped"
            print(f"  -  {key:32s}  {msg}")
        elif r.get("ok"):
            print(f"  OK {key:32s}  {r['rows']:>10,} rows   "
                  f"{r['src_mb']:>7.1f} MB -> {r['dst_mb']:>6.1f} MB   "
                  f"{r['elapsed_s']:>6.2f}s")
        else:
            print(f"  ER {key:32s}  {r.get('error')}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--force", action="store_true",
                        help="Re-convert every file even if Parquet is fresh.")
    parser.add_argument("--check", action="store_true",
                        help="Report what would be converted; do not write.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    if not _DATA.exists():
        print(f"Data dir not found: {_DATA}")
        return 1

    if args.check:
        print(f"Parquet target: {_PARQUET}\n")
        any_work = False
        for key in SOURCES:
            src = SOURCES[key]["src"]
            if not src.exists():
                print(f"  -  {key:32s}  source missing")
                continue
            reason = is_stale(key)
            if reason is None:
                print(f"  OK {key:32s}  fresh")
            else:
                any_work = True
                print(f"  >> {key:32s}  needs convert ({reason})")
        return 0 if not any_work else 0

    results = convert_all(force=args.force)
    _print_report(results)
    return 0 if all(r.get("ok") for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
