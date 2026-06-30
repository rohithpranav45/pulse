"""
Price-node series builder — what the geo-impact map regresses against.
======================================================================

Builds the daily PRICE NODES the geo engine measures, from the /Data tape:

  crude   : brent_flat (real C1 settle), wti_flat (synth C1), wti_brent,
            brent_structure (C1-C12), brent_m1_m2, brent_fly_123
  product : ho_crack    = HO×42  − WTI     (US ULSD/heating distillate crack)
            gasoil_crack = Gasoil/7.45 − Brent (ARA distillate crack)
            regrade     = (Gasoil/7.45) − (HO×42)  (ARA gasoil vs US ULSD, $/bbl)

Unit conversions (verified against the lake 2026-06: HO≈$2.47/gal, Gasoil≈
$733/tonne, WTI/Brent $/bbl; cracks land ≈ $30 — plausible):
  HO   $/gal   → $/bbl  × 42.0
  Gasoil $/tonne → $/bbl  ÷ 7.45   (standard ICE 0.1% gasoil density factor)

Provenance is reported per node — wti_flat / ho / gasoil are SYNTHESISED from
the last 1-min mid per session (not exchange settles, like get_wti_settlements),
so anything built on them is flagged ESTIMATE.

HONEST GAPS (declared, not silently approximated — these need a products/sour
feed to become real nodes):
  rbob_crack   — no gasoline curve in the lake (only a daily proxy via cracks.py)
  brent_dubai  — no Dubai/sour curve → no East-of-Suez sour differential
  cushing / wti_midland diffs — no US grade differentials in the lake

Public API
----------
  NODES                          catalog {id -> {label, unit, provenance, ...}}
  available_nodes()              ids we can actually compute right now
  gap_nodes()                    ids declared but not yet priceable
  compute_nodes(b, w, ho, go)    pure: daily frames -> node DataFrame (testable)
  build_node_panel()             load /Data + compute_nodes -> daily node panel
  describe()                     the catalog as a list of dicts (for the API)

Run standalone:  python -m backend.research.news_impact.geo.nodes
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

log = logging.getLogger("pulse.news_impact.geo.nodes")

# ── unit conversions to $/bbl ─────────────────────────────────────────────────
HO_GAL_PER_BBL = 42.0          # heating oil quoted $/gallon
GASOIL_BBL_PER_TONNE = 7.45    # ICE gasoil quoted $/tonne → bbl

# ── node catalog ──────────────────────────────────────────────────────────────
# provenance: "real" (exchange settle), "synth" (last 1-min mid/session), "gap"
NODES: dict[str, dict] = {
    "brent_flat":      {"label": "Brent front", "unit": "$/bbl", "provenance": "real",
                        "estimate": False, "available": True},
    "wti_flat":        {"label": "WTI front", "unit": "$/bbl", "provenance": "synth",
                        "estimate": True, "available": True},
    "wti_brent":       {"label": "WTI − Brent", "unit": "$/bbl", "provenance": "synth",
                        "estimate": True, "available": True},
    "brent_structure": {"label": "Brent M1-M12", "unit": "$/bbl", "provenance": "real",
                        "estimate": False, "available": True},
    "brent_m1_m2":     {"label": "Brent M1-M2", "unit": "$/bbl", "provenance": "real",
                        "estimate": False, "available": True},
    "brent_fly_123":   {"label": "Brent fly M1-2×M2+M3", "unit": "$/bbl", "provenance": "real",
                        "estimate": False, "available": True},
    "ho_crack":        {"label": "ULSD/HO crack vs WTI", "unit": "$/bbl", "provenance": "synth",
                        "estimate": True, "available": True},
    "gasoil_crack":    {"label": "Gasoil crack vs Brent", "unit": "$/bbl", "provenance": "synth",
                        "estimate": True, "available": True},
    "regrade":         {"label": "Gasoil − ULSD", "unit": "$/bbl", "provenance": "synth",
                        "estimate": True, "available": True},
    # RBOB gasoline crack — now REAL via the OHLCV products feed (was a gap). The
    # daily settle is the last hourly bar (session-end proxy), so it's an ESTIMATE.
    "rbob_crack":      {"label": "RBOB gasoline crack vs WTI", "unit": "$/bbl",
                        "provenance": "feed", "estimate": True, "available": True},
    # ── declared gaps (need a sour/grade feed) ──
    "brent_dubai":     {"label": "Brent − Dubai (EFS)", "unit": "$/bbl", "provenance": "gap",
                        "estimate": False, "available": False,
                        "gap_reason": "no Dubai/sour curve → no East-of-Suez differential"},
}


def available_nodes() -> list[str]:
    return [k for k, v in NODES.items() if v["available"]]


def gap_nodes() -> list[str]:
    return [k for k, v in NODES.items() if not v["available"]]


def describe() -> list[dict]:
    return [{"id": k, **v} for k, v in NODES.items()]


# ═════════════════════════════════════════════════════════════════════════════
# Pure computation (no I/O → unit-testable without /Data)
# ═════════════════════════════════════════════════════════════════════════════
def _autoscale_ho(ho_c1: pd.Series) -> pd.Series:
    """HO should be ~$2-5/gal. If the source is cents/gal (~250-500) divide by 100."""
    med = float(ho_c1.dropna().median()) if ho_c1.notna().any() else np.nan
    if med == med and med > 50:          # looks like cents/gal
        log.warning("nodes: HO median %.1f looks like cents/gal — scaling /100", med)
        return ho_c1 / 100.0
    return ho_c1


def compute_nodes(brent: pd.DataFrame | None,
                  wti: pd.DataFrame | None,
                  ho: pd.DataFrame | None,
                  gasoil: pd.DataFrame | None,
                  rbob: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Build the daily node panel from per-product daily frames (date-indexed, with
    c1.. columns; HO/Gasoil/RBOB need only c1). Any missing input simply omits the
    nodes that depend on it. Returns a date-indexed DataFrame of node columns.
    `rbob` (gasoline $/gal, from the OHLCV products feed) adds rbob_crack.
    """
    cols: dict[str, pd.Series] = {}

    bc1 = bc3 = bc12 = None
    if brent is not None and not brent.empty:
        bc1 = brent["c1"].astype(float)
        cols["brent_flat"] = bc1
        if {"c1", "c2"}.issubset(brent.columns):
            cols["brent_m1_m2"] = bc1 - brent["c2"].astype(float)
        if {"c1", "c2", "c3"}.issubset(brent.columns):
            cols["brent_fly_123"] = bc1 - 2 * brent["c2"].astype(float) + brent["c3"].astype(float)
        if "c12" in brent.columns:
            bc12 = brent["c12"].astype(float)
            cols["brent_structure"] = bc1 - bc12

    wc1 = None
    if wti is not None and not wti.empty and "c1" in wti.columns:
        wc1 = wti["c1"].astype(float)
        cols["wti_flat"] = wc1
        if bc1 is not None:
            cols["wti_brent"] = wc1 - bc1          # matches features.py sign

    ho_bbl = None
    if ho is not None and not ho.empty and "c1" in ho.columns:
        ho_bbl = _autoscale_ho(ho["c1"].astype(float)) * HO_GAL_PER_BBL
        if wc1 is not None:
            cols["ho_crack"] = ho_bbl - wc1        # US ULSD/heating crack vs WTI

    go_bbl = None
    if gasoil is not None and not gasoil.empty and "c1" in gasoil.columns:
        go_bbl = gasoil["c1"].astype(float) / GASOIL_BBL_PER_TONNE
        if bc1 is not None:
            cols["gasoil_crack"] = go_bbl - bc1    # ARA gasoil crack vs Brent

    if ho_bbl is not None and go_bbl is not None:
        cols["regrade"] = go_bbl - ho_bbl          # ARA gasoil vs US ULSD ($/bbl)

    if rbob is not None and not rbob.empty and "c1" in rbob.columns:
        rb_bbl = _autoscale_ho(rbob["c1"].astype(float)) * HO_GAL_PER_BBL   # $/gal → $/bbl
        if wc1 is not None:
            cols["rbob_crack"] = rb_bbl - wc1      # US gasoline (RBOB) crack vs WTI

    if not cols:
        return pd.DataFrame()
    panel = pd.concat(cols, axis=1).sort_index()
    panel.index.name = "date"
    return panel


