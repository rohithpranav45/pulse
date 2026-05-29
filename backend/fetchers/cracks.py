"""
Refinery crack spreads, VLCC freight proxy, and Saudi OSP.

Crack Spreads  (live yfinance data)
--------------------------------------
  3-2-1 crack    — (2×RBOB_bbl + 1×HO_bbl − 3×WTI) / 3
                   Most-watched US refining margin proxy
  5-3-2 crack    — (3×RBOB_bbl + 2×HO_bbl − 5×WTI) / 5
  Gasoline crack — RBOB_bbl − WTI
  Diesel crack   — HO_bbl  − WTI
  Brent crack    — RBOB_bbl − Brent  (European NWE proxy)

  Unit note: RBOB (RB=F) and Heating Oil (HO=F) trade in $/gallon.
             Multiply × 42 gal/bbl to convert to $/barrel.

VLCC Freight Proxy  (ESTIMATED — no free API for Baltic Exchange BDTI)
-----------------------------------------------------------------------
  Dubai crude estimated at Brent × 0.975 (Dubai ~97.5% of Brent historically).
  Brent-Dubai spread used as a proxy for VLCC demand tightness.
  VLCC rate estimate: rough empirical heuristic only.
  Baltic Exchange BDTI and TD3C rates require a paid subscription.

Saudi OSP  (HARDCODED — Aramco publishes monthly, no free API)
--------------------------------------------------------------
  Differentials vs regional benchmarks ($/bbl).
  Manually updated from Aramco monthly OSP press releases.
  Last updated: May 2026.

Public API
----------
  get_crack_spreads() → dict with all three sections
"""

import logging
from datetime import datetime, timezone

import yfinance as yf

log = logging.getLogger(__name__)

_GAL_TO_BBL = 42   # gallons per barrel

# ── Symbols ───────────────────────────────────────────────────────────────────
_CRACK_SYMBOLS = {
    "wti":         "CL=F",
    "brent":       "BZ=F",
    "rbob":        "RB=F",         # $/gallon (gasoline)
    "heating_oil": "HO=F",         # $/gallon (diesel/heat oil)
}

# ── Saudi OSP — hardcoded (Aramco monthly press release) ─────────────────────
# Differentials are relative to regional benchmark crude ($/bbl)
# Positive = premium, Negative = discount to benchmark
_SAUDI_OSP = {
    "as_of":       "May 2026",
    "data_source": "HARDCODED",
    "note":        "Source: Aramco OSP press releases. No machine-readable free API available.",
    "grades": {
        "Arab Light": {
            "Asia":  {"vs_benchmark": +1.70, "benchmark": "Oman/Dubai avg"},
            "NWE":   {"vs_benchmark": -0.80, "benchmark": "ICE Brent"},
            "USGC":  {"vs_benchmark": +3.60, "benchmark": "ASCI"},
        },
        "Arab Medium": {
            "Asia":  {"vs_benchmark": -0.20, "benchmark": "Oman/Dubai avg"},
            "NWE":   {"vs_benchmark": -3.50, "benchmark": "ICE Brent"},
            "USGC":  {"vs_benchmark": +2.50, "benchmark": "ASCI"},
        },
        "Arab Heavy": {
            "Asia":  {"vs_benchmark": -3.00, "benchmark": "Oman/Dubai avg"},
            "NWE":   {"vs_benchmark": -6.20, "benchmark": "ICE Brent"},
            "USGC":  {"vs_benchmark": -0.40, "benchmark": "ASCI"},
        },
    },
}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _fetch_closes() -> dict[str, list[float]]:
    """
    Fetch 1-year daily closes for all crack-spread inputs.
    Returns {key: [close_0, close_1, ..., close_n]} or {key: []} on failure.
    One yfinance call per symbol — avoids tz-join errors from batch download.
    """
    data: dict[str, list[float]] = {}
    for key, sym in _CRACK_SYMBOLS.items():
        try:
            hist  = yf.Ticker(sym).history(period="1y", auto_adjust=True)
            close = hist["Close"].dropna()
            if close.empty:
                raise ValueError("no data")
            data[key] = [float(v) for v in close]
        except Exception as exc:
            log.warning("Cracks: %s (%s) — %s", key, sym, exc)
            data[key] = []
    return data


def _last(series: list[float]):
    """Latest close, or None if series is empty."""
    return round(series[-1], 4) if series else None


def _avg(series: list[float], min_rows: int = 20):
    """Mean of all closes, or None if too few rows."""
    if len(series) < min_rows:
        return None
    return round(sum(series) / len(series), 4)


