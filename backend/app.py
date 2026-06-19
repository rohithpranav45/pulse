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
from datetime import datetime, timezone, timedelta

# ── ensure backend/ and project root are on sys.path ─────────────────────────
_BACKEND = os.path.abspath(os.path.dirname(__file__))          # pulse/backend/
_ROOT    = os.path.abspath(os.path.join(_BACKEND, ".."))       # pulse/
for _p in (_BACKEND, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from flask import Flask, jsonify, request
from flask_cors import CORS
from schemas import (
    PricesResponse, SignalResponse, TradeIdeaResponse, FundamentalsResponse,
    NewsResponse, PaperPositionsResponse, PaperPerformanceResponse,
    HealthDetailResponse, respond,
)
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

# ── Observability (Sprint 0b) ────────────────────────────────────────────────
# Sentry must initialise BEFORE the Flask app is constructed so its Flask
# integration can hook into request/response handling. Better Stack attaches
# to the root logger so every log line streams up automatically.
from observability import init_sentry, init_better_stack_logging  # noqa: E402
init_sentry()
init_better_stack_logging()

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
TTL_OVX            = 3600  # CBOE OVX from FRED — daily-cadence series
TTL_CURVE_REGIME   = 3600  # 15-yr spread percentile — file-backed, recompute hourly
TTL_ORDER_FLOW     = 3600  # buy/sell volume from desk feed
TTL_JODI           = 86400 # JODI monthly — only changes monthly
TTL_GDELT_TONE     = 1800  # GDELT GKG tone — 30-min cadence
TTL_MARKETAUX      = 900   # MarketAux news — 15-min refresh
TTL_ANALOGS        = 21600 # matrix-profile analogs — 6h (expensive compute)


# ─────────────────────────────────────────────────────────────────────────────
# Error-safe wrapper
# ─────────────────────────────────────────────────────────────────────────────

def safe_fetch(func, fallback=None):
    """
    Call func() and return its result.
    On any exception, log the error, ship it to Sentry, and return fallback.
    Handles lambdas (which have no meaningful __name__).
    """
    name = getattr(func, "__name__", None) or repr(func)
    try:
        return func()
    except Exception as exc:
        log.error("%s failed: %s", name, exc)
        try:
            from observability import capture_exception
            capture_exception(exc, fetcher=name)
        except Exception:
            pass
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

def _jodi():
    from fetchers.jodi import get_jodi_opec_production
    return get_jodi_opec_production()

def _rig_count_v2():
    from fetchers.rig_count import get_rig_count
    return get_rig_count()

def _ovx():
    from fetchers.ovx import get_ovx
    return get_ovx()

def _curve_regime():
    from fetchers.curve_regime import get_curve_regime
    return get_curve_regime()

def _order_flow():
    from fetchers.order_flow import get_order_flow_imbalance
    return get_order_flow_imbalance()

def _stooq():
    from fetchers.stooq import get_stooq_quotes
    return get_stooq_quotes()

def _ecb_fx():
    from fetchers.ecb_fx import get_ecb_fx
    return get_ecb_fx()

def _gdelt_news():
    from fetchers.gdelt import get_gdelt_news
    return get_gdelt_news(max_articles=40, hours=12)

def _gdelt_tone():
    from fetchers.gdelt import get_gdelt_tone
    # ECON_OILPRICE alone returns a clean signal; MILITARY makes the OR query so
    # broad that GDELT throttles us. Keep it tight.
    return get_gdelt_tone(themes=("ECON_OILPRICE",), hours=24)

def _gdelt_bylines():
    from fetchers.gdelt import get_byline_articles
    return get_byline_articles(handles=("Javier Blas", "Amena Bakr", "Helima Croft"), hours=72)

# Phase B fetchers
def _marketaux():
    from fetchers.marketaux import get_marketaux_news
    return get_marketaux_news(limit=40, hours=36)

def _analogs():
    from fetchers.analogs import get_pattern_analogs
    return get_pattern_analogs()

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
    """News pipeline — GDELT primary (free, reliable), legacy aggregator fallback."""
    try:
        gdelt = _gdelt_news()
        if gdelt and gdelt.get("articles"):
            # Reuse the existing FinBERT scoring + clustering on GDELT results
            try:
                from fetchers.sentiment import score_articles_finbert
                from fetchers.news     import _cluster_articles
                scored   = score_articles_finbert(gdelt["articles"])
                clusters = _cluster_articles(scored)
                gdelt["articles"] = scored
                gdelt["clusters"] = clusters
                # Composite sentiment
                if scored:
                    avg = sum(a.get("sentiment_score", 0) for a in scored) / len(scored)
                    bull = sum(1 for a in scored if a.get("sentiment_score", 0) >  0.1)
                    bear = sum(1 for a in scored if a.get("sentiment_score", 0) < -0.1)
                    gdelt["composite_sentiment"] = {
                        "composite": round(avg, 4),
                        "bullish":   bull,
                        "bearish":   bear,
                        "neutral":   len(scored) - bull - bear,
                        "count":     len(scored),
                        "label":     "BULLISH" if avg > 0.1 else "BEARISH" if avg < -0.1 else "NEUTRAL",
                        "stale":     False,
                    }
            except Exception as exc:
                log.warning("FinBERT/cluster on GDELT failed: %s", exc)
            return gdelt
    except Exception as exc:
        log.warning("GDELT primary news failed: %s — trying MarketAux", exc)
    # Fallback 1 — MarketAux (free key)
    try:
        ma = _marketaux()
        if ma and ma.get("articles"):
            try:
                from fetchers.news import _cluster_articles
                ma["clusters"] = _cluster_articles(ma["articles"])
            except Exception:
                pass
            # MarketAux's entity sentiment is missing on most general-news
            # articles (entities = []), so per-article sentiment_score arrives
            # as None. Fall back to FinBERT scoring on the headline so the
            # composite chip renders.
            try:
                from fetchers.sentiment import score_articles_finbert
                arts = ma["articles"]
                unscored = [a for a in arts if not isinstance(a.get("sentiment_score"), (int, float))]
                if unscored:
                    score_articles_finbert(unscored)  # mutates in place
            except Exception as exc:
                log.warning("FinBERT scoring on MarketAux failed: %s", exc)

            # Compute composite sentiment from per-article scores so the chip renders
            try:
                arts = ma["articles"]
                scored = [a for a in arts if isinstance(a.get("sentiment_score"), (int, float))]
                if scored:
                    avg = sum(a["sentiment_score"] for a in scored) / len(scored)
                    bull = sum(1 for a in scored if a["sentiment_score"] >  0.1)
                    bear = sum(1 for a in scored if a["sentiment_score"] < -0.1)
                    ma["composite_sentiment"] = {
                        "composite": round(avg, 4),
                        "bullish":   bull,
                        "bearish":   bear,
                        "neutral":   len(scored) - bull - bear,
                        "count":     len(scored),
                        "label":     "BULLISH" if avg > 0.1 else "BEARISH" if avg < -0.1 else "NEUTRAL",
                        "stale":     False,
                    }
            except Exception as exc:
                log.warning("MarketAux composite sentiment failed: %s", exc)
            return ma
    except Exception as exc:
        log.warning("MarketAux fallback failed: %s", exc)
    # Fallback 2 — legacy aggregator (Apify → NewsAPI → direct RSS)
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
    data = get_macro_data() or {}
    # Layer on ECB FX as a no-key second source for EUR/USD
    try:
        ecb = _ecb_fx()
        if ecb and ecb.get("eur_usd"):
            data["ecb_eurusd"] = {
                "value":  round(float(ecb["eur_usd"]), 4),
                "date":   ecb.get("as_of"),
                "label":  "EUR/USD (ECB)",
                "unit":   "rate",
                "source": "ECB reference rate",
            }
    except Exception as exc:
        log.warning("ECB FX overlay failed: %s", exc)
    return data

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

def _build_fundamentals(hh_price=None) -> dict:
    """Single source of truth for the fundamentals payload. Used by every
    code path that needs to populate the cache (fetch / refresh / warm)."""
    return {
        "inventory":    safe_fetch(_inventory,              {}),
        "snapshot":     safe_fetch(_snapshot,               {}),
        "cot":          safe_fetch(_cot,                    {}),
        "opec":         safe_fetch(_opec,                   {}),
        "opec_jodi":    safe_fetch(_jodi,                   {}),
        "geo_risk":     safe_fetch(_geo_risk,               {}),
        # Prefer the new multi-source rig_count fetcher; legacy EIA path stays as backup
        "rig_count":    safe_fetch(_rig_count_v2, safe_fetch(_rig_count, {})),
        "seasonality":  safe_fetch(_seasonality,            {}),
        "opec_eia":     safe_fetch(_opec_eia,               {}),
        "spark_dark":   safe_fetch(lambda: _spark_dark(hh_price), {}),
        "curve_regime": safe_fetch(_curve_regime,           {}),
        "order_flow":   safe_fetch(_order_flow,             {}),
    }


def _is_fundamentals_complete(data: dict) -> bool:
    """Cached fundamentals dict missing any of the Phase-A/B fields → recompute."""
    if not isinstance(data, dict):
        return False
    required = {"opec_jodi", "curve_regime", "order_flow"}
    return required.issubset(data.keys())


def _fetch_fundamentals():
    cached = get_cached("fundamentals", TTL_FUNDAMENTALS)
    if cached is not None and _is_fundamentals_complete(cached):
        return cached
    # Stale or missing-fields → rebuild fresh
    prices   = _fetch_prices()
    hh_price = prices.get("henry_hub", {}).get("price") if prices else None
    data = _build_fundamentals(hh_price)
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
    """
    GDELT byline tracking — replaces Nitter (X-com mirrors are dead in 2026).
    Falls back to the legacy Nitter scraper if GDELT returns nothing.
    """
    try:
        out = _gdelt_bylines()
        # Treat as valid if at least one author has any results
        if out and any(a.get("ok") for a in out.get("analysts", [])):
            return out
    except Exception as exc:
        log.warning("GDELT bylines failed: %s — falling back", exc)
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


def _fetch_ovx():
    cached = get_cached("ovx", TTL_OVX)
    if cached is not None: return cached
    data = safe_fetch(_ovx, {"stale": True, "current": None,
                              "source": "FRED OVXCLS"})
    set_cache("ovx", data)
    return data

def _fetch_curve_regime():
    cached = get_cached("curve_regime", TTL_CURVE_REGIME)
    if cached is not None: return cached
    data = safe_fetch(_curve_regime, {"available": False})
    set_cache("curve_regime", data)
    return data

def _fetch_order_flow():
    cached = get_cached("order_flow", TTL_ORDER_FLOW)
    if cached is not None: return cached
    data = safe_fetch(_order_flow, {"available": False, "contracts": []})
    set_cache("order_flow", data)
    return data

def _fetch_jodi():
    cached = get_cached("jodi", TTL_JODI)
    if cached is not None: return cached
    data = safe_fetch(_jodi, {"available": False, "members": []})
    set_cache("jodi", data)
    return data

def _fetch_gdelt_tone():
    cached = get_cached("gdelt_tone", TTL_GDELT_TONE)
    # Treat a cached stale entry as a miss so the next request retries
    if cached is not None and not cached.get("stale"):
        return cached
    data = safe_fetch(_gdelt_tone, {"mean_tone": None, "stale": True})
    if data and not data.get("stale"):   # only cache real results
        set_cache("gdelt_tone", data)
    return data

def _fetch_marketaux():
    cached = get_cached("marketaux", TTL_MARKETAUX)
    if cached is not None: return cached
    data = safe_fetch(_marketaux, {"articles": [], "stale": True})
    set_cache("marketaux", data)
    return data

def _fetch_analogs():
    cached = get_cached("analogs", TTL_ANALOGS)
    if cached is not None: return cached
    data = safe_fetch(_analogs, {"available": False, "analogs": []})
    set_cache("analogs", data)
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
    prices   = get_cached("prices", TTL_PRICES) or {}
    hh_price = prices.get("henry_hub", {}).get("price") if prices else None
    set_cache("fundamentals", _build_fundamentals(hh_price))

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

# New Phase A streams
_scheduler.add_job(lambda: set_cache("ovx",          safe_fetch(_ovx,          {"stale": True})),
                   "interval", seconds=TTL_OVX, next_run_time=_NOW, id="_refresh_ovx")
_scheduler.add_job(lambda: set_cache("curve_regime", safe_fetch(_curve_regime, {"available": False})),
                   "interval", seconds=TTL_CURVE_REGIME, next_run_time=_NOW, id="_refresh_curve_regime")
_scheduler.add_job(lambda: set_cache("order_flow",   safe_fetch(_order_flow,   {"available": False, "contracts": []})),
                   "interval", seconds=TTL_ORDER_FLOW, next_run_time=_NOW, id="_refresh_order_flow")
_scheduler.add_job(lambda: set_cache("jodi",         safe_fetch(_jodi,         {"available": False, "members": []})),
                   "interval", seconds=TTL_JODI, next_run_time=_NOW, id="_refresh_jodi")
_scheduler.add_job(lambda: set_cache("gdelt_tone",   safe_fetch(_gdelt_tone,   {"mean_tone": None, "stale": True})),
                   "interval", seconds=TTL_GDELT_TONE, next_run_time=_NOW, id="_refresh_gdelt_tone")

# Phase B streams
_scheduler.add_job(lambda: set_cache("marketaux",    safe_fetch(_marketaux,    {"articles": [], "stale": True})),
                   "interval", seconds=TTL_MARKETAUX, next_run_time=_NOW, id="_refresh_marketaux")
_scheduler.add_job(lambda: set_cache("analogs",      safe_fetch(_analogs,      {"available": False, "analogs": []})),
                   "interval", seconds=TTL_ANALOGS, next_run_time=_NOW, id="_refresh_analogs")

# Paper-trading mark-to-market — every minute, auto-close on TP/SL hits.
def _paper_mtm():
    try:
        from paper_trading import mark_to_market
        s = mark_to_market()
        if s.get("auto_closed"):
            log.info("paper MTM: auto-closed %d, %d still open", s["auto_closed"], s["still_open"])
    except Exception as exc:
        log.warning("paper MTM failed: %s", exc)

_scheduler.add_job(_paper_mtm, "interval", seconds=60, id="_paper_mtm")

# Phase 2.8.6-followup A/B harness — dual-push pooled + gated arms once per day.
# Idempotent: ab_test.tick() dedups on open (asset, direction, ab_mode), so
# multiple firings within a session are safe.
def _ab_tick():
    if os.environ.get("PULSE_AB_TEST_DISABLED") == "1":
        return
    try:
        from research.ab_test import tick
        s = tick()
        log.info(
            "A/B tick: pushed pooled=%d gated=%d",
            len(s.get("pushed", {}).get("pooled", []) or []),
            len(s.get("pushed", {}).get("gated", []) or []),
        )
    except Exception as exc:
        log.warning("A/B tick failed: %s", exc)

# Once per 24 hours, kicked off five minutes after boot so the data lake +
# regime models have warmed up before we generate signals.
_scheduler.add_job(
    _ab_tick,
    "interval",
    seconds=86_400,
    next_run_time=_dt.now() + timedelta(minutes=5),
    id="_ab_tick",
)

# Phase 3.1 — live analysis engine. Generate signals off the live intraday feed
# and track each signal's subsequent performance. Disabled with
# PULSE_LIVE_SIGNALS_DISABLED=1 (e.g. on the Oracle box, which can't see the
# office I: share). Cadence "Both": one daily signal + intraday re-evaluations,
# with a performance sweep that MTMs open signals against the latest bars.
def _live_signals_disabled() -> bool:
    return os.environ.get("PULSE_LIVE_SIGNALS_DISABLED") == "1"

def _live_signal_daily():
    if _live_signals_disabled():
        return
    try:
        from research.signal_log import generate_live_signals
        s = generate_live_signals(cadence="daily")
        if s.get("available"):
            log.info("live signals (daily): logged=%s regime=%s as_of=%s",
                     s.get("logged"), s.get("regime"), s.get("feed_as_of"))
    except Exception as exc:
        log.warning("live signal daily gen failed: %s", exc)

def _live_signal_intraday():
    if _live_signals_disabled():
        return
    try:
        from research.signal_log import generate_live_signals, update_signal_performance
        g = generate_live_signals(cadence="intraday")
        u = update_signal_performance()
        if g.get("available"):
            log.info("live signals (intraday): logged=%s | perf checked=%s closed=%s",
                     g.get("logged"), u.get("checked"), u.get("closed"))
    except Exception as exc:
        log.warning("live signal intraday tick failed: %s", exc)

# Daily generation once per 24h (kicked off 6 min after boot, after warm-up).
_scheduler.add_job(
    _live_signal_daily, "interval", seconds=86_400,
    next_run_time=_dt.now() + timedelta(minutes=6), id="_live_signal_daily",
)
# Intraday re-evaluation + performance sweep every 15 min (matches bar size).
_scheduler.add_job(
    _live_signal_intraday, "interval", seconds=900,
    next_run_time=_dt.now() + timedelta(minutes=7), id="_live_signal_intraday",
)


# ─────────────────────────────────────────────────────────────────────────────
# Flask routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "timestamp": _now()})


@app.route("/api/_observability/smoke")
def _observability_smoke():
    """
    Sprint 0b smoke test. Disabled in prod; enable with PULSE_OBS_SMOKE=1.

    Logs an INFO + WARNING line (shipped to Better Stack) and raises an
    exception caught by Sentry's Flask middleware. Returns a quick summary
    so a curl can confirm the path was exercised.
    """
    if os.environ.get("PULSE_OBS_SMOKE") != "1":
        return jsonify({"error": "disabled", "hint": "set PULSE_OBS_SMOKE=1"}), 403
    from observability import capture_exception, state as obs_state
    log.info("pulse smoke test (info): better-stack should receive this line")
    log.warning("pulse smoke test (warning): sentry breadcrumb")
    try:
        raise RuntimeError("pulse smoke test — intentional, ignore")
    except RuntimeError as exc:
        capture_exception(exc, source="smoke_test")
    return jsonify({
        "ok":     True,
        "state":  obs_state(),
        "advice": "check https://sentry.io and Better Stack dashboards for the test event",
    })


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 (class-demo) — regime-based opportunity engine
# ─────────────────────────────────────────────────────────────────────────────

def _regime_current():
    from research.live_ranker import get_current_regime
    return get_current_regime()

def _regime_recommendation():
    from research.live_ranker import get_recommendation
    return get_recommendation()

def _regime_backtest():
    from research.live_ranker import get_backtest_report
    return get_backtest_report()

@app.route("/api/regime")
def regime_route():
    """Current curve regime + drivers."""
    return jsonify({"data": safe_fetch(_regime_current, {"available": False}),
                    "timestamp": _now()})

@app.route("/api/regime/recommendation")
def regime_recommendation_route():
    """Top-ranked regime-conditional opportunity + full receipts."""
    return jsonify({"data": safe_fetch(_regime_recommendation, {"available": False}),
                    "timestamp": _now()})

@app.route("/api/regime/backtest")
def regime_backtest_route():
    """Saved training report — OOS R², band-hit rate per (spread, regime)."""
    return jsonify({"data": safe_fetch(_regime_backtest, {"available": False}),
                    "timestamp": _now()})

@app.route("/api/regime/drill/<spread>")
def regime_drill_route(spread: str):
    """
    Drill-down receipts for one spread under today's regime:
      • scatter of actual vs fair value across the regime's full history
      • 3 closest historical analogs to today's feature vector + 20d forward
    """
    def _drill():
        from research.drill import get_drill_data
        return get_drill_data(spread)
    return jsonify({"data": safe_fetch(_drill, {"available": False}),
                    "timestamp": _now()})

@app.route("/api/regime/walkforward")
def regime_walkforward_route():
    """
    Walk-forward backtest results (Sprint 4). Expanding-window refits across
    2024-2026 with regime-aware + regime-unaware baseline. Read-only — run
    `python -m backend.research.walkforward` to regenerate.
    """
    def _wf():
        from research.walkforward import load_report
        rpt = load_report()
        if not rpt:
            return {"available": False, "error": "no walk-forward report — run python -m backend.research.walkforward first"}
        rpt["available"] = True
        return rpt
    return jsonify({"data": safe_fetch(_wf, {"available": False}),
                    "timestamp": _now()})


@app.route("/api/regime/calibration")
def regime_calibration_route():
    """
    Phase 4.H — calibration plot. Bin gated_trades.json by |z|; report the
    mean-reversion fraction (fwd_pnl > 0) per bin so the user can read
    "when the engine flagged z = X, the spread reverted Y% of the time
    within the 20-day window (n trades)."

    Read-only; gated_trades.json is the same tape the walk-forward emits, so
    no model is hit. Source is filtered to gate=pass rows by default (what
    the live engine would have fired); pass ?include=all to include the
    full backtest tape.
    """
    import json as _json
    import os as _os

    def _calib():
        include = (request.args.get("include") or "pass").lower()
        path = _os.path.join(
            _os.path.dirname(__file__), "data", "research", "gated_trades.json"
        )
        if not _os.path.exists(path):
            return {"available": False, "error": "gated_trades.json not found — run the walk-forward first"}
        with open(path, "r", encoding="utf-8") as f:
            trades = _json.load(f)

        rows = [
            t for t in trades
            if t.get("z") is not None and t.get("fwd_pnl") is not None
            and (include == "all" or t.get("gate") == "pass")
        ]
        if not rows:
            return {"available": False, "error": f"no trades match include={include}"}

        # Bin on |z|. Buckets land on the conviction thresholds the engine
        # actually trades around (1.5σ gate, 2σ band, 2.5σ stop, 3σ extreme).
        edges = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
        bins = []
        for lo, hi in zip([0.0] + edges, edges + [float("inf")]):
            in_bin = [t for t in rows if lo <= abs(t["z"]) < hi]
            n = len(in_bin)
            if n == 0:
                continue
            reverted = sum(1 for t in in_bin if t["fwd_pnl"] > 0)
            mean_pnl = sum(t["fwd_pnl"] for t in in_bin) / n
            bins.append({
                "z_lo":           lo,
                "z_hi":           None if hi == float("inf") else hi,
                "n":              n,
                "reverted_frac":  reverted / n,
                "mean_fwd_pnl":   round(mean_pnl, 4),
            })

        n_total    = len(rows)
        n_reverted = sum(1 for t in rows if t["fwd_pnl"] > 0)
        return {
            "available":           True,
            "include":             include,
            "horizon_days":        20,
            "n_total":             n_total,
            "overall_reverted":    n_reverted / n_total if n_total else None,
            "bins":                bins,
            "source":              "backend/data/research/gated_trades.json",
        }

    return jsonify({"data": safe_fetch(_calib, {"available": False}),
                    "timestamp": _now()})


@app.route("/api/regime/ab")
def regime_ab_route():
    """
    Phase 2.8.6-followup A/B paper-test report.

    Compares two parallel paper books — Arm A (pooled, un-gated) vs Arm B
    (gated_blend, current default) — pushed daily via research.ab_test.tick.
    Returns per-arm headline metrics, Welch + paired t-tests on per-trade
    NET PnL (Phase 2.8.6 cost-aware), stop-criteria progress and a verdict.
    """
    from schemas import ABReportResponse
    def _ab():
        from research.ab_test import get_report
        return get_report()
    return respond(ABReportResponse, safe_fetch(_ab, {"available": False, "verdict": "no_data"}), _now())


@app.route("/api/regime/ab/tick", methods=["POST"])
def regime_ab_tick_route():
    """
    Manually fire one A/B generation step (dual-push of pooled + gated arms).
    Idempotent: dedup on open (asset, direction, ab_mode). Used for smoke
    tests + when the operator wants to backfill a missed daily tick. The
    APScheduler job fires this automatically once per day.
    """
    body = request.get_json(silent=True) or {}
    session = body.get("session")
    from research.ab_test import tick
    out = tick(ab_session=session)
    return jsonify({"data": out, "timestamp": _now()})


@app.route("/api/regime/ab/reset", methods=["POST"])
def regime_ab_reset_route():
    """
    Wipe A/B-tagged paper trades. scope='all'|'closed'. Does NOT touch
    non-A/B paper rows (the dashboard's regular paper book is preserved).
    """
    body = request.get_json(silent=True) or {}
    from research.ab_test import reset as ab_reset
    n = ab_reset(scope=body.get("scope", "all"))
    return jsonify({"data": {"removed": n}, "timestamp": _now()})


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3.1 — live analysis engine + signal log
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/api/regime/live")
def regime_live_route():
    """
    Run the regime framework against the CURRENT market from the live intraday
    feed (lightstreamer bars). Returns the same shape as
    /api/regime/recommendation plus a `live_feed` block. Read-only — does not
    persist. Set PULSE_LIVE_FEED_DIR to point at the feed directory.
    """
    def _live():
        from research.live_engine import get_live_recommendation
        return get_live_recommendation(include_wti=request.args.get("wti") == "1")
    return jsonify({"data": safe_fetch(_live, {"available": False}), "timestamp": _now()})


@app.route("/api/regime/intraday_replay")
def regime_intraday_replay_route():
    """
    In-window sanity replay of the live engine over the recorder's 15-min bar
    history (the only intraday feed we have). Walks the REAL spread path with the
    engine's overlay-corrected fair value + the tuned exit rule (TP halfway-to-
    fair · SL 2.5σ · close-based). Read-only — does not persist.

    NOT a statistically valid backtest — see the `caveats` field; the response is
    explicitly labelled a diagnostic, not a performance claim.
    """
    def _replay():
        from research.intraday_replay import run_replay
        return run_replay(include_wti=request.args.get("wti", "1") != "0")
    return jsonify({"data": safe_fetch(_replay, {"available": False}), "timestamp": _now()})


@app.route("/api/regime/shock")
def regime_shock_route():
    """
    Shock-absorption monitor: today's GMM stress read (P(stress), onset,
    circuit-breaker state) + the validated absorption metrics + a P(stress)
    history that shows the detector caught the real oil shocks out-of-sample.
    """
    def _shock():
        from research.shock_engine import dashboard_payload
        return dashboard_payload()
    return jsonify({"data": safe_fetch(_shock, {"available": False}), "timestamp": _now()})


@app.route("/api/regime/signals")
def regime_signals_route():
    """
    The live signal log — every opportunity the model generated, with timestamp,
    regime, instrument, rationale, confidence, and subsequent performance.
    Query: ?status=open|closed|all (default all), ?limit=N (default 200).
    """
    def _signals():
        from research.signal_log import list_signals
        status = (request.args.get("status") or "all").upper()
        if status not in ("OPEN", "CLOSED"):
            status = "all"
        try:
            limit = int(request.args.get("limit", 200))
        except (TypeError, ValueError):
            limit = 200
        rows = list_signals(status=status, limit=limit)
        n_open = sum(1 for r in rows if r.get("status") == "OPEN")
        return {"available": True, "signals": rows, "n": len(rows), "n_open": n_open}
    return jsonify({"data": safe_fetch(_signals, {"available": False, "signals": []}),
                    "timestamp": _now()})


@app.route("/api/regime/signals/generate", methods=["POST"])
def regime_signals_generate_route():
    """
    Manually fire one live signal-generation step (idempotent — dedups on
    instrument/direction/feed_as_of/cadence). The scheduler fires daily +
    intraday automatically; this is for smoke tests / backfilling a tick.
    """
    body = request.get_json(silent=True) or {}
    from research.signal_log import generate_live_signals
    out = generate_live_signals(
        cadence=body.get("cadence", "daily"),
        include_wti=bool(body.get("include_wti", True)),
    )
    return jsonify({"data": out, "timestamp": _now()})


# ─────────────────────────────────────────────────────────────────────────────
# Paper-trading sandbox
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/api/paper/push", methods=["POST"])
def paper_push():
    """
    Open a new paper trade. Body can be:
      • the full trade-idea payload, OR
      • {} — we pull the latest from /api/trade-idea cache and use that.
    Optional override: size (default 1.0), asset (default brent).
    """
    body = request.get_json(silent=True) or {}
    idea = body.get("idea") or body
    # Empty body → use cached trade idea
    if not idea or not idea.get("direction"):
        idea = _fetch_trade_idea() or {}
    if not idea.get("asset"):
        idea["asset"] = body.get("asset", "brent")
    size = float(body.get("size", 1.0))
    from paper_trading import push_trade
    out = push_trade(idea, size=size, source=body.get("source", "trade_idea"))
    return jsonify({"data": out, "timestamp": _now()}), (200 if out.get("ok") else 400)


@app.route("/api/paper/close/<int:trade_id>", methods=["POST"])
def paper_close(trade_id: int):
    body = request.get_json(silent=True) or {}
    from paper_trading import close_trade
    out = close_trade(trade_id, reason=body.get("reason", "manual"))
    return jsonify({"data": out, "timestamp": _now()}), (200 if out.get("ok") else 404)


@app.route("/api/paper/positions")
def paper_positions():
    status = request.args.get("status", "all")
    from paper_trading import list_positions
    return respond(PaperPositionsResponse, list_positions(status=status), _now())


@app.route("/api/paper/performance")
def paper_performance():
    from paper_trading import get_performance
    return respond(PaperPerformanceResponse, get_performance(), _now())


@app.route("/api/paper/clear", methods=["POST"])
def paper_clear():
    body = request.get_json(silent=True) or {}
    from paper_trading import clear_trades
    n = clear_trades(scope=body.get("scope", "closed"))
    return jsonify({"data": {"removed": n}, "timestamp": _now()})


# ─────────────────────────────────────────────────────────────────────────────
# Health detail — per-stream up/stale/down with last-known age + error.
# Reads ONLY from the SQLite cache so it's instant and doesn't trigger
# upstream fetches itself.
# ─────────────────────────────────────────────────────────────────────────────

from db.cache import _conn as _cache_conn  # type: ignore

# (cache_key, display_label, ttl_seconds, optional probe fn that returns
#  (status, detail) given the cached value. Probe should be cheap.)
_HEALTH_STREAMS: list[tuple[str, str, int, "callable"]] = []   # populated below

def _probe_default(d):
    """Generic non-empty check."""
    if not d:                            return ("down", "no cached value")
    if isinstance(d, dict) and d.get("stale"):
        return ("stale", d.get("error") or "marked stale by source")
    return ("up", None)

def _probe_prices(d):
    if not d or not d.get("brent", {}).get("price"):
        return ("down", "no brent price")
    return ("up", None)

def _probe_articles(d):
    if not d:                                                  return ("down", "no payload")
    arts = d.get("articles") or []
    if d.get("stale"):                                         return ("stale", d.get("error"))
    if not arts:                                               return ("stale", "no articles")
    return ("up", f"{len(arts)} articles")

def _probe_available(d):
    if not d:                                                  return ("down", "no payload")
    if d.get("available") is False:                            return ("stale", d.get("error") or "available=false")
    return ("up", None)

def _probe_rig(d):
    if not d or d.get("current") is None:                      return ("down", "no value")
    if d.get("stale"):                                         return ("stale", d.get("note") or "stale")
    return ("up", f"current={d.get('current')}")

def _probe_fv(d):
    if not d or not d.get("brent"):                            return ("down", "no payload")
    b = d["brent"]
    if not b.get("fair_value"):                                return ("down", "no fair_value")
    if b.get("degraded"):                                      return ("stale", f"degraded: {','.join(b.get('degraded_components', []))}")
    return ("up", f"dev {b.get('deviation_pct')}%")

# (cache_key, display_label, TTL seconds, probe function)
_HEALTH_STREAMS = [
    ("prices",          "Live prices",            TTL_PRICES,        _probe_prices),
    ("ohlcv",           "OHLCV intraday",         TTL_OHLCV,         _probe_default),
    ("history",         "Daily history",          TTL_HISTORY,       _probe_default),
    ("curve",           "Forward curve",          TTL_CURVE,         _probe_default),
    ("fair_value",      "Fair value model",       TTL_FAIR_VALUE,    _probe_fv),
    ("signal",          "Signal engine",          TTL_SIGNAL,        _probe_default),
    ("correlations",    "Correlations",           TTL_CORRELATIONS,  _probe_default),
    ("fundamentals",    "Fundamentals",           TTL_FUNDAMENTALS,  _probe_default),
    ("news",            "News",                   TTL_NEWS,          _probe_articles),
    ("weather",         "Weather (Open-Meteo)",   TTL_WEATHER,       _probe_default),
    ("technicals",      "Technicals",             TTL_TECHNICALS,    _probe_default),
    ("term_structure",  "Term structure",         TTL_TERM_STRUCTURE,_probe_default),
    ("macro",           "Macro (FRED)",           TTL_MACRO,         _probe_default),
    ("patterns",        "Pattern recognition",    TTL_PATTERNS,      _probe_default),
    ("iv",              "Implied vol (OVX)",      TTL_IV,            _probe_default),
    ("trade_idea",      "Trade idea + brief",     TTL_TRADE,         _probe_default),
    ("alerts",          "Alerts",                 TTL_ALERTS,        _probe_default),
    ("cracks",          "Crack spreads",          TTL_CRACKS,        _probe_default),
    ("steo",            "EIA STEO",               TTL_STEO,          _probe_available),
    ("analyst_watch",   "Analyst watch (GDELT)",  TTL_ANALYST_WATCH, _probe_default),
    ("tanker_watch",    "Tanker watch (AIS)",     TTL_TANKER_WATCH,  _probe_available),
    ("spreads_history", "Spreads history",        TTL_SPREADS_HIST,  _probe_default),
    ("seasonality",     "Seasonality",            TTL_SPREADS_HIST,  _probe_default),
    ("eia_surprise",    "EIA Surprise tracker",   TTL_EIA_SURPRISE,  _probe_default),
    ("forward_cover",   "Forward cover",          TTL_EIA_SURPRISE,  _probe_default),
    ("ovx",             "CBOE OVX (FRED)",        TTL_OVX,           _probe_default),
    ("curve_regime",    "Curve regime 15y",       TTL_CURVE_REGIME,  _probe_available),
    ("order_flow",      "Order flow (desk)",      TTL_ORDER_FLOW,    _probe_available),
    ("jodi",            "JODI-Oil",               TTL_JODI,          _probe_available),
    ("gdelt_tone",      "GDELT tone",             TTL_GDELT_TONE,    _probe_default),
    ("marketaux",       "MarketAux news",         TTL_MARKETAUX,     _probe_articles),
    ("analogs",         "Pattern analogs",        TTL_ANALOGS,       _probe_available),
]


def _read_cache_row(key: str):
    """Return (value_dict_or_None, updated_at_epoch_or_None) without touching TTL."""
    try:
        c = _cache_conn()
        row = c.execute("SELECT value_json, updated_at FROM cache WHERE key=?", (key,)).fetchone()
        if not row:
            return (None, None)
        import json as _json
        return (_json.loads(row[0]), float(row[1]))
    except Exception:
        return (None, None)


@app.route("/api/health-detail")
def health_detail():
    """
    Per-stream health snapshot. Status codes:
      up    — fresh cache, payload looks healthy
      stale — cache present but flagged stale OR older than 3x its TTL
      down  — no cache row at all OR probe says "down"
    """
    now_ts = time.time()
    streams = []
    counts  = {"up": 0, "stale": 0, "down": 0}
    for key, label, ttl, probe in _HEALTH_STREAMS:
        value, updated = _read_cache_row(key)
        age = int(now_ts - updated) if updated else None
        # Run the per-stream probe
        if value is None:
            status, detail = ("down", "no cached value yet")
        else:
            status, detail = probe(value)
        # Promote to "stale" if cache exists but is way past its TTL
        if status == "up" and age is not None and age > ttl * 3:
            status, detail = ("stale", f"age {age}s > 3x ttl {ttl}s")
        counts[status] += 1
        streams.append({
            "key":     key,
            "label":   label,
            "status":  status,
            "detail":  detail,
            "age_s":   age,
            "ttl_s":   ttl,
        })
    # Sprint 0b: surface observability stack health as two synthetic streams.
    # These don't sit in the cache — we read directly from the observability
    # module's in-process state, which is cheap.
    try:
        from observability import state as _obs_state
        s = _obs_state()
        for key, label, enabled, token_key in (
            ("sentry",       "Sentry (errors)",        s["sentry_enabled"],
                "sentry_dsn_set"),
            ("better_stack", "Better Stack (logs)",    s["better_stack_enabled"],
                "better_stack_token_set"),
        ):
            if enabled:
                status, detail = "up", None
            elif s.get(token_key):
                status, detail = "stale", "configured but init failed"
            else:
                status, detail = "down", "no token configured"
            counts[status] += 1
            streams.append({
                "key": key, "label": label, "status": status,
                "detail": detail, "age_s": None, "ttl_s": None,
            })
    except Exception as exc:
        log.warning("health-detail: observability probe failed: %s", exc)

    overall = "ok" if counts["down"] == 0 and counts["stale"] == 0 \
              else "degraded" if counts["down"] == 0 else "down"
    return respond(HealthDetailResponse, {
        "overall":   overall,
        "counts":    counts,
        "total":     len(streams),
        "streams":   streams,
    }, _now())



@app.route("/api/prices")
def prices():
    return respond(PricesResponse, _fetch_prices(), _now(), stale=False)


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
    return respond(SignalResponse, _fetch_signal(), _now())


@app.route("/api/correlations")
def correlations():
    data = _fetch_correlations()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/fundamentals")
def fundamentals():
    return respond(FundamentalsResponse, _fetch_fundamentals(), _now())


@app.route("/api/news")
def news():
    return respond(NewsResponse, _fetch_news(), _now())


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
    return respond(TradeIdeaResponse, _fetch_trade_idea(), _now())


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


@app.route("/api/ovx")
def ovx_route():
    """CBOE OVX (real implied vol for crude) via FRED."""
    data = _fetch_ovx()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/curve-regime")
def curve_regime_route():
    """15-year Brent M1-M12 spread percentile & regime classification."""
    data = _fetch_curve_regime()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/order-flow")
def order_flow_route():
    """Daily buy/sell volume imbalance per Brent contract."""
    data = _fetch_order_flow()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/jodi")
def jodi_route():
    """JODI-Oil OPEC+ monthly crude production."""
    data = _fetch_jodi()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/gdelt-tone")
def gdelt_tone_route():
    """GDELT GKG aggregate tone for energy themes (geo-risk input)."""
    data = _fetch_gdelt_tone()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/marketaux")
def marketaux_route():
    """MarketAux energy-industry news (secondary news source)."""
    data = _fetch_marketaux()
    return jsonify({"data": data, "timestamp": _now()})


@app.route("/api/analogs")
def analogs_route():
    """stumpy matrix-profile analogs vs the current 60-day price window."""
    data = _fetch_analogs()
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
        "ovx":            {"data": _fetch_ovx()},
        "curve_regime":   {"data": _fetch_curve_regime()},
        "order_flow":     {"data": _fetch_order_flow()},
        "jodi":           {"data": _fetch_jodi()},
        "gdelt_tone":     {"data": _fetch_gdelt_tone()},
        "marketaux":      {"data": _fetch_marketaux()},
        "analogs":        {"data": _fetch_analogs()},
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

    # Step 3 — Fundamentals (uses the single source-of-truth builder so the
    # cache always matches the shape that /api/fundamentals expects, including
    # opec_jodi, curve_regime, order_flow.)
    try:
        _wc_prices = get_cached("prices", TTL_PRICES) or {}
        _wc_hh     = _wc_prices.get("henry_hub", {}).get("price") if _wc_prices else None
        set_cache("fundamentals", _build_fundamentals(_wc_hh))
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