# ═════════════════════════════════════════════════════════════════════════════
# /Data loaders (synthesise daily product settles from 1-min, like WTI)
# ═════════════════════════════════════════════════════════════════════════════
_daily_cache: dict[str, pd.DataFrame | None] = {}


def _synth_daily_from_1min(key: str, contracts: tuple[str, ...] = ("c1", "c2", "c3")
                           ) -> pd.DataFrame | None:
    """Last 1-min mid per session for the given 1-min view → date-indexed c1.. frame.
    Mirrors data_lake._build_wti_settlements_from_1min (session-end mid = ESTIMATE)."""
    if key in _daily_cache:
        return _daily_cache[key]
    import data_lake as dl
    if not dl.parquet_path(key).exists():
        log.warning("nodes: %s parquet missing — node(s) using it will be omitted", key)
        _daily_cache[key] = None
        return None
    con = dl.duckdb_conn()
    have = {r[0] for r in con.execute(
        f'SELECT column_name FROM (DESCRIBE SELECT * FROM "{key}")').fetchall()}
    use = [c for c in contracts if f"{c}||weighted_mid" in have]
    if not use:
        _daily_cache[key] = None
        return None
    sel = ", ".join(f's."{c}||weighted_mid" AS {c}' for c in use)
    sql = f"""
        WITH last_ts AS (
            SELECT CAST(timestamp AS DATE) AS d, MAX(timestamp) AS ts
            FROM "{key}" WHERE "c1||weighted_mid" IS NOT NULL
            GROUP BY CAST(timestamp AS DATE)
        )
        SELECT last_ts.d AS date, {sel}
        FROM last_ts JOIN "{key}" s ON s.timestamp = last_ts.ts
        ORDER BY date
    """
    df = con.execute(sql).df()
    if df.empty:
        _daily_cache[key] = None
        return None
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index().dropna(how="all")
    _daily_cache[key] = df
    return df


