"""
ECB euro reference exchange rates — free, no auth.
==================================================
ECB publishes a daily XML of 30+ FX rates vs EUR at 16:00 CET on each
working day. Used as a second-source EUR/USD for the macro panel.

  https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml

Public API
----------
  get_ecb_fx() -> dict
    {
      "available":  bool,
      "as_of":      "YYYY-MM-DD",
      "eur_usd":    float,
      "usd_eur":    float,
      "rates":      {"USD": 1.1234, "GBP": 0.84, ...},
      "source":     "ECB (eurofxref-daily.xml)",
      "stale":      bool,
      "timestamp":  iso str,
    }
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

log = logging.getLogger("pulse.ecb_fx")

URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
NS  = "{http://www.ecb.int/vocabulary/2002-08-01/eurofxref}"


def get_ecb_fx() -> dict:
    try:
        r = requests.get(URL, timeout=15)
        if r.status_code != 200:
            return _stale(f"HTTP {r.status_code}")
        root = ET.fromstring(r.content)
        cube_root = root.find(f"{NS}Cube")
        if cube_root is None:
            return _stale("malformed ECB XML")
        cube_day = cube_root.find(f"{NS}Cube")
        if cube_day is None:
            return _stale("no daily Cube")

        date = cube_day.get("time")
        rates = {}
        for cube in cube_day.findall(f"{NS}Cube"):
            ccy  = cube.get("currency")
            rate = cube.get("rate")
            if ccy and rate:
                try:
                    rates[ccy] = float(rate)
                except ValueError:
                    continue

        eur_usd = rates.get("USD")
        out = {
            "available":  True,
            "as_of":      date,
            "eur_usd":    eur_usd,
            "usd_eur":    round(1 / eur_usd, 4) if eur_usd else None,
            "rates":      rates,
            "source":     "ECB (eurofxref-daily.xml)",
            "stale":      False,
            "timestamp":  datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        return out
    except Exception as exc:
        log.warning("ECB FX failed: %s", exc)
        return _stale(str(exc)[:160])


def _stale(reason: str) -> dict:
    return {
        "available":  False,
        "as_of":      None,
        "eur_usd":    None,
        "usd_eur":    None,
        "rates":      {},
        "source":     "ECB (eurofxref-daily.xml)",
        "stale":      True,
        "error":      reason,
        "timestamp":  datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    r = get_ecb_fx()
    # Drop the long rates dict for printing
    short = {k: v for k, v in r.items() if k != "rates"}
    print(json.dumps(short, indent=2))
    print(f"\nrates: {len(r.get('rates', {}))} currencies")