def _bbl(gal_price) -> float | None:
    """Convert $/gallon → $/barrel.  Returns None if input is None."""
    return round(gal_price * _GAL_TO_BBL, 3) if gal_price is not None else None


def _spread(a, b) -> float | None:
    if a is None or b is None:
        return None
    return round(a - b, 2)


def _crack321(rbob_b, ho_b, crude) -> float | None:
    if any(v is None for v in [rbob_b, ho_b, crude]):
        return None
    return round((2 * rbob_b + ho_b - 3 * crude) / 3, 2)


def _crack532(rbob_b, ho_b, crude) -> float | None:
    if any(v is None for v in [rbob_b, ho_b, crude]):
        return None
    return round((3 * rbob_b + 2 * ho_b - 5 * crude) / 5, 2)


def _sig(val, avg_v) -> str:
    """Signal label relative to 1Y average (±20% threshold)."""
    if val is None or avg_v is None or avg_v == 0:
        return "UNKNOWN"
    diff_pct = (val - avg_v) / abs(avg_v)
    if diff_pct > 0.20:
        return "WIDE"
    if diff_pct < -0.20:
        return "NARROW"
    return "NORMAL"


def _entry(val_now, val_avg) -> dict:
    return {
        "value":   val_now,
        "avg_1y":  val_avg,
        "vs_avg":  _spread(val_now, val_avg),
        "signal":  _sig(val_now, val_avg),
    }


# ── Public function ───────────────────────────────────────────────────────────