def _combine_tail(lake: pd.DataFrame | None,
                  feed: pd.DataFrame | None) -> pd.DataFrame | None:
    """Lake history EXTENDED with feed rows dated strictly after the lake's last
    date — so real exchange-settle history is preferred and the hourly-OHLCV feed
    only fills the recent gap (the lake stops 2026-05-26; the feed runs to 06-26)."""
    if lake is None or lake.empty:
        return feed
    if feed is None or feed.empty:
        return lake
    tail = feed[feed.index > lake.index.max()]
    if tail.empty:
        return lake
    return pd.concat([lake, tail], axis=0).sort_index()


def build_node_panel(use_products_feed: bool = True) -> pd.DataFrame:
    """Load the /Data tape and assemble the full daily node panel. When the OHLCV
    products feed is present (`use_products_feed`), it (1) EXTENDS brent/wti/ho/
    gasoil past the lake's last settle and (2) adds RBOB → rbob_crack. Empty frame
    if neither source is available."""
    try:
        import data_lake as dl
        brent = dl.get_brent_settlements()
        wti = dl.get_wti_settlements()
    except Exception as exc:  # /Data missing
        log.info("nodes: crude settlements unavailable (%s)", type(exc).__name__)
        brent = wti = None
    ho = _synth_daily_from_1min("ho_1min")
    gasoil = _synth_daily_from_1min("gasoil_1min")
    rbob = None

    if use_products_feed:
        try:
            from research.news_impact.geo import products_feed as pf
            if pf.available():
                feeds = pf.daily_settles()
                brent = _combine_tail(brent, feeds.get("LCO"))
                wti = _combine_tail(wti, feeds.get("CL"))
                ho = _combine_tail(ho, feeds.get("HO"))
                gasoil = _combine_tail(gasoil, feeds.get("LGO"))
                rbob = feeds.get("RBOB")
        except Exception as exc:
            log.info("nodes: products feed merge skipped (%s)", type(exc).__name__)

    return compute_nodes(brent, wti, ho, gasoil, rbob)


# ── standalone ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print("Node catalog:")
    for n in describe():
        tag = "OK " if n["available"] else "GAP"
        extra = f"  ({n.get('gap_reason')})" if not n["available"] else \
                ("  [ESTIMATE]" if n["estimate"] else "")
        print(f"  [{tag}] {n['id']:16s} {n['label']:26s} {n['provenance']}{extra}")

    print("\nBuilding node panel from /Data …")
    panel = build_node_panel()
    if panel.empty:
        print("EMPTY — /Data not available on this machine.")
        raise SystemExit(0)

    print(f"\nrows: {len(panel)}  ({panel.index.min().date()} .. {panel.index.max().date()})")
    print("\nlatest valid value per node (calendars differ, so show last non-NaN):")
    for c in panel.columns:
        s = panel[c].dropna()
        if s.empty:
            print(f"  {c:16s}      (no data)")
        else:
            print(f"  {c:16s} {s.iloc[-1]:+10.3f}   as of {s.index[-1].date()}")
    print("\nmedians (sanity — cracks should be ~$15-40, regrade small):")
    for c in panel.columns:
        print(f"  {c:16s} {panel[c].median():+10.3f}")
