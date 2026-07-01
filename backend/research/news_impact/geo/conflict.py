"""
ACLED conflict feed — quantitative geopolitical-risk channel for oil.
====================================================================

The desk-supplied ACLED panel (political-violence event counts, 2021→2025) for
the oil producers / transit states. Two uses:

  1. A **conflict-intensity regime** — trailing-window z-score of a country's (or
     the oil-bloc's) event count — a continuous geopolitical-risk state to gate /
     condition the geo node impacts (a Hormuz headline in a HIGH-conflict month is
     not the same event as in a calm one).
  2. A **graded study**: does oil-bloc conflict intensity actually co-move with
     crude? Reuses the Brent settle tape (data_lake) resampled monthly. Honest
     read: ACLED ends 2025-06, so it covers the pre-war 2021-2025 era + the very
     first war month (Iran 8→443 in 2025-06) — a natural step-change to test.

Public API
----------
  OIL_COUNTRIES                          the bloc we track
  load_conflict(freq="monthly"|"daily")  -> DataFrame (date-indexed, per-country + TOTAL)
  bloc_intensity(freq=)                  -> Series (oil-bloc sum)
  conflict_regime(country=, asof=, ...)  -> {z, level, value}  (HIGH/NORMAL/LOW)
  oil_conflict_study()                   -> dict  (corr of bloc conflict vs Brent monthly move)

Run standalone:  python backend/research/news_impact/geo/conflict.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

log = logging.getLogger("pulse.news_impact.geo.conflict")

_GEO_DATA = Path(__file__).parent.parent.parent.parent / "data" / "research" / "news_impact" / "geo"
_CSV = {"daily": _GEO_DATA / "acled_conflict_daily.csv",
        "monthly": _GEO_DATA / "acled_conflict_monthly.csv"}

# oil producers / chokepoint states present in the ACLED panel
OIL_COUNTRIES = ["Iran", "Iraq", "Nigeria", "Libya", "Yemen", "Saudi Arabia",
                 "Venezuela", "Russia"]
Z_HIGH, Z_LOW = 1.0, -1.0


def available(freq: str = "monthly") -> bool:
    return _CSV.get(freq, Path("/nonexistent")).exists()


def load_conflict(freq: str = "monthly") -> pd.DataFrame:
    """Date-indexed conflict-count frame (per country + TOTAL). Empty if absent."""
    p = _CSV.get(freq)
    if not p or not p.exists():
        log.info("ACLED %s not found", freq)
        return pd.DataFrame()
    df = pd.read_csv(p)
    datecol = df.columns[0]
    df[datecol] = pd.to_datetime(df[datecol], errors="coerce",
                                 format="%Y-%m" if freq == "monthly" else None)
    df = df.dropna(subset=[datecol]).set_index(datecol).sort_index()
    return df.apply(pd.to_numeric, errors="coerce")


def bloc_intensity(freq: str = "monthly") -> pd.Series:
    """Summed event count across the oil bloc (ex-TOTAL), per period."""
    df = load_conflict(freq)
    if df.empty:
        return pd.Series(dtype=float)
    cols = [c for c in OIL_COUNTRIES if c in df.columns]
    return df[cols].sum(axis=1, min_count=1)


def conflict_regime(country: str = "Iran", asof=None, freq: str = "monthly",
                    window: int = 12) -> dict:
    """Trailing-window z-score of a country's (or 'BLOC') conflict count → a
    HIGH/NORMAL/LOW geopolitical-risk regime as of `asof` (causal: uses only
    observations up to `asof`)."""
    s = bloc_intensity(freq) if country.upper() == "BLOC" else load_conflict(freq).get(country)
    if s is None or s.empty:
        return {"country": country, "z": None, "level": "UNKNOWN", "value": None}
    s = s.dropna()
    if asof is not None:
        s = s[s.index <= pd.to_datetime(asof)]
    if len(s) < max(3, window // 2):
        return {"country": country, "z": None, "level": "UNKNOWN", "value": None}
    val = float(s.iloc[-1])
    ref = s.iloc[-(window + 1):-1] if len(s) > window else s.iloc[:-1]
    mu, sd = float(ref.mean()), float(ref.std())
    z = (val - mu) / sd if sd and sd > 0 else 0.0
    level = "HIGH" if z >= Z_HIGH else ("LOW" if z <= Z_LOW else "NORMAL")
    return {"country": country, "z": round(z, 2), "level": level, "value": val,
            "as_of": str(s.index[-1].date())}


def oil_conflict_study() -> dict:
    """Does oil-bloc conflict intensity co-move with crude? Correlate the monthly
    ACLED bloc count (and its MoM change) with the same-month Brent % move, over
    the overlap. Descriptive (small N, war-tail-driven) — reported honestly."""
    intensity = bloc_intensity("monthly")
    if intensity.empty:
        return {"available": False}
    try:
        import data_lake as dl
        b = dl.get_brent_settlements()
        bm = b["c1"].astype(float).resample("MS").last()
    except Exception:
        return {"available": False, "reason": "no Brent tape"}
    ret = (bm.pct_change() * 100.0)
    intensity.index = intensity.index.to_period("M").to_timestamp()
    df = pd.concat({"conflict": intensity, "d_conflict": intensity.diff(),
                    "brent_ret": ret}, axis=1).dropna()
    if len(df) < 12:
        return {"available": False, "n": int(len(df))}

    def _corr(a, b):
        return round(float(np.corrcoef(a, b)[0, 1]), 3) if a.std() and b.std() else None
    iran = load_conflict("monthly").get("Iran")
    iran = iran.reindex(df.index) if iran is not None else None
    return {
        "available": True, "n": int(len(df)),
        "span": [str(df.index.min().date()), str(df.index.max().date())],
        "corr_level_ret": _corr(df["conflict"], df["brent_ret"]),
        "corr_change_ret": _corr(df["d_conflict"], df["brent_ret"]),
        "corr_iran_change_ret": (_corr(iran.diff().reindex(df.index).fillna(0), df["brent_ret"])
                                 if iran is not None else None),
        "note": ("Descriptive monthly co-movement, oil-bloc ACLED vs Brent. ACLED ends "
                 "2025-06 so the sample is the pre-war era + the first war month — read "
                 "as characterisation, not a tradeable signal."),
    }


# ── standalone ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.WARNING)

    m = load_conflict("monthly")
    print(f"ACLED monthly: {len(m)} rows"
          + (f"  ({m.index.min().date()} .. {m.index.max().date()})" if not m.empty else ""))
    print("\nconflict regime now (per country):")
    for c in ["BLOC", "Iran", "Russia", "Yemen", "Saudi Arabia"]:
        r = conflict_regime(c)
        print(f"  {c:14s} value={r['value']} z={r['z']} -> {r['level']}")

    print("\n=== oil-bloc conflict vs Brent monthly move (graded) ===")
    st = oil_conflict_study()
    for k, v in st.items():
        print(f"  {k}: {v}")
