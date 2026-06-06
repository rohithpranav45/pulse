"""
JODI-Oil monthly crude production — free, authoritative, no auth.
=================================================================
Joint Organisations Data Initiative publishes monthly crude oil production
for 100+ countries (covering ~90% of global supply). This module pulls the
full primary CSV, filters to OPEC+ members and CRUDEOIL/INDPROD/KBD, and
caches the slim parquet locally for 7 days.

Replaces the HARDCODED OPEC compliance table in `fetchers/opec.py`.

Public API
----------
  get_jodi_opec_production() -> dict
    {
      "available":   bool,
      "as_of":       "YYYY-MM",
      "members":     [{name, iso, latest_kbd, mom_change_kbd, yoy_change_kbd}, …],
      "opec_total_kbd":      float,
      "opec_plus_total_kbd": float,
      "source":      "JODI-Oil World Database (monthly)",
      "stale":       bool,
      "timestamp":   iso str,
    }
"""

from __future__ import annotations

import io
import logging
import os
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

_BACKEND = Path(__file__).parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

log = logging.getLogger("pulse.jodi")

# ── Configuration ──────────────────────────────────────────────────────────
JODI_URL = "https://www.jodidata.org/_resources/files/downloads/oil-data/world_Primary_CSV.zip"

CACHE_DIR  = _BACKEND / "data" / "cache"
CACHE_FILE = CACHE_DIR / "jodi_opec_production.parquet"
CACHE_TTL_SECONDS = 7 * 86400  # weekly refresh

OPEC_MEMBERS = {
    "SA": "Saudi Arabia",
    "IQ": "Iraq",
    "IR": "Iran",
    "AE": "United Arab Emirates",
    "KW": "Kuwait",
    "VE": "Venezuela",
    "DZ": "Algeria",
    "NG": "Nigeria",
    "LY": "Libya",
    "CG": "Congo",
    "GA": "Gabon",
    "GQ": "Equatorial Guinea",
}
OPEC_PLUS_EXTRAS = {
    "RU": "Russia",
    "KZ": "Kazakhstan",
    "OM": "Oman",
    "BH": "Bahrain",
    "AZ": "Azerbaijan",
    "MX": "Mexico",
    "MY": "Malaysia",
    "BN": "Brunei",
    "SD": "Sudan",
    "SS": "South Sudan",
}


def _cache_fresh() -> bool:
    if not CACHE_FILE.exists():
        return False
    age = time.time() - CACHE_FILE.stat().st_mtime
    return age < CACHE_TTL_SECONDS


def _download_and_filter() -> pd.DataFrame:
    """Download JODI zip, extract CSV, filter to OPEC+ crude production."""
    log.info("Downloading JODI primary CSV (~23 MB zip)…")
    r = requests.get(JODI_URL, timeout=60, stream=True)
    r.raise_for_status()
    blob = io.BytesIO(r.content)
    with zipfile.ZipFile(blob) as z:
        member_name = z.namelist()[0]
        with z.open(member_name) as fh:
            # The full CSV is ~280 MB. Read it column-pruned + filtered in chunks.
            keep_iso = set(OPEC_MEMBERS) | set(OPEC_PLUS_EXTRAS)
            chunks = []
            for chunk in pd.read_csv(
                fh,
                chunksize=200_000,
                usecols=["REF_AREA", "TIME_PERIOD", "ENERGY_PRODUCT",
                         "FLOW_BREAKDOWN", "UNIT_MEASURE", "OBS_VALUE"],
                dtype=str,
            ):
                m = (
                    chunk["REF_AREA"].isin(keep_iso)
                    & (chunk["ENERGY_PRODUCT"] == "CRUDEOIL")
                    & (chunk["FLOW_BREAKDOWN"] == "INDPROD")
                    & (chunk["UNIT_MEASURE"] == "KBD")
                )
                if m.any():
                    chunks.append(chunk[m])
            if not chunks:
                raise RuntimeError("JODI CSV filter returned 0 rows")
            df = pd.concat(chunks, ignore_index=True)

    df["OBS_VALUE"] = pd.to_numeric(df["OBS_VALUE"], errors="coerce")
    df = df.dropna(subset=["OBS_VALUE"])
    df["TIME_PERIOD"] = pd.to_datetime(df["TIME_PERIOD"], format="%Y-%m", errors="coerce")
    df = df.dropna(subset=["TIME_PERIOD"])
    df = df.sort_values(["REF_AREA", "TIME_PERIOD"])

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(CACHE_FILE, index=False)
    except Exception:
        # Parquet engine may be missing — fall back to pickle
        df.to_pickle(CACHE_FILE.with_suffix(".pkl"))
    log.info("JODI cache built: %d rows, latest %s", len(df), df["TIME_PERIOD"].max())
    return df


