"""
PULSE Flask REST API
====================
Serves all data fetchers and model outputs to the dashboard.

Run:
    python api/app.py          (from pulse/ project root)

Endpoints:
    GET /api/health
    GET /api/prices
    GET /api/curve
    GET /api/fair-value
    GET /api/signal
    GET /api/correlations
    GET /api/fundamentals
    GET /api/news
    GET /api/weather
    GET /api/technicals
    GET /api/term-structure
    GET /api/macro
    GET /api/patterns
    GET /api/all

TTL strategy:
    prices       30 s   — near real-time tick data
    curve        300 s  — futures strip, changes slowly intraday
    fair_value   300 s  — model depends on prices + slow fundamentals
    signal       300 s  — synthesised, as fast as slowest component
    news         300 s  — news feed refresh cadence
    fundamentals 3600 s — EIA/COT/OPEC data is weekly or daily
    correlations 3600 s — rolling windows, very stable intraday
"""

import os
import sys
import threading
import time
import logging
from datetime import datetime, timezone

# ── ensure backend/ and project root are on sys.path ─────────────────────────
_BACKEND = os.path.abspath(os.path.dirname(__file__))          # pulse/backend/
_ROOT    = os.path.abspath(os.path.join(_BACKEND, ".."))       # pulse/
for _p in (_BACKEND, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime as _dt

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pulse.api")

_STATIC_DIR = os.path.join(_BACKEND, "static")
app = Flask(__name__, static_folder=None)
CORS(app)   # allow all origins — dashboard may be served from a different port


# ─── Serve built React app ───────────────────────────────────────────────────
from flask import send_from_directory  # type: ignore


@app.route("/")
def _index():
    idx = os.path.join(_STATIC_DIR, "index.html")
    if os.path.exists(idx):
        return send_from_directory(_STATIC_DIR, "index.html")
    return (
        "<html><body style='background:#070b14;color:#eef2f9;font-family:sans-serif;padding:40px'>"
        "<h2 style='color:#d4af37'>PULSE — React build missing</h2>"
        "<p>Run <code>cd frontend && npm install && npm run build</code>, then refresh.</p>"
        "<p>Or run <code>cd frontend && npm run dev</code> and open <a href='http://127.0.0.1:5173' style='color:#22d3ee'>http://127.0.0.1:5173</a></p>"
        "</body></html>",
        200,
    )


@app.route("/<path:path>")
def _static_proxy(path):
    if path.startswith("api/"):
        return ("Not found", 404)
    full = os.path.join(_STATIC_DIR, path)
    if os.path.exists(full) and os.path.isfile(full):
        return send_from_directory(_STATIC_DIR, path)
    # SPA fallback
    idx = os.path.join(_STATIC_DIR, "index.html")
    if os.path.exists(idx):
        return send_from_directory(_STATIC_DIR, "index.html")
    return ("Not found", 404)

# ─────────────────────────────────────────────────────────────────────────────
# SQLite-backed TTL cache (db/cache.py) — drop-in replacement
# ─────────────────────────────────────────────────────────────────────────────

from db.cache import get_cached as _db_get_cached, set_cache


def get_cached(key: str, ttl_seconds: int):
    """Cache read — returns None when ?nocache=1 is present on the request."""
    try:
        from flask import has_request_context, request as _req
        if has_request_context() and _req.args.get("nocache"):
            return None
    except Exception:
        pass
    return _db_get_cached(key, ttl_seconds)


# TTL constants (seconds)
TTL_PRICES       = 60
TTL_OHLCV        = 60      # intraday 5-min candles — refresh every minute
TTL_CURVE        = 600
TTL_FAIR_VALUE   = 600
TTL_SIGNAL       = 600
TTL_NEWS         = 600
TTL_WEATHER      = 3600    # Open-Meteo updates hourly
TTL_TECHNICALS   = 300     # derived from prices, refresh every 5 min
TTL_FUNDAMENTALS = 7200
TTL_CORRELATIONS = 7200
TTL_HISTORY      = 3600    # daily candles — refresh once per hour
TTL_TERM_STRUCTURE = 3600  # forward strips + correlation matrix
TTL_MACRO          = 3600  # FRED data updates once daily at most
TTL_PATTERNS       = 3600  # scipy pattern scan — close series changes daily
TTL_IV             = 300   # options IV — refresh every 5 min
TTL_TRADE          = 600   # trade idea + Ollama brief — refresh every 10 min
TTL_ALERTS         = 60    # alert checks — refresh every minute
TTL_CRACKS         = 600   # crack spreads — refresh every 10 min
TTL_STEO           = 86400 # EIA STEO — daily publication cycle
TTL_ANALYST_WATCH  = 900   # Nitter/Truth Social RSS — 15-min refresh
TTL_TANKER_WATCH   = 300   # AIS snapshot — 5-min refresh
TTL_SPREADS_HIST   = 3600  # daily spread history — once per hour
TTL_EIA_SURPRISE   = 3600  # EIA surprise tracker — once per hour


# ─────────────────────────────────────────────────────────────────────────────
# Error-safe wrapper
# ─────────────────────────────────────────────────────────────────────────────

def safe_fetch(func, fallback=None):
    """
    Call func() and return its result.
    On any exception, log the error and return fallback.
    Handles lambdas (which have no meaningful __name__).
    """
    name = getattr(func, "__name__", None) or repr(func)
    try:
        return func()
    except Exception as exc:
        log.error("%s failed: %s", name, exc)
        return fallback


# ─────────────────────────────────────────────────────────────────────────────
# Lazy imports — each fetcher/model is imported on first call so the server
# starts instantly even before the warm-up thread finishes.
# ─────────────────────────────────────────────────────────────────────────────

def _prices():
    from fetchers.prices import get_live_prices
    return get_live_prices()

def _curve():
    from fetchers.curve import get_both_curves
    return get_both_curves()

def _fair_value_brent():
    from models.fair_value import calculate_fair_value
    return calculate_fair_value("brent")

def _fair_value_wti():
    from models.fair_value import calculate_fair_value
    return calculate_fair_value("wti")

def _signal():
    from models.signal_engine import get_all_signals
    return get_all_signals()

def _correlation_matrix():
    from models.correlations import get_correlation_matrix
    return get_correlation_matrix()

def _curve_correlation():
    from models.correlations import get_curve_correlation
    return get_curve_correlation()

def _brent_wti_analysis():
    from models.correlations import get_brent_wti_analysis
    return get_brent_wti_analysis()

def _inventory():
    from fetchers.eia import get_inventory_vs_seasonal
    return get_inventory_vs_seasonal()

def _snapshot():
    from fetchers.eia import get_inventory_snapshot
    return get_inventory_snapshot()

def _rig_count():
    from fetchers.eia import get_rig_count
    return get_rig_count()

def _opec_eia():
    from fetchers.eia import get_opec_eia_production
    return get_opec_eia_production()

def _spark_dark(hh_price=None):
    from fetchers.eia import get_spark_dark_spread
    return get_spark_dark_spread(hh_price)

def _cot():
    from fetchers.cot import get_positioning_percentile
    return get_positioning_percentile()

def _opec():
    from fetchers.opec import get_compliance_table
    return get_compliance_table()

def _geo_risk():
    from fetchers.geo_risk import calculate_geo_risk
    return calculate_geo_risk()

def _news():
    from fetchers.news import get_energy_news
    return get_energy_news()

def _weather():
    from fetchers.weather import get_weather_signal
    return get_weather_signal()

def _technicals():
    from fetchers.technicals import get_all_technicals
    return get_all_technicals()

def _term_structure():
    from models.term_structure import get_term_structure
    return get_term_structure()

def _seasonality():
    from fetchers.seasonality import get_seasonality
    return get_seasonality()

def _macro():
    from fetchers.macro import get_macro_data
    return get_macro_data()

def _patterns():
    from models.patterns import get_patterns
    return get_patterns("Brent")

def _iv():
    from fetchers.options_iv import get_iv
    return get_iv()

def _alerts():
    from models.alerts import check_alerts
    fund = _fetch_fundamentals()
    return check_alerts(
        _fetch_prices(),
        _fetch_technicals(),
        fund,
        fund.get("cot", {}) if isinstance(fund, dict) else {},
        iv=_fetch_iv(),
        news=_fetch_news(),     # squawk geopolitical / supply-shock headlines
    )

def _cracks():
    from fetchers.cracks import get_crack_spreads
    return get_crack_spreads()

def _trade_idea():
    from models.trade_idea import generate_trade_idea
    return generate_trade_idea(
        _fetch_signal(),
        _fetch_fair_value(),
        _fetch_curve(),
        _fetch_technicals(),
        fundamentals = _fetch_fundamentals(),
        patterns     = _fetch_patterns(),
        macro        = _fetch_macro(),
        weather      = _fetch_weather(),
        prices       = _fetch_prices(),
        cracks       = _fetch_cracks(),
    )


def _candles_from_df(df) -> list[dict]:
    """
    Convert a yfinance history DataFrame to a list of OHLCV dicts.

    Each row becomes:
      {"t": unix_ms, "o": open, "h": high, "l": low, "c": close, "v": volume}

    Timestamps are normalised to milliseconds so they can be fed directly
    into any JS charting library (Lightweight Charts, Chart.js, etc.).
    """
    rows = []
    for ts, row in df.iterrows():
        try:
            t_ms = int(ts.timestamp() * 1000)
        except Exception:
            continue
        rows.append({
            "t": t_ms,
            "o": round(float(row["Open"]),   3),
            "h": round(float(row["High"]),   3),
            "l": round(float(row["Low"]),    3),
            "c": round(float(row["Close"]),  3),
            "v": int(row.get("Volume", 0)),
        })
    return rows


def _fetch_ticker_ohlcv(symbol: str, period: str, interval: str) -> list[dict]:
    """Download one ticker via yfinance and return a list of candle dicts."""
    import yfinance as yf
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval)
    if df.empty:
        return []
    return _candles_from_df(df)


