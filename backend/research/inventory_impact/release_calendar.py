"""
Release calendar — map each report week to the *exact* moment the market got it.

The EIA Weekly Petroleum Status Report covers the week ending the prior Friday
and is released the following **Wednesday 10:30 ET**. When a US federal holiday
falls Mon–Wed of release week, EIA pushes the release to **Thursday 11:00 ET**.
Getting this timestamp right is load-bearing: the whole event study aligns the
1-min tape to it, and a one-day error silently destroys every beta.

Two layers, belt-and-suspenders:
  scheduled_release(week_ending)   calendar rule (holiday-aware), in UTC.
  snap_to_spike(scheduled, lake)   nudges to the actual 10:30-ET minute by
                                   locating the abnormal 1-min move — robust to
                                   any scheduling quirk the calendar misses.

Public API
----------
  release_datetime(week_ending)  -> pd.Timestamp (UTC)   scheduled release
  release_table(week_endings)    -> pd.DataFrame          scheduled for many
  snap_to_spike(scheduled_utc, m1_1min) -> (ts, jump)     empirical release minute
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

_YEARS = range(2010, 2031)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """The nth (n≥1) or last (n=-1) `weekday` (Mon=0 … Sun=6) in a month."""
    if n > 0:
        first = date(year, month, 1)
        offset = (weekday - first.weekday()) % 7
        return first + timedelta(days=offset + 7 * (n - 1))
    last = date(year, month, calendar.monthrange(year, month)[1])
    offset = (last.weekday() - weekday) % 7
    return last - timedelta(days=offset)


def _observed(d: date) -> date:
    """Federal observed-date shift: a Saturday holiday is observed the Friday
    before, a Sunday holiday the Monday after (so EIA's Mon–Wed delay check sees
    the day offices actually close)."""
    if d.weekday() == 5:        # Saturday → Friday
        return d - timedelta(days=1)
    if d.weekday() == 6:        # Sunday → Monday
        return d + timedelta(days=1)
    return d


def _us_federal_holidays(years) -> set[date]:
    """Self-contained set of *observed* US federal holiday dates — the only ones
    that delay an EIA release. Used so the calendar stays correct even when the
    optional `holidays` package isn't installed (a silent empty set would mis-date
    every release — see the module docstring on why that's load-bearing)."""
    out: set[date] = set()
    for y in years:
        out.add(_observed(date(y, 1, 1)))        # New Year's Day
        out.add(_nth_weekday(y, 1, 0, 3))        # MLK Day        — 3rd Mon Jan
        out.add(_nth_weekday(y, 2, 0, 3))        # Presidents' Day— 3rd Mon Feb
        out.add(_nth_weekday(y, 5, 0, -1))       # Memorial Day   — last Mon May
        if y >= 2021:
            out.add(_observed(date(y, 6, 19)))   # Juneteenth (federal since 2021)
        out.add(_observed(date(y, 7, 4)))        # Independence Day
        out.add(_nth_weekday(y, 9, 0, 1))        # Labor Day      — 1st Mon Sep
        out.add(_nth_weekday(y, 10, 0, 2))       # Columbus Day   — 2nd Mon Oct
        out.add(_observed(date(y, 11, 11)))      # Veterans Day
        out.add(_nth_weekday(y, 11, 3, 4))       # Thanksgiving   — 4th Thu Nov
        out.add(_observed(date(y, 12, 25)))      # Christmas Day
    return out


# Prefer the `holidays` package when installed (full observance fidelity); fall
# back to the self-contained federal set otherwise. The old fallback was an empty
# dict, which silently disabled every holiday delay — the bug this replaces.
try:
    import holidays as _holidays_pkg
    _US_HOLIDAYS = _holidays_pkg.US(years=_YEARS)
except Exception:
    _US_HOLIDAYS = _us_federal_holidays(_YEARS)