def get_crack_spreads() -> dict:
    """
    Compute crack spreads, VLCC freight proxy, and Saudi OSP.

    Returns
    -------
    {
      "crack_spreads": {
        "crack_321":         {value, avg_1y, vs_avg, signal},
        "crack_532":         {value, avg_1y, vs_avg, signal},
        "gasoline_crack":    {value, avg_1y, vs_avg, signal},
        "heating_oil_crack": {value, avg_1y, vs_avg, signal},
        "brent_crack":       {value, avg_1y, vs_avg, signal},
      },
      "input_prices": {wti, brent, rbob_gal, ho_gal, rbob_bbl, ho_bbl},
      "vlcc_proxy": {
        "brent_price":        float,
        "dubai_estimated":    float,
        "brent_dubai_spread": float,
        "proxy_rate_kUSD":    float,   # $/day in $000 (rough VLCC proxy)
        "context":            str,     # "TIGHT" | "NORMAL" | "SOFT"
        "data_source":        "ESTIMATED",
        "note":               str,
      },
      "saudi_osp":  { ... hardcoded ... },
      "stale":     bool,
      "timestamp": str,
    }
    """
    raw   = _fetch_closes()
    stale = any(len(v) == 0 for v in raw.values())

    # ── Current prices ────────────────────────────────────────────────────────
    wti_now   = _last(raw["wti"])
    brent_now = _last(raw["brent"])
    rbob_gal  = _last(raw["rbob"])
    ho_gal    = _last(raw["heating_oil"])

    rbob_bbl_now = _bbl(rbob_gal)
    ho_bbl_now   = _bbl(ho_gal)

    # ── 1-year average prices ─────────────────────────────────────────────────
    wti_avg   = _avg(raw["wti"])
    brent_avg = _avg(raw["brent"])
    rbob_avg  = _bbl(_avg(raw["rbob"]))
    ho_avg    = _bbl(_avg(raw["heating_oil"]))

    # ── Crack spreads — current ───────────────────────────────────────────────
    c321  = _crack321(rbob_bbl_now, ho_bbl_now,  wti_now)
    c532  = _crack532(rbob_bbl_now, ho_bbl_now,  wti_now)
    gas_c = _spread(rbob_bbl_now, wti_now)
    ho_c  = _spread(ho_bbl_now,   wti_now)
    brt_c = _spread(rbob_bbl_now, brent_now)

    # ── Crack spreads — 1Y average ────────────────────────────────────────────
    c321_a  = _crack321(rbob_avg, ho_avg, wti_avg)
    c532_a  = _crack532(rbob_avg, ho_avg, wti_avg)
    gas_ca  = _spread(rbob_avg, wti_avg)
    ho_ca   = _spread(ho_avg,   wti_avg)
    brt_ca  = _spread(rbob_avg, brent_avg)

    # ── VLCC freight proxy ────────────────────────────────────────────────────
    # Dubai crude typically trades at ~97.5% of Brent (2–3% discount).
    # Brent-Dubai spread widens when Atlantic Basin supply tightens relative
    # to the Middle East — proxy for VLCC demand strength.
    # Rough empirical heuristic:  TD3C ≈ base_rate + k × (B-D − long_run_avg)
    # This is intentionally rough — treat as directional only.
    dubai_est   = round(brent_now * 0.975, 2) if brent_now else None
    b_dubai     = _spread(brent_now, dubai_est)
    proxy_rate  = None
    if b_dubai is not None:
        # Historical B-D long-run avg ~$2.0; +$0.5 → ~+$3k/day on TD3C
        proxy_rate = round(40.0 + (b_dubai - 2.0) * 6.0, 1)   # $000/day

    vlcc_ctx = (
        "TIGHT"  if (proxy_rate or 0) > 52 else
        "NORMAL" if (proxy_rate or 0) > 36 else
        "SOFT"
    )

    return {
        "crack_spreads": {
            "crack_321":         _entry(c321,  c321_a),
            "crack_532":         _entry(c532,  c532_a),
            "gasoline_crack":    _entry(gas_c, gas_ca),
            "heating_oil_crack": _entry(ho_c,  ho_ca),
            "brent_crack":       _entry(brt_c, brt_ca),
        },
        "input_prices": {
            "wti":       wti_now,
            "brent":     brent_now,
            "rbob_gal":  rbob_gal,
            "ho_gal":    ho_gal,
            "rbob_bbl":  rbob_bbl_now,
            "ho_bbl":    ho_bbl_now,
        },
        "vlcc_proxy": {
            "brent_price":        brent_now,
            "dubai_estimated":    dubai_est,
            "brent_dubai_spread": b_dubai,
            "proxy_rate_kUSD":    proxy_rate,
            "context":            vlcc_ctx,
            "data_source":        "ESTIMATED",
            "note": (
                "Dubai crude estimated as Brent×0.975. "
                "VLCC proxy rate is a rough directional heuristic only. "
                "Baltic Exchange BDTI / TD3C requires a paid subscription."
            ),
        },
        "saudi_osp": _SAUDI_OSP,
        "stale":     stale,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# ── Test block ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    d  = get_crack_spreads()
    cs = d["crack_spreads"]
    ip = d["input_prices"]

    print(f"\n{'='*66}")
    print("  Input prices")
    print(f"{'='*66}")
    print(f"  WTI      : ${ip['wti']:.3f}/bbl")
    print(f"  Brent    : ${ip['brent']:.3f}/bbl")
    print(f"  RBOB     : ${ip['rbob_gal']:.4f}/gal  ->  ${ip['rbob_bbl']:.2f}/bbl")
    print(f"  Heat Oil : ${ip['ho_gal']:.4f}/gal  ->  ${ip['ho_bbl']:.2f}/bbl")

    print(f"\n{'='*66}")
    print("  Crack Spreads                    Current   1Y avg   vs avg   Signal")
    print(f"{'='*66}")
    NAMES = {
        "crack_321":         "3-2-1 crack         ",
        "crack_532":         "5-3-2 crack         ",
        "gasoline_crack":    "Gasoline crack      ",
        "heating_oil_crack": "Heating oil crack   ",
        "brent_crack":       "Brent crack (NWE)   ",
    }
    for key, row in cs.items():
        v, a, va, s = row["value"], row["avg_1y"], row["vs_avg"], row["signal"]
        fmt_v  = f"${v:>7.2f}" if v  else "    N/A"
        fmt_a  = f"${a:>7.2f}" if a  else "    N/A"
        fmt_va = f"{va:>+7.2f}" if va else "    N/A"
        print(f"  {NAMES.get(key, key):<22}  {fmt_v}   {fmt_a}  {fmt_va}   [{s}]")

    vp = d["vlcc_proxy"]
    print(f"\n{'='*66}")
    print(f"  VLCC Proxy  [{vp['data_source']}]")
    print(f"{'='*66}")
    print(f"  Brent         : ${vp['brent_price']:.2f}")
    print(f"  Dubai est.    : ${vp['dubai_estimated']:.2f}  (Brent × 0.975)")
    print(f"  B-D spread    : ${vp['brent_dubai_spread']:.2f}/bbl")
    print(f"  Proxy rate    : ${vp['proxy_rate_kUSD']:.0f}k/day  [{vp['context']}]")

    osp = d["saudi_osp"]
    print(f"\n{'='*66}")
    print(f"  Saudi Aramco OSP  [{osp['data_source']} — {osp['as_of']}]")
    print(f"{'='*66}")
    print(f"  {'Grade':<14}  {'Region':<5}  {'Differential':>12}  Benchmark")
    print(f"  {'-'*50}")
    for grade, regions in osp["grades"].items():
        for region, info in regions.items():
            diff = info["vs_benchmark"]
            sign = "+" if diff >= 0 else ""
            print(f"  {grade:<14}  {region:<5}  {sign}{diff:>+10.2f}  vs {info['benchmark']}")