def _ohlcv():
    """Intraday 5-minute OHLCV for Brent (BZ=F) and WTI (CL=F)."""
    return {
        "brent": _fetch_ticker_ohlcv("BZ=F", period="1d", interval="5m"),
        "wti":   _fetch_ticker_ohlcv("CL=F", period="1d", interval="5m"),
    }


def _history():
    """90-day daily OHLCV for Brent (BZ=F) and WTI (CL=F)."""
    return {
        "brent": _fetch_ticker_ohlcv("BZ=F", period="3mo", interval="1d"),
        "wti":   _fetch_ticker_ohlcv("CL=F", period="3mo", interval="1d"),
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint helpers — fetch-or-cache pattern shared by every route
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_prices():
    cached = get_cached("prices", TTL_PRICES)
    if cached is not None:
        return cached
    data = safe_fetch(_prices, {})
    set_cache("prices", data)
    return data


def _fetch_ohlcv():
    cached = get_cached("ohlcv", TTL_OHLCV)
    if cached is not None:
        return cached
    data = safe_fetch(_ohlcv, {"brent": [], "wti": []})
    set_cache("ohlcv", data)
    return data


def _fetch_history():
    cached = get_cached("history", TTL_HISTORY)
    if cached is not None:
        return cached
    data = safe_fetch(_history, {"brent": [], "wti": []})
    set_cache("history", data)
    return data

def _fetch_curve():
    cached = get_cached("curve", TTL_CURVE)
    if cached is not None:
        return cached
    data = safe_fetch(_curve, {})
    set_cache("curve", data)
    return data

def _fetch_fair_value():
    cached = get_cached("fair_value", TTL_FAIR_VALUE)
    if cached is not None:
        return cached
    brent = safe_fetch(_fair_value_brent, {})
    wti   = safe_fetch(_fair_value_wti,   {})
    data  = {"brent": brent, "wti": wti}
    set_cache("fair_value", data)
    return data

def _fetch_signal():
    cached = get_cached("signal", TTL_SIGNAL)
    # treat empty dict as a cache miss — means warm_cache raced a failing request
    if cached and isinstance(cached, dict) and "brent" in cached:
        return cached
    data = safe_fetch(_signal, {})
    if data and "brent" in data:           # only cache a real result
        set_cache("signal", data)
    return data

def _fetch_correlations():
    cached = get_cached("correlations", TTL_CORRELATIONS)
    if cached is not None:
        return cached
    data = {
        "matrix":    safe_fetch(_correlation_matrix, {}),
        "curve":     safe_fetch(_curve_correlation,  {}),
        "brent_wti": safe_fetch(_brent_wti_analysis, {}),
    }
    set_cache("correlations", data)
    return data

def _fetch_fundamentals():
    cached = get_cached("fundamentals", TTL_FUNDAMENTALS)
    if cached is not None:
        return cached
    # Grab cached HH price for spark/dark calculation (avoids a redundant yfinance call)
    prices  = _fetch_prices()
    hh_price = prices.get("henry_hub", {}).get("price") if prices else None
    data = {
        "inventory":   safe_fetch(_inventory,              {}),
        "snapshot":    safe_fetch(_snapshot,               {}),
        "cot":         safe_fetch(_cot,                    {}),
        "opec":        safe_fetch(_opec,                   {}),
        "geo_risk":    safe_fetch(_geo_risk,               {}),
        "rig_count":   safe_fetch(_rig_count,              {}),
        "seasonality": safe_fetch(_seasonality,            {}),
        "opec_eia":    safe_fetch(_opec_eia,               {}),
        "spark_dark":  safe_fetch(lambda: _spark_dark(hh_price), {}),
    }
    set_cache("fundamentals", data)
    return data

def _fetch_news():
    cached = get_cached("news", TTL_NEWS)
    if cached is not None:
        return cached
    data = safe_fetch(_news, {"articles": [], "negative_count": 0})
    set_cache("news", data)
    return data

def _fetch_weather():
    cached = get_cached("weather", TTL_WEATHER)
    if cached is not None:
        return cached
    data = safe_fetch(_weather, {"error": True, "net_demand_signal": 0.0,
                                  "summary": "Weather unavailable", "cities": []})
    set_cache("weather", data)
    return data

def _fetch_technicals():
    cached = get_cached("technicals", TTL_TECHNICALS)
    if cached is not None:
        return cached
    data = safe_fetch(_technicals, {})
    set_cache("technicals", data)
    return data

def _fetch_term_structure():
    cached = get_cached("term_structure", TTL_TERM_STRUCTURE)
    if cached is not None:
        return cached
    data = safe_fetch(_term_structure, {
        "correlation_matrix": {"labels": [], "matrix": [], "error": True},
        "strips": {},
    })
    set_cache("term_structure", data)
    return data

def _fetch_macro():
    cached = get_cached("macro", TTL_MACRO)
    if cached is not None:
        return cached
    data = safe_fetch(_macro, {"stale": True, "error": "fetch failed",
                                "source": "FRED"})
    set_cache("macro", data)
    return data

def _fetch_patterns():
    cached = get_cached("patterns", TTL_PATTERNS)
    if cached is not None:
        return cached
    data = safe_fetch(_patterns, {"stale": True, "error": "fetch failed"})
    set_cache("patterns", data)
    return data

def _fetch_iv():
    cached = get_cached("iv", TTL_IV)
    if cached is not None:
        return cached
    data = safe_fetch(_iv, {"stale": True, "error": "IV fetch failed",
                             "crude_iv": None, "crude_iv_pctile": 0.5,
                             "hh_iv": None, "hh_iv_pctile": 0.5, "signal": 0.0})
    set_cache("iv", data)
    return data

def _fetch_trade_idea():
    cached = get_cached("trade_idea", TTL_TRADE)
    if cached is not None:
        return cached
    data = safe_fetch(_trade_idea, {
        "direction": "NEUTRAL", "stale": True,
        "entry_thesis": ["Signal data loading — try again shortly."],
        "morning_brief": "Morning brief loading — Ollama or rule-based brief will appear here.",
    })
    set_cache("trade_idea", data)
    return data

def _fetch_alerts():
    cached = get_cached("alerts", TTL_ALERTS)
    if cached is not None:
        return cached
    data = safe_fetch(_alerts, {"alerts": [], "eia_change": None, "eia_4wk_avg": None})
    set_cache("alerts", data)
    return data

def _fetch_cracks():
    cached = get_cached("cracks", TTL_CRACKS)
    if cached is not None:
        return cached
    data = safe_fetch(_cracks, {"stale": True, "crack_spreads": {}, "vlcc_proxy": {}, "saudi_osp": {}})
    set_cache("cracks", data)
    return data

def _steo():
    from fetchers.eia import get_steo_balance
    return get_steo_balance()

def _fetch_steo():
    cached = get_cached("steo", TTL_STEO)
    if cached is not None:
        return cached
    data = safe_fetch(_steo, {"available": False, "stale": True, "months": [],
                               "current_supply": None, "current_demand": None,
                               "current_balance": None, "as_of": None})
    set_cache("steo", data)
    return data


def _analyst_watch():
    from fetchers.analyst_watch import get_analyst_watch
    return get_analyst_watch()

def _fetch_analyst_watch():
    cached = get_cached("analyst_watch", TTL_ANALYST_WATCH)
    if cached is not None:
        return cached
    data = safe_fetch(_analyst_watch, {"analysts": [], "timestamp": _now()})
    set_cache("analyst_watch", data)
    return data


def _tanker_watch():
    from fetchers.tanker_watch import get_tanker_watch
    return get_tanker_watch()

def _fetch_tanker_watch():
    cached = get_cached("tanker_watch", TTL_TANKER_WATCH)
    if cached is not None:
        return cached
    data = safe_fetch(_tanker_watch, {"available": False, "chokepoints": [],
                                      "note": "Loading…", "timestamp": _now()})
    set_cache("tanker_watch", data)
    return data


def _spreads_history():
    from fetchers.spreads_history import get_spreads_history
    return get_spreads_history(days=365)

def _fetch_spreads_history():
    cached = get_cached("spreads_history", TTL_SPREADS_HIST)
    if cached is not None:
        return cached
    data = safe_fetch(_spreads_history, {"rbob_ho": [], "crack_321": [],
                                          "gasoline_crack": [], "distillate_crack": [],
                                          "brent_wti": [], "stats": {},
                                          "timestamp": _now()})
    set_cache("spreads_history", data)
    return data


def _seasonality():
    from fetchers.seasonality import get_seasonality
    return get_seasonality()

def _fetch_seasonality():
    cached = get_cached("seasonality", TTL_SPREADS_HIST)
    if cached is not None:
        return cached
    data = safe_fetch(_seasonality, {"products": [], "current_month": 0,
                                      "current_month_name": "", "data_years": 5})
    set_cache("seasonality", data)
    return data


def _eia_surprise():
    from fetchers.eia_surprise import get_eia_surprise
    return get_eia_surprise(weeks=12)

def _fetch_eia_surprise():
    cached = get_cached("eia_surprise", TTL_EIA_SURPRISE)
    if cached is not None:
        return cached
    data = safe_fetch(_eia_surprise, {"releases": [], "regression": None,
                                       "next_release_utc": None,
                                       "next_release_in_seconds": None,
                                       "timestamp": _now()})
    set_cache("eia_surprise", data)
    return data


def _forward_cover():
    from fetchers.forward_cover import get_forward_cover_history
    return get_forward_cover_history(years=5)

def _fetch_forward_cover():
    cached = get_cached("forward_cover", TTL_EIA_SURPRISE)  # same hourly cadence
    if cached is not None:
        return cached
    data = safe_fetch(_forward_cover, {"history": [], "seasonal_band": [],
                                        "current": None, "current_date": None,
                                        "critical_low": 54, "comfortable_high": 65,
                                        "timestamp": _now()})
    set_cache("forward_cover", data)
    return data


# ─────────────────────────────────────────────────────────────────────────────
# APScheduler refresh jobs — one per cache key, called on interval
# ─────────────────────────────────────────────────────────────────────────────

def _refresh_prices():
    set_cache("prices",      safe_fetch(_prices, {}))

def _refresh_ohlcv():
    set_cache("ohlcv",       safe_fetch(_ohlcv, {"brent": [], "wti": []}))

def _refresh_history():
    set_cache("history",     safe_fetch(_history, {"brent": [], "wti": []}))

def _refresh_curve():
    set_cache("curve",       safe_fetch(_curve, {}))

def _refresh_fair_value():
    set_cache("fair_value", {
        "brent": safe_fetch(_fair_value_brent, {}),
        "wti":   safe_fetch(_fair_value_wti,   {}),
    })

def _refresh_signal():
    set_cache("signal",      safe_fetch(_signal, {}))

def _refresh_correlations():
    set_cache("correlations", {
        "matrix":    safe_fetch(_correlation_matrix, {}),
        "curve":     safe_fetch(_curve_correlation,  {}),
        "brent_wti": safe_fetch(_brent_wti_analysis, {}),
    })

def _refresh_fundamentals():
    from fetchers.eia        import (get_inventory_vs_seasonal, get_inventory_snapshot,
                                     get_rig_count, get_opec_eia_production,
                                     get_spark_dark_spread)
    from fetchers.cot        import get_positioning_percentile
    from fetchers.opec       import get_opec_summary
    from fetchers.geo_risk   import calculate_geo_risk
    from fetchers.seasonality import get_seasonality
    prices   = get_cached("prices", TTL_PRICES) or {}
    hh_price = prices.get("henry_hub", {}).get("price") if prices else None
    set_cache("fundamentals", {
        "inventory":   safe_fetch(get_inventory_vs_seasonal, {}),
        "snapshot":    safe_fetch(get_inventory_snapshot, {}),
        "cot":         safe_fetch(get_positioning_percentile, {}),
        "opec":        safe_fetch(get_opec_summary, {}),
        "geo_risk":    safe_fetch(calculate_geo_risk, {}),
        "rig_count":   safe_fetch(get_rig_count, {}),
        "seasonality": safe_fetch(get_seasonality, {}),
        "opec_eia":    safe_fetch(get_opec_eia_production, {}),
        "spark_dark":  safe_fetch(lambda: get_spark_dark_spread(hh_price), {}),
    })

def _refresh_news():
    set_cache("news",         safe_fetch(_news, {"articles": [], "negative_count": 0}))

def _refresh_weather():
    set_cache("weather",      safe_fetch(_weather, {}))

def _refresh_technicals():
    set_cache("technicals",   safe_fetch(_technicals, {}))

def _refresh_term_structure():
    set_cache("term_structure", safe_fetch(_term_structure, {}))

def _refresh_macro():
    set_cache("macro",        safe_fetch(_macro, {"stale": True, "error": "fetch failed",
                                                   "source": "FRED"}))

def _refresh_patterns():
    set_cache("patterns",     safe_fetch(_patterns, {"stale": True, "error": "fetch failed"}))

def _refresh_iv():
    set_cache("iv",           safe_fetch(_iv, {
        "stale": True, "crude_iv": None, "hh_iv": None,
        "crude_iv_pctile": 0.5, "hh_iv_pctile": 0.5, "signal": 0.0,
    }))

def _refresh_trade():
    set_cache("trade_idea",   safe_fetch(_trade_idea, {
        "direction": "NEUTRAL", "stale": True,
        "entry_thesis": ["Signal data loading — try again shortly."],
        "morning_brief": "Morning brief loading.",
    }))

def _refresh_alerts():
    set_cache("alerts", safe_fetch(_alerts, {"alerts": [], "eia_change": None, "eia_4wk_avg": None}))

def _refresh_cracks():
    set_cache("cracks", safe_fetch(_cracks, {"stale": True, "crack_spreads": {}, "vlcc_proxy": {}, "saudi_osp": {}}))

def _refresh_steo():
    set_cache("steo", safe_fetch(_steo, {"available": False, "stale": True, "months": [],
                                          "current_supply": None, "current_demand": None,
                                          "current_balance": None, "as_of": None}))

def _refresh_spreads_history():
    set_cache("spreads_history", safe_fetch(_spreads_history,
        {"rbob_ho": [], "crack_321": [], "gasoline_crack": [],
         "distillate_crack": [], "brent_wti": [], "stats": {}, "timestamp": _now()}))

def _refresh_seasonality():
    set_cache("seasonality", safe_fetch(_seasonality,
        {"products": [], "current_month": 0, "current_month_name": "", "data_years": 5}))

def _refresh_eia_surprise():
    set_cache("eia_surprise", safe_fetch(_eia_surprise,
        {"releases": [], "regression": None, "next_release_utc": None,
         "next_release_in_seconds": None, "timestamp": _now()}))

def _refresh_forward_cover():
    set_cache("forward_cover", safe_fetch(_forward_cover,
        {"history": [], "seasonal_band": [], "current": None,
         "current_date": None, "critical_low": 54, "comfortable_high": 65,
         "timestamp": _now()}))


# ─────────────────────────────────────────────────────────────────────────────
# Scheduler — fires at TTL intervals; slow jobs fire immediately on start
# ─────────────────────────────────────────────────────────────────────────────

_NOW = _dt.now()   # evaluated at import time — jobs with this next_run_time fire immediately on start()

_scheduler = BackgroundScheduler(daemon=True)
_scheduler.add_job(_refresh_prices,         "interval", seconds=TTL_PRICES)
_scheduler.add_job(_refresh_ohlcv,          "interval", seconds=TTL_OHLCV)
_scheduler.add_job(_refresh_history,        "interval", seconds=TTL_HISTORY)
_scheduler.add_job(_refresh_curve,          "interval", seconds=TTL_CURVE)
_scheduler.add_job(_refresh_fair_value,     "interval", seconds=TTL_FAIR_VALUE)
_scheduler.add_job(_refresh_signal,         "interval", seconds=TTL_SIGNAL)
_scheduler.add_job(_refresh_correlations,   "interval", seconds=TTL_CORRELATIONS)
_scheduler.add_job(_refresh_fundamentals,   "interval", seconds=TTL_FUNDAMENTALS)
_scheduler.add_job(_refresh_weather,        "interval", seconds=TTL_WEATHER)
_scheduler.add_job(_refresh_technicals,     "interval", seconds=TTL_TECHNICALS)
_scheduler.add_job(_refresh_term_structure, "interval", seconds=TTL_TERM_STRUCTURE)
# Slow jobs: fire immediately when scheduler starts (next_run_time in the past → fires at once)
_scheduler.add_job(_refresh_news,     "interval", seconds=TTL_NEWS,     next_run_time=_NOW)
_scheduler.add_job(_refresh_macro,    "interval", seconds=TTL_MACRO,    next_run_time=_NOW)
_scheduler.add_job(_refresh_patterns, "interval", seconds=TTL_PATTERNS, next_run_time=_NOW)
_scheduler.add_job(_refresh_iv,       "interval", seconds=TTL_IV,       next_run_time=_NOW)
_scheduler.add_job(_refresh_trade,    "interval", seconds=TTL_TRADE,    next_run_time=_NOW)
_scheduler.add_job(_refresh_alerts,   "interval", seconds=TTL_ALERTS,   next_run_time=_NOW)
_scheduler.add_job(_refresh_cracks,   "interval", seconds=TTL_CRACKS,   next_run_time=_NOW)
_scheduler.add_job(_refresh_steo,     "interval", seconds=TTL_STEO,     next_run_time=_NOW)
_scheduler.add_job(lambda: set_cache("analyst_watch", safe_fetch(_analyst_watch, {"analysts": [], "timestamp": _now()})),
                   "interval", seconds=TTL_ANALYST_WATCH, next_run_time=_NOW, id="_refresh_analyst_watch")
_scheduler.add_job(lambda: set_cache("tanker_watch", safe_fetch(_tanker_watch, {"available": False, "chokepoints": [], "note": "Loading…", "timestamp": _now()})),
                   "interval", seconds=TTL_TANKER_WATCH, next_run_time=_NOW, id="_refresh_tanker_watch")
_scheduler.add_job(_refresh_spreads_history, "interval", seconds=TTL_SPREADS_HIST, next_run_time=_NOW, id="_refresh_spreads_history")
_scheduler.add_job(_refresh_seasonality,     "interval", seconds=TTL_SPREADS_HIST, next_run_time=_NOW, id="_refresh_seasonality")
_scheduler.add_job(_refresh_eia_surprise,    "interval", seconds=TTL_EIA_SURPRISE, next_run_time=_NOW, id="_refresh_eia_surprise")
_scheduler.add_job(_refresh_forward_cover,   "interval", seconds=TTL_EIA_SURPRISE, next_run_time=_NOW, id="_refresh_forward_cover")


# ─────────────────────────────────────────────────────────────────────────────
# Flask routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "timestamp": _now()})



@app.route("/api/prices")
def prices():
    data = _fetch_prices()
    return jsonify({"data": data, "timestamp": _now(), "stale": False})


@app.route("/api/ohlcv")
def ohlcv():
    data = _fetch_ohlcv()
    return jsonify({"brent": data.get("brent", []),
                    "wti":   data.get("wti",   []),
                    "timestamp": _now()})


@app.route("/api/history")
def history():
    data = _fetch_history()
    return jsonify({"brent": data.get("brent", []),
                    "wti":   data.get("wti",   []),
                    "timestamp": _now()})


@app.route("/api/curve")
def curve():
    data = _fetch_curve()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/fair-value")
def fair_value():
    fv   = _fetch_fair_value()
    return jsonify({"brent": fv.get("brent", {}),
                    "wti":   fv.get("wti",   {}),
                    "timestamp": _now()})


@app.route("/api/signal")
def signal():
    data = _fetch_signal()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/correlations")
def correlations():
    data = _fetch_correlations()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/fundamentals")
def fundamentals():
    data = _fetch_fundamentals()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/news")
def news():
    data = _fetch_news()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/weather")
def weather():
    data = _fetch_weather()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/technicals")
def technicals():
    data = _fetch_technicals()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/term-structure")
def term_structure():
    data = _fetch_term_structure()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/macro")
def macro():
    data = _fetch_macro()
    return jsonify({"data": data, "timestamp": _now(),
                    "stale": data.get("stale", False)})


@app.route("/api/patterns")
def patterns():
    data = _fetch_patterns()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/iv")
def iv():
    data = _fetch_iv()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/trade-idea")
def trade_idea_route():
    data = _fetch_trade_idea()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/alerts")
def alerts_route():
    data = _fetch_alerts()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/cracks")
def cracks_route():
    data = _fetch_cracks()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/steo")
def steo_route():
    data = _fetch_steo()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/analyst-watch")
def analyst_watch_route():
    data = _fetch_analyst_watch()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/tanker-watch")
def tanker_watch_route():
    data = _fetch_tanker_watch()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/spreads-history")
def spreads_history_route():
    """Daily history of RBOB-HO, 3-2-1 crack, gasoline/distillate cracks, Brent-WTI."""
    data = _fetch_spreads_history()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/seasonality")
def seasonality_route():
    """5-product monthly seasonal returns (Brent/WTI/NG/RBOB/HO)."""
    data = _fetch_seasonality()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/eia-surprise")
def eia_surprise_route():
    """EIA Wednesday Weekly Petroleum Status Report — surprise tracker."""
    data = _fetch_eia_surprise()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/forward-cover")
def forward_cover_route():
    """5-year US days-of-forward-cover history + seasonal band."""
    data = _fetch_forward_cover()
    return jsonify({"data": data, "timestamp": _now()})


# ─────────────────────────────────────────────────────────────────────────────
# RAG chat — Q&A grounded in the OilMacroTrading curriculum + live snapshot
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/ask", methods=["POST"])
def ask_route():
    """
    Free-form Q&A. Body: {"question": str}.
    Combines BM25 retrieval over the curriculum with the live PULSE snapshot,
    then calls Ollama (if running) — falls back to extractive answer otherwise.
    """
    try:
        from rag.chat import answer as rag_answer
    except Exception as exc:
        return jsonify({"error": f"RAG module failed to load: {exc}"}), 500

    body = request.get_json(silent=True) or {}
    question = (body.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400

    # Build a compact live snapshot from the cache (no fresh fetches — fast)
    snapshot = {
        "prices":         _fetch_prices(),
        "curve":          _fetch_curve(),
        "signal":         _fetch_signal(),
        "fair_value":     _fetch_fair_value(),
        "fundamentals":   _fetch_fundamentals(),
        "cracks":         _fetch_cracks(),
        "forward_cover":  _fetch_forward_cover(),
    }

    try:
        result = rag_answer(question, snapshot=snapshot, k=5)
    except Exception as exc:
        log.exception("ask failed")
        return jsonify({"error": str(exc)}), 500

    return jsonify({"data": result, "timestamp": _now()})


@app.route("/api/ask/stats")
def ask_stats_route():
    """RAG index diagnostic — chunk count, vocab, book path."""
    try:
        from rag.retrieval import index_stats
        return jsonify({"data": index_stats(), "timestamp": _now()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/all")
def all_data():
    """Assemble all data from individual caches in one response."""
    fv = _fetch_fair_value()
    return jsonify({
        "prices":       {"data": _fetch_prices(),       "stale": False},
        "curve":        {"data": _fetch_curve()},
        "fair_value":   {"brent": fv.get("brent", {}),
                         "wti":   fv.get("wti",   {})},
        "signal":       {"data": _fetch_signal()},
        "correlations": {"data": _fetch_correlations()},
        "fundamentals": {"data": _fetch_fundamentals()},
        "news":         {"data": _fetch_news()},
        "weather":        {"data": _fetch_weather()},
        "technicals":     {"data": _fetch_technicals()},
        "term_structure": {"data": _fetch_term_structure()},
        "macro":          {"data": _fetch_macro()},
        "patterns":       {"data": _fetch_patterns()},
        "iv":             {"data": _fetch_iv()},
        "cracks":         {"data": _fetch_cracks()},
        "steo":           {"data": _fetch_steo()},
        "analyst_watch":  {"data": _fetch_analyst_watch()},
        "tanker_watch":   {"data": _fetch_tanker_watch()},
        "spreads_history":{"data": _fetch_spreads_history()},
        "seasonality":    {"data": _fetch_seasonality()},
        "eia_surprise":   {"data": _fetch_eia_surprise()},
        "forward_cover":  {"data": _fetch_forward_cover()},
        "timestamp":      _now(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Background cache warm-up
# ─────────────────────────────────────────────────────────────────────────────

def warm_cache():
    from fetchers.prices     import get_live_prices
    from fetchers.curve      import get_both_curves
    from fetchers.eia        import (get_inventory_vs_seasonal,
                                          get_inventory_snapshot,
                                          get_rig_count)
    from fetchers.seasonality import get_seasonality
    from fetchers.cot        import get_positioning_percentile
    from fetchers.opec       import get_opec_summary
    from fetchers.geo_risk   import calculate_geo_risk
    from fetchers.weather    import get_weather_signal
    from fetchers.technicals import get_all_technicals
    from models.term_structure    import get_term_structure
    from models.fair_value        import calculate_fair_value
    from models.signal_engine     import get_all_signals
    from models.correlations      import (get_correlation_matrix,
                                          get_curve_correlation,
                                          get_brent_wti_analysis)

    time.sleep(2)
    log.info("=== PULSE warm-up starting ===")

    # Step 1 — Fast data immediately
    # OHLCV and history also go here — they are pure yfinance calls,
    # independent of all other fetchers, and are needed by the chart panels.
    for key, func in [
        ("prices",  get_live_prices),
        ("curve",   get_both_curves),
        ("ohlcv",   _ohlcv),
        ("history", _history),
    ]:
        try:
            set_cache(key, func())
            log.info(f"✓ {key}")
        except Exception as e:
            log.error(f"✗ {key}: {e}")

    log.info("→ news, macro, patterns, iv, trade_idea warming via APScheduler...")

    # Step 2b — Weather (Open-Meteo, free, no key, ~1s)
    try:
        set_cache("weather", get_weather_signal())
        log.info("✓ weather")
    except Exception as e:
        log.error(f"✗ weather: {e}")

    # Step 2c — Technicals (derived from historical prices)
    try:
        set_cache("technicals", get_all_technicals())
        log.info("✓ technicals")
    except Exception as e:
        log.error(f"✗ technicals: {e}")

    # Step 2d — Term structure (forward curves + correlation matrix)
    try:
        set_cache("term_structure", get_term_structure())
        log.info("✓ term_structure")
    except Exception as e:
        log.error(f"✗ term_structure: {e}")

    # Step 3 — Fundamentals (one Apify call for geo_risk)
    try:
        from fetchers.eia import get_opec_eia_production, get_spark_dark_spread
        _wc_prices  = get_cached("prices", TTL_PRICES) or {}
        _wc_hh      = _wc_prices.get("henry_hub", {}).get("price") if _wc_prices else None
        set_cache("fundamentals", {
            "inventory":   get_inventory_vs_seasonal(),
            "snapshot":    get_inventory_snapshot(),
            "cot":         get_positioning_percentile(),
            "opec":        get_opec_summary(),
            "rig_count":   get_rig_count(),
            "geo_risk":    calculate_geo_risk(),
            "seasonality": get_seasonality(),
            "opec_eia":    get_opec_eia_production(),
            "spark_dark":  get_spark_dark_spread(_wc_hh),
            "timestamp":   datetime.now().isoformat(),
        })
        log.info("✓ fundamentals")
    except Exception as e:
        log.error(f"✗ fundamentals: {e}")

    # Step 4 — Fair value (geo_risk hits module cache)
    try:
        set_cache("fair_value", {
            "brent":     calculate_fair_value("brent"),
            "wti":       calculate_fair_value("wti"),
            "timestamp": datetime.now().isoformat(),
        })
        log.info("\u2713 fair_value")
    except Exception as e:
        log.error(f"\u2717 fair_value: {e}")

    # Step 5 — Signal (geo_risk hits module cache)
    try:
        set_cache("signal", get_all_signals())
        log.info("\u2713 signal")
    except Exception as e:
        log.error(f"\u2717 signal: {e}")

    # Step 6 — Correlations
    try:
        set_cache("correlations", {
            "matrix":    get_correlation_matrix(),
            "curve":     get_curve_correlation(),
            "brent_wti": get_brent_wti_analysis(),
            "timestamp": datetime.now().isoformat(),
        })
        log.info("\u2713 correlations")
    except Exception as e:
        log.error(f"\u2717 correlations: {e}")

    log.info("=== Core warm-up complete \u2014 dashboard ready ===")
    log.info("=== Slow fetchers (news/macro/patterns/iv/trade) running via APScheduler ===")


# \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
# Entry point
# \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

if __name__ == "__main__":
    warm_cache_thread = threading.Thread(target=warm_cache, name="cache-warmup")
    warm_cache_thread.daemon = True
    warm_cache_thread.start()

    # Warm Ollama (if running locally) in the background so the first
    # /api/ask doesn't pay the model-load cost. Fails silently when Ollama
    # is offline — chat will just use the extractive fallback in that case.
    def _warm_ollama_bg():
        try:
            from rag.chat import warm_ollama
            warm_ollama()
        except Exception as exc:
            log.info("Ollama warm-up skipped: %s", exc)
    threading.Thread(target=_warm_ollama_bg, name="ollama-warmup", daemon=True).start()

    _scheduler.start()
    log.info("APScheduler started — background refresh active")

    # Bind host/port from env so we can run locally (127.0.0.1:5000) or
    # inside a container (0.0.0.0:$PORT — Hugging Face / Render / Fly all
    # inject $PORT at runtime, HF Spaces specifically expects 7860).
    _host = os.environ.get("HOST", "127.0.0.1")
    _port = int(os.environ.get("PORT", "5000"))
    log.info(f"PULSE API starting on http://{_host}:{_port}  (warm-up ~60s)")
    app.run(host=_host, port=_port, debug=False, use_reloader=False)