_ET = ZoneInfo("America/New_York")
_UTC = ZoneInfo("UTC")
_RELEASE_TIME_NORMAL = time(10, 30)   # Wednesday 10:30 ET
_RELEASE_TIME_DELAYED = time(11, 0)   # holiday weeks → Thursday 11:00 ET


def _is_holiday(d: datetime) -> bool:
    return d.date() in _US_HOLIDAYS


def release_datetime(week_ending) -> pd.Timestamp:
    """
    Scheduled release datetime (UTC) for the report covering the week that ends
    on `week_ending` (a Friday). Wednesday 10:30 ET, shifted to Thursday 11:00 ET
    when a federal holiday falls Mon–Wed of release week.
    """
    we = pd.Timestamp(week_ending)
    # the report's Wednesday = week_ending Friday + 5 days
    wed = (we + pd.Timedelta(days=5)).date()
    wed = datetime(wed.year, wed.month, wed.day)

    # holiday Mon/Tue/Wed of release week → delay to Thursday
    mon = wed - pd.Timedelta(days=2)
    tue = wed - pd.Timedelta(days=1)
    delayed = any(_is_holiday(d) for d in (mon, tue, wed))

    if delayed:
        rel_day = wed + pd.Timedelta(days=1)         # Thursday
        rel_t = _RELEASE_TIME_DELAYED
    else:
        rel_day = wed
        rel_t = _RELEASE_TIME_NORMAL

    et_dt = datetime.combine(rel_day.date() if hasattr(rel_day, "date") else rel_day, rel_t, tzinfo=_ET)
    return pd.Timestamp(et_dt).tz_convert(_UTC)


def release_table(week_endings) -> pd.DataFrame:
    """Scheduled release datetimes (UTC) for an iterable of week-ending Fridays."""
    rows = []
    for we in week_endings:
        we = pd.Timestamp(we)
        rel = release_datetime(we)
        rows.append({
            "week_ending": we,
            "release_utc": rel,
            "release_et": rel.tz_convert(_ET),
            "delayed": rel.tz_convert(_ET).weekday() == 3,  # Thursday
        })
    return pd.DataFrame(rows).set_index("week_ending")


def snap_to_spike(
    scheduled_utc: pd.Timestamp,
    m1_1min: pd.Series,
    search_minutes: int = 90,
    require_jump: float = 0.0,
) -> tuple[pd.Timestamp | None, float]:
    """
    Snap a scheduled release to the empirical release minute by locating the
    abnormal 1-min move. `m1_1min` is a UTC-indexed front-month mid series.

    Searches ±`search_minutes` around the scheduled time for the minute with the
    largest absolute 1-min return; that's the print hitting the tape. Returns
    (snapped_ts, jump_bps). If the tape is empty in the window or the biggest
    move is below `require_jump` (bps), returns (None, 0.0) and the caller should
    fall back to the scheduled time.
    """
    if m1_1min is None or len(m1_1min) == 0:
        return None, 0.0
    lo = scheduled_utc - pd.Timedelta(minutes=search_minutes)
    hi = scheduled_utc + pd.Timedelta(minutes=search_minutes)
    win = m1_1min[(m1_1min.index >= lo) & (m1_1min.index <= hi)].dropna()
    if len(win) < 5:
        return None, 0.0
    ret = win.pct_change().abs() * 1e4  # bps
    if ret.dropna().empty:
        return None, 0.0
    snap_ts = ret.idxmax()
    jump = float(ret.max())
    if jump < require_jump:
        return None, 0.0
    return snap_ts, jump


if __name__ == "__main__":
    # show the upcoming + recent scheduled releases and flag holiday delays
    weeks = pd.date_range("2026-01-02", "2026-07-31", freq="W-FRI")
    tbl = release_table(weeks)
    print("Scheduled EIA crude releases (2026):\n")
    for we, r in tbl.iterrows():
        flag = "  <- DELAYED (holiday) Thursday" if r["delayed"] else ""
        print(f"  week ending {we.date()}  ->  {r['release_et']:%a %Y-%m-%d %H:%M %Z}{flag}")
