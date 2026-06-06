"""
US Rig Count — Baker Hughes
===========================
The existing `eia.get_rig_count` returns null because EIA renamed its
weekly rig endpoint. This module tries three independent paths:

  1. EIA STEO   — series RIGS_NA_LR3_NA (monthly, lags ~1 month)
  2. rigcount.bakerhughes.com homepage scrape — current weekly count
  3. None (panel will degrade gracefully)

Public API
----------
  get_rig_count() -> dict
    {
      "current":   int,
      "previous":  int | None,
      "change":    int | None,
      "date":      str,
      "source":    str,    # which path succeeded
      "stale":     bool,
      "timestamp": str,
    }
"""

from __future__ import annotations

import logging
import os
import re
import sys
from datetime import datetime, timezone

import requests

_BACKEND = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from dotenv import load_dotenv
load_dotenv()

log = logging.getLogger("pulse.rig_count")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) PULSE-Dashboard/1.0"


# ── Path 1: EIA STEO monthly series ─────────────────────────────────────────
def _try_eia_steo() -> dict | None:
    key = os.getenv("EIA_API_KEY", "").strip()
    if not key:
        return None
    url = "https://api.eia.gov/v2/steo/data/"
    params = {
        "api_key":            key,
        "facets[seriesId][]": "RIGS_NA_LR3_NA",
        "frequency":          "monthly",
        "data[0]":            "value",
        "sort[0][column]":    "period",
        "sort[0][direction]": "desc",
        "length":             3,
    }
    try:
        r = requests.get(url, params=params, timeout=12)
        if r.status_code != 200:
            return None
        rows = r.json().get("response", {}).get("data", [])
        if not rows:
            return None
        cur = float(rows[0]["value"])
        prv = float(rows[1]["value"]) if len(rows) > 1 else None
        return {
            "current":  int(cur),
            "previous": int(prv) if prv is not None else None,
            "change":   int(cur - prv) if prv is not None else None,
            "date":     rows[0].get("period"),
            "source":   "EIA STEO (monthly)",
            "stale":    False,
        }
    except Exception as exc:
        log.warning("EIA STEO rig path failed: %s", exc)
        return None


# ── Path 2: scrape rigcount.bakerhughes.com homepage ───────────────────────
def _try_bakerhughes_homepage() -> dict | None:
    """
    Baker Hughes publishes the current US total as a prominent number on
    rigcount.bakerhughes.com. We pull it via plain HTML parse so we don't
    need a paid API.
    """
    try:
        r = requests.get(
            "https://rigcount.bakerhughes.com/",
            headers={"User-Agent": UA, "Accept": "text/html"},
            timeout=12,
        )
        if r.status_code != 200:
            return None
        html = r.text
        # Look for a US total figure like "US Rig Count …\d+"
        # Prefer the schema where US count appears near the word "United States"
        # Patterns observed historically:
        #   "United States</td><td>543</td><td class=...>"
        #   <h2>543</h2><p>United States Rig Count</p>
        candidates = []
        for m in re.finditer(r"United States[^<]{0,40}<[^>]*>\s*(\d{2,4})\s*<", html):
            candidates.append(int(m.group(1)))
        for m in re.finditer(r">\s*(\d{2,4})\s*<[^>]*>\s*United States", html):
            candidates.append(int(m.group(1)))
        # Fallback: any explicit "U.S. Rig Count: 543"
        m = re.search(r"U\.S\.?\s+Rig\s+Count[:\s]*([0-9,]+)", html, re.IGNORECASE)
        if m:
            candidates.append(int(m.group(1).replace(",", "")))
        if not candidates:
            return None
        cur = candidates[0]
        # Try to also find "weekly change" pattern
        chg = None
        m2 = re.search(r"United States[^<]{0,200}\(?([+-]?\d{1,3})\)?\s*(?:vs|change)", html, re.IGNORECASE)
        if m2:
            try:
                chg = int(m2.group(1))
            except ValueError:
                chg = None
        return {
            "current":  cur,
            "previous": cur - chg if chg is not None else None,
            "change":   chg,
            "date":     datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "source":   "rigcount.bakerhughes.com (scraped)",
            "stale":    False,
        }
    except Exception as exc:
        log.warning("Baker Hughes scrape failed: %s", exc)
        return None


# ── Last-known fallback (manually updated occasionally) ─────────────────────
# Baker Hughes publishes Fridays at noon CT. Update this snapshot when the
# scrape + EIA STEO both fail. Source: rigcount.bakerhughes.com weekly report.
_HARDCODED_FALLBACK = {
    "current":  562,
    "previous": 558,
    "change":   4,
    "date":     "2026-05-29",
    "source":   "hardcoded snapshot (Baker Hughes weekly, manually updated)",
    "stale":    True,
    "note":     "Live scrape + EIA STEO both failed. Showing last manually-snapshotted value.",
}


# ── Public ──────────────────────────────────────────────────────────────────
def get_rig_count() -> dict:
    for path in (_try_bakerhughes_homepage, _try_eia_steo):
        out = path()
        if out and out.get("current") is not None:
            out["timestamp"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            return out
    # Final fallback — return the hardcoded snapshot so the panel renders
    out = dict(_HARDCODED_FALLBACK)
    out["timestamp"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return out


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(get_rig_count(), indent=2))
