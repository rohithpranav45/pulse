"""
EIA Weekly Petroleum Status Report — surprise tracker.

The EIA publishes US crude oil stock data every Wednesday at 10:30 EST
(15:30 UTC). The market reaction is one of the most consistent
recurring intraday signals — chapter 6 of the curriculum calls it
"the single most market-moving regular data release in oil markets."

This module:
  1. Pulls the last N weeks of US crude commercial stock changes.
  2. Computes a model expectation (4-week moving average of changes).
  3. Surprise = actual change - expected change. >0 = bearish surprise
     (more crude than expected). <0 = bullish surprise (tighter than
     expected).
  4. For each release, looks up the Brent intraday price action in the
     hour after 15:30 UTC on that Wednesday using yfinance 5-min bars
     (when available — limited to ~60 days of history).
  5. Computes a simple linear regression between surprise (Mbbl) and
     1-hour Brent return (%) so the dashboard can show "expected price
     reaction per 1-Mbbl bearish surprise" — the trader-facing punchline.

Public function:
  get_eia_surprise(weeks=12) -> dict
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta, timezone

_BACKEND = os.path.abspath(os.path.dirname(__file__))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

log = logging.getLogger("pulse.eia_surprise")


def _silent_yf(ticker: str, period: str, interval: str):
    """yfinance fetch with its noisy ERROR logger muted."""
    import yfinance as yf
    yf_log = logging.getLogger("yfinance")
    prev = yf_log.level
    yf_log.setLevel(logging.CRITICAL)
    try:
        return yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True)
    except Exception as exc:
        log.debug("yf %s/%s failed: %s", ticker, interval, exc)
        return None
    finally:
        yf_log.setLevel(prev)


def _next_eia_release_utc(now: datetime | None = None) -> datetime:
    """
    Next EIA weekly release datetime in UTC.
    Released Wednesdays 10:30 EST = 15:30 UTC (standard time).
    During US daylight savings (mid-Mar → early-Nov), 10:30 EDT = 14:30 UTC.

    This is a deliberate approximation — for the dashboard countdown
    being within 15 minutes is fine.
    """
    now = now or datetime.now(timezone.utc)
    # Find next Wednesday
    days_ahead = (2 - now.weekday()) % 7  # weekday(): Mon=0 .. Sun=6, Wed=2
    candidate = now.replace(hour=14, minute=30, second=0, microsecond=0) + timedelta(days=days_ahead)
    # If we're already past today's Wednesday release window, skip 7 days
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def _stocks_history(weeks: int = 16) -> list[dict]:
    """Pull last `weeks` weekly US crude stock observations from EIA."""
    from fetchers.eia import _fetch_series
    rows = _fetch_series(
        "https://api.eia.gov/v2/petroleum/sum/sndw/data/",
        "WCRSTUS1",
        length=weeks + 8,  # buffer so we can compute 4-week MA at the start
    )
    # rows come back desc; reverse to chronological
    cleaned = []
    for r in reversed(rows):
        try:
            cleaned.append({
                "date": r["period"],
                "value": float(r["value"]),
            })
        except (TypeError, ValueError, KeyError):
            continue
    return cleaned


def _brent_intraday_return(release_dt_utc: datetime, lookahead_minutes: int = 60) -> float | None:
    """
    Compute Brent's % move in the first `lookahead_minutes` after the EIA
    release time. Returns None if intraday data is unavailable (yfinance
    5-min interval is capped at ~60 days of history).
    """
    df = _silent_yf("BZ=F", period="60d", interval="5m")
    if df is None or df.empty or "Close" not in df.columns:
        return None
    try:
        import pandas as pd
        df = df.copy()
        # yfinance intraday is tz-aware; convert to UTC
        idx = pd.to_datetime(df.index, utc=True)
        df.index = idx
        # Find bar at or just after release
        after = df.loc[df.index >= release_dt_utc]
        if after.empty:
            return None
        end_target = release_dt_utc + timedelta(minutes=lookahead_minutes)
        window = after.loc[after.index <= end_target]
        if window.empty:
            return None
        start = float(window["Close"].iloc[0])
        end = float(window["Close"].iloc[-1])
        if start <= 0:
            return None
        return round((end / start - 1) * 100, 3)
    except Exception as exc:
        log.debug("intraday return calc failed: %s", exc)
        return None


def _linreg(xs: list[float], ys: list[float]) -> dict | None:
    """Simple OLS linear regression. Returns slope/intercept/r²."""
    n = len(xs)
    if n < 3:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxy = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    sxx = sum((x - mean_x) ** 2 for x in xs)
    syy = sum((y - mean_y) ** 2 for y in ys)
    if sxx == 0:
        return None
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    r2 = (sxy ** 2) / (sxx * syy) if syy > 0 else 0
    return {"slope": round(slope, 4), "intercept": round(intercept, 4), "r2": round(r2, 3), "n": n}


def get_eia_surprise(weeks: int = 12) -> dict:
    """
    Return the EIA crude-stock surprise series for the last `weeks` releases.

    Returns
    -------
    {
      "releases": [
        {
          "date":          "2026-05-22",
          "release_utc":   "2026-05-21T14:30:00+00:00",
          "actual_change": -1850.0,           # Mbbl, signed
          "expected_change": -120.5,           # 4-wk MA
          "surprise":      -1729.5,            # actual - expected; negative = bullish
          "bullish":       true,               # surprise < 0
          "brent_1h_return_pct": -0.4,         # post-release intraday move (when available)
          "level":         816348.0,           # absolute stocks Mbbl
        },
        ...
      ],
      "regression":      {"slope": -0.0001, "intercept": 0.05, "r2": 0.12, "n": 8},
      "next_release_utc":"2026-05-28T14:30:00+00:00",
      "next_release_in_seconds": 86400,
      "timestamp":       "2026-05-29T07:00:00+00:00",
    }
    """
    try:
        hist = _stocks_history(weeks=weeks)
    except Exception as exc:
        log.warning("EIA stocks history fetch failed: %s", exc)
        hist = []

    releases: list[dict] = []
    # Need at least 5 weeks to compute the 4-wk MA for the first analyzed week.
    if len(hist) >= 5:
        changes = []  # absolute weekly change in Mbbl
        for i in range(1, len(hist)):
            prev = hist[i - 1]["value"]
            cur = hist[i]["value"]
            changes.append(cur - prev)

        # Now build the per-release rows starting from the 5th week
        for i in range(4, len(changes)):
            cur_change = changes[i]
            expected = sum(changes[i - 4:i]) / 4.0
            surprise = cur_change - expected
            date_str = hist[i + 1]["date"]
            # EIA data period is the *report week*; the release date is typically the
            # following Wednesday. We use this date directly + Wednesday 14:30 UTC.
            try:
                report_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                # Find the next Wednesday after the report date
                wed_offset = (2 - report_date.weekday()) % 7
                if wed_offset == 0 and report_date.hour >= 15:
                    wed_offset = 0
                release_dt = report_date.replace(hour=14, minute=30, second=0) + timedelta(days=wed_offset)
            except (ValueError, TypeError):
                release_dt = None

            brent_move = None
            if release_dt is not None:
                brent_move = _brent_intraday_return(release_dt, lookahead_minutes=60)

            releases.append({
                "date":               date_str,
                "release_utc":        release_dt.isoformat() if release_dt else None,
                "actual_change":      round(cur_change, 1),
                "expected_change":    round(expected, 1),
                "surprise":           round(surprise, 1),
                "bullish":            surprise < 0,
                "brent_1h_return_pct":brent_move,
                "level":              round(hist[i + 1]["value"], 1),
            })

    # Surprise → return regression (need at least 3 non-null pairs)
    pairs = [(r["surprise"], r["brent_1h_return_pct"])
             for r in releases if r["brent_1h_return_pct"] is not None]
    regression = _linreg([p[0] for p in pairs], [p[1] for p in pairs]) if len(pairs) >= 3 else None

    # Next release timer
    now = datetime.now(timezone.utc)
    next_release = _next_eia_release_utc(now)
    next_in = int((next_release - now).total_seconds())

    return {
        "releases":               releases,
        "regression":             regression,
        "next_release_utc":       next_release.isoformat(),
        "next_release_in_seconds":next_in,
        "timestamp":              now.isoformat(timespec="seconds"),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    d = get_eia_surprise(weeks=12)
    print(f"Next release: {d['next_release_utc']} (in {d['next_release_in_seconds']}s)")
    print(f"Releases: {len(d['releases'])}")
    for r in d["releases"][-8:]:
        bull = "BULL" if r["bullish"] else "BEAR"
        bm = f"  Brent 1h: {r['brent_1h_return_pct']:+.2f}%" if r["brent_1h_return_pct"] is not None else ""
        print(f"  {r['date']}  actual {r['actual_change']:+7.0f}  "
              f"expected {r['expected_change']:+7.0f}  surprise {r['surprise']:+7.0f}  [{bull}]{bm}")
    if d["regression"]:
        reg = d["regression"]
        print(f"\nRegression (Brent 1h%pct vs surprise Mbbl):")
        print(f"  return_pct ≈ {reg['slope']:+.5f} * surprise + {reg['intercept']:+.3f}")
        print(f"  r² = {reg['r2']}  n = {reg['n']}")