def _load_cache() -> pd.DataFrame | None:
    if CACHE_FILE.exists():
        try:
            return pd.read_parquet(CACHE_FILE)
        except Exception:
            pass
    pkl = CACHE_FILE.with_suffix(".pkl")
    if pkl.exists():
        try:
            return pd.read_pickle(pkl)
        except Exception:
            pass
    return None


def get_jodi_opec_production() -> dict:
    """OPEC+ monthly crude production from JODI, with MoM/YoY change."""
    try:
        if _cache_fresh():
            df = _load_cache()
            if df is None:
                df = _download_and_filter()
        else:
            try:
                df = _download_and_filter()
            except Exception as exc:
                log.warning("JODI refresh failed (%s) — using cache", exc)
                df = _load_cache()
                if df is None:
                    raise
    except Exception as exc:
        log.error("JODI fetch failed completely: %s", exc)
        return {
            "available":   False,
            "members":     [],
            "opec_total_kbd":      None,
            "opec_plus_total_kbd": None,
            "as_of":       None,
            "source":      "JODI-Oil",
            "stale":       True,
            "error":       str(exc)[:200],
            "timestamp":   datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    latest_period = df["TIME_PERIOD"].max()
    yoy_period    = latest_period - pd.DateOffset(years=1)
    mom_period    = latest_period - pd.DateOffset(months=1)

    name_map = {**OPEC_MEMBERS, **OPEC_PLUS_EXTRAS}
    members_out = []
    opec_total = 0.0
    plus_total = 0.0

    for iso, name in name_map.items():
        rows = df[df["REF_AREA"] == iso]
        if rows.empty:
            continue
        latest_row = rows[rows["TIME_PERIOD"] == latest_period]
        latest_val = float(latest_row["OBS_VALUE"].iloc[0]) if not latest_row.empty else None
        if latest_val is None:
            continue

        mom_row = rows[rows["TIME_PERIOD"] == mom_period]
        mom_val = float(mom_row["OBS_VALUE"].iloc[0]) if not mom_row.empty else None
        mom_chg = round(latest_val - mom_val, 1) if mom_val is not None else None

        yoy_row = rows[rows["TIME_PERIOD"] == yoy_period]
        yoy_val = float(yoy_row["OBS_VALUE"].iloc[0]) if not yoy_row.empty else None
        yoy_chg = round(latest_val - yoy_val, 1) if yoy_val is not None else None

        members_out.append({
            "iso":            iso,
            "name":           name,
            "latest_kbd":     round(latest_val, 1),
            "mom_change_kbd": mom_chg,
            "yoy_change_kbd": yoy_chg,
            "is_opec":        iso in OPEC_MEMBERS,
        })

        if iso in OPEC_MEMBERS:
            opec_total += latest_val
        plus_total += latest_val

    members_out.sort(key=lambda x: x["latest_kbd"], reverse=True)

    return {
        "available":           True,
        "members":             members_out,
        "opec_total_kbd":      round(opec_total, 1),
        "opec_plus_total_kbd": round(plus_total, 1),
        "as_of":               latest_period.strftime("%Y-%m"),
        "source":              "JODI-Oil World Database (monthly)",
        "stale":               False,
        "timestamp":           datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    r = get_jodi_opec_production()
    print(f"available={r['available']}  as_of={r.get('as_of')}  members={len(r.get('members', []))}")
    print(f"OPEC total: {r.get('opec_total_kbd')} kbd")
    print(f"OPEC+ total: {r.get('opec_plus_total_kbd')} kbd")
    for m in r.get("members", [])[:8]:
        print(f"  {m['name']:<22} {m['latest_kbd']:>8.1f} kbd  (mom {m['mom_change_kbd']:+.1f}, yoy {m['yoy_change_kbd']:+.1f})")
