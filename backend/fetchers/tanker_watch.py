"""
Tanker Watch — Live AIS ship positions near key oil chokepoints.

Source: aisstream.io WebSocket API (free tier, requires API key).
  https://aisstream.io/documentation

Chokepoints monitored
---------------------
  Strait of Hormuz      — ~35% of seaborne oil trade
  Bab el-Mandeb         — Red Sea gateway
  Suez Canal            — Europe-Asia shortcut
  Strait of Malacca     — Asia Pacific gateway
  Cape of Good Hope     — Africa bypass (no API key needed to monitor)

How it works
------------
  1. Open a WebSocket to wss://stream.aisstream.io/v0/stream
  2. Send a subscription message with bounding boxes for each chokepoint
  3. Collect messages for up to COLLECT_SECS seconds
  4. Filter for tanker vessels (AIS ship type 80-89)
  5. Group by chokepoint, count vessels, list recent positions
  6. Close the connection

Fallback
--------
  If AISSTREAM_API_KEY is not set or connection fails, returns static
  placeholder data with availability=False so the frontend can indicate
  the feature is unconfigured.

Public API
----------
  get_tanker_watch() → dict
    {
      "available":   bool,
      "chokepoints": [
        {
          "name":        str,
          "short_name":  str,
          "tankers":     int,     # tankers counted in this snapshot
          "vessels":     int,     # all vessel types counted
          "risk_level":  "LOW" | "MODERATE" | "HIGH" | "CRITICAL",
          "risk_color":  str,     # CSS colour string
          "tanker_list": [        # up to 5 most recent tankers
            {"mmsi": str, "name": str, "lat": float, "lon": float,
             "speed": float, "heading": int, "ago": str}
          ],
          "marine_traffic_url": str,
          "last_updated": str,
        },
        ...
      ],
      "note":      str,
      "timestamp": str,
    }
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ── Load env ──────────────────────────────────────────────────────────────────
_BACKEND = Path(__file__).parent.parent          # pulse/backend/
_ROOT    = _BACKEND.parent                       # pulse/
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")                  # pulse/.env — where keys actually live
except Exception:
    pass

AISSTREAM_KEY = os.getenv("AISSTREAM_API_KEY", "")

# ── Configuration ─────────────────────────────────────────────────────────────
COLLECT_SECS  = 12    # seconds to collect AIS messages per fetch
MAX_TANKERS   = 5     # max tankers to include in tanker_list per chokepoint

# AIS ship type codes for tankers: 80-89
_TANKER_TYPES = set(range(80, 90))

# ── Chokepoint definitions ────────────────────────────────────────────────────
# Bounding boxes: [min_lat, min_lon, max_lat, max_lon]
_CHOKEPOINTS = [
    {
        "name":       "Strait of Hormuz",
        "short_name": "HORMUZ",
        "bbox":       [55.5, 22.5, 57.5, 27.5],   # [min_lon, min_lat, max_lon, max_lat]
        "marine_traffic_url": "https://www.marinetraffic.com/en/ais/home/centerx:56.5/centery:26.5/zoom:10",
        "context":    "~35% of global seaborne oil passes here",
    },
    {
        "name":       "Bab el-Mandeb",
        "short_name": "BAB-EL-MANDEB",
        "bbox":       [42.5, 11.5, 44.0, 13.5],
        "marine_traffic_url": "https://www.marinetraffic.com/en/ais/home/centerx:43.5/centery:12.5/zoom:10",
        "context":    "Red Sea gateway — impacted by Houthi attacks",
    },
    {
        "name":       "Suez Canal",
        "short_name": "SUEZ",
        "bbox":       [32.0, 29.5, 33.0, 31.5],
        "marine_traffic_url": "https://www.marinetraffic.com/en/ais/home/centerx:32.5/centery:30.5/zoom:10",
        "context":    "Europe-Asia shortcut; bypassed → +15 days via Cape",
    },
    {
        "name":       "Strait of Malacca",
        "short_name": "MALACCA",
        "bbox":       [99.0, 1.0, 104.5, 6.5],
        "marine_traffic_url": "https://www.marinetraffic.com/en/ais/home/centerx:103.5/centery:1.5/zoom:9",
        "context":    "Asia Pacific gateway — ~25% of global trade",
    },
]

# ── Marine traffic shortcut URLs per chokepoint (for frontend links) ──────────
_MT_URLS = {cp["short_name"]: cp["marine_traffic_url"] for cp in _CHOKEPOINTS}


def _risk_level(tanker_count: int, name: str) -> tuple[str, str]:
    """
    Simple rule-based risk level from tanker count.
    Hormuz/Bab el-Mandeb elevated baseline due to geopolitics.
    """
    elevated = "HORMUZ" in name.upper() or "BAB" in name.upper() or "SUEZ" in name.upper()
    if tanker_count == 0:
        return ("MONITORING", "#6a88aa")
    if tanker_count <= 3:
        return ("LOW",      "#00c878") if not elevated else ("MODERATE", "#f0a500")
    if tanker_count <= 8:
        return ("MODERATE", "#f0a500") if not elevated else ("HIGH", "#e8455a")
    return ("HIGH",     "#e8455a") if not elevated else ("CRITICAL", "#ff0000")


def _ago(unix_ts: float) -> str:
    secs = int(time.time() - unix_ts)
    if secs < 60:   return "just now"
    if secs < 3600: return f"{secs//60}m ago"
    return f"{secs//3600}h ago"


def _fallback_data(reason: str) -> dict:
    """Return placeholder data when AIS feed is unavailable."""
    chkpts = []
    for cp in _CHOKEPOINTS:
        chkpts.append({
            "name":               cp["name"],
            "short_name":         cp["short_name"],
            "tankers":            None,
            "vessels":            None,
            "risk_level":         "MONITORING",
            "risk_color":         "#6a88aa",
            "tanker_list":        [],
            "marine_traffic_url": cp["marine_traffic_url"],
            "context":            cp["context"],
            "last_updated":       None,
        })
    return {
        "available":   False,
        "chokepoints": chkpts,
        "note":        reason,
        "timestamp":   datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _fetch_via_websocket() -> dict:
    """
    Open aisstream.io WebSocket, collect messages for COLLECT_SECS seconds,
    then close and return parsed results.
    """
    try:
        import websocket   # websocket-client
    except ImportError:
        return _fallback_data("websocket-client package not installed (pip install websocket-client)")

    # Build subscription message
    bboxes = [[cp["bbox"][1], cp["bbox"][0], cp["bbox"][3], cp["bbox"][2]]
              for cp in _CHOKEPOINTS]  # aisstream wants [min_lat,min_lon,max_lat,max_lon]

    sub_msg = json.dumps({
        "APIKey":        AISSTREAM_KEY,
        "BoundingBoxes": bboxes,
        "FilterMessageTypes": ["PositionReport"],
    })

    # Accumulate positions per chokepoint bbox
    # positions[i] = list of vessel dicts for _CHOKEPOINTS[i]
    positions: list[list[dict]] = [[] for _ in _CHOKEPOINTS]
    deadline = time.time() + COLLECT_SECS
    error_msg: Optional[str] = None

    ws = websocket.WebSocket()
    try:
        ws.connect("wss://stream.aisstream.io/v0/stream", timeout=10)
        ws.send(sub_msg)
        ws.settimeout(2)

        while time.time() < deadline:
            try:
                raw = ws.recv()
                if not raw:
                    continue
                msg = json.loads(raw)

                # Handle error from server
                if "error" in msg:
                    error_msg = msg["error"]
                    break

                meta     = msg.get("MetaData", {})
                position = msg.get("Message", {}).get("PositionReport", {})
                if not position:
                    continue

                mmsi     = str(meta.get("MMSI", ""))
                ship_name= meta.get("ShipName", "UNKNOWN").strip()
                ship_type= int(meta.get("ShipType", 0) or 0)
                lat      = float(position.get("Latitude",  0))
                lon      = float(position.get("Longitude", 0))
                speed    = float(position.get("Sog",       0))
                heading  = int(position.get("TrueHeading", 511) or 511)
                ts       = time.time()

                vessel = {
                    "mmsi":    mmsi,
                    "name":    ship_name or mmsi,
                    "lat":     round(lat, 4),
                    "lon":     round(lon, 4),
                    "speed":   round(speed, 1),
                    "heading": heading if heading != 511 else None,
                    "is_tanker": ship_type in _TANKER_TYPES,
                    "ts":      ts,
                }

                # Assign to chokepoint by bbox containment
                for i, cp in enumerate(_CHOKEPOINTS):
                    min_lon, min_lat, max_lon, max_lat = cp["bbox"]
                    if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
                        positions[i].append(vessel)
                        break

            except websocket.WebSocketTimeoutException:
                continue   # keep looping until deadline
            except Exception as exc:
                log.debug("AIS message error: %s", exc)
                continue

    except Exception as exc:
        error_msg = f"WebSocket connection failed: {exc}"
        log.warning("AIS stream error: %s", exc)
    finally:
        try:
            ws.close()
        except Exception:
            pass

    if error_msg:
        return _fallback_data(f"AIS stream error: {error_msg}")

    # Build result
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    chkpts  = []
    for i, cp in enumerate(_CHOKEPOINTS):
        vessels  = positions[i]
        tankers  = [v for v in vessels if v["is_tanker"]]
        # Deduplicate by MMSI, keep latest
        seen_mmsi: set = set()
        unique_tankers = []
        for v in sorted(tankers, key=lambda x: x["ts"], reverse=True):
            if v["mmsi"] not in seen_mmsi:
                seen_mmsi.add(v["mmsi"])
                unique_tankers.append(v)

        n_tankers = len(seen_mmsi)
        n_vessels = len({v["mmsi"] for v in vessels})
        risk, color = _risk_level(n_tankers, cp["name"])

        tanker_list = [
            {
                "mmsi":    v["mmsi"],
                "name":    v["name"],
                "lat":     v["lat"],
                "lon":     v["lon"],
                "speed":   v["speed"],
                "heading": v["heading"],
                "ago":     _ago(v["ts"]),
            }
            for v in unique_tankers[:MAX_TANKERS]
        ]

        chkpts.append({
            "name":               cp["name"],
            "short_name":         cp["short_name"],
            "tankers":            n_tankers,
            "vessels":            n_vessels,
            "risk_level":         risk,
            "risk_color":         color,
            "tanker_list":        tanker_list,
            "marine_traffic_url": cp["marine_traffic_url"],
            "context":            cp["context"],
            "last_updated":       now_iso,
        })

    log.info("AIS snapshot: %s",
             ", ".join(f"{c['short_name']}:{c['tankers']}T" for c in chkpts))

    return {
        "available":   True,
        "chokepoints": chkpts,
        "note":        f"Live AIS snapshot ({COLLECT_SECS}s window) via aisstream.io",
        "timestamp":   now_iso,
    }


def get_tanker_watch() -> dict:
    """
    Fetch live tanker positions near key chokepoints.

    Returns fallback data if AISSTREAM_API_KEY is not set.
    """
    if not AISSTREAM_KEY:
        return _fallback_data(
            "Set AISSTREAM_API_KEY in backend/.env to enable live tanker tracking. "
            "Free API key at https://aisstream.io"
        )
    return _fetch_via_websocket()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Fetching tanker watch data...\n")
    data = get_tanker_watch()
    print(f"Available: {data['available']}")
    print(f"Note: {data['note']}\n")
    for cp in data["chokepoints"]:
        print(f"  {cp['name']} — {cp['tankers']} tankers / {cp['vessels']} vessels"
              f" [{cp['risk_level']}]")
        for t in cp["tanker_list"][:3]:
            print(f"    {t['name']} ({t['mmsi']}) — {t['speed']}kn @ {t['ago']}")
