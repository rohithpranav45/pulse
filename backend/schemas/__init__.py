"""
Pydantic response models for PULSE API
======================================
Sprint 0a — typed contracts between the Flask backend and the React frontend.

Why
---
Phase 2 will add ~15 new endpoints. Every "frontend reads the wrong shape"
bug we've shipped in Phase 1 had the same root cause: the response shape
existed only in the developer's head. These models pin every documented
field to a real type, validated at response time, and `scripts/generate_ts_types.py`
emits a matching TypeScript file so the frontend can't drift from the backend.

Design
------
- **Pydantic v2** (`extra="allow"`) so undocumented fields don't break the
  response — we add structure *over* the existing payloads without forcing a
  big-bang rewrite.
- Every public model ends in `Response` (e.g. `PricesResponse`) and exposes
  the full envelope including `timestamp`. The route wraps its payload in
  `respond(Model, data)` (see `respond()` below).
- Validation failures log a warning and fall back to the raw payload — the
  contract is observability-first, not strictness-first. Strict mode can come
  later once every consumer is migrated.

Coverage (Sprint 0a — 8 most-used endpoints)
--------------------------------------------
- /api/prices            → PricesResponse
- /api/fundamentals      → FundamentalsResponse
- /api/news              → NewsResponse
- /api/signal            → SignalResponse
- /api/trade-idea        → TradeIdeaResponse
- /api/paper/positions   → PaperPositionsResponse
- /api/paper/performance → PaperPerformanceResponse
- /api/health-detail     → HealthDetailResponse

Future endpoints follow the same pattern.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Union

from flask import jsonify
from pydantic import BaseModel, ConfigDict, Field, ValidationError

log = logging.getLogger("pulse.schemas")


# ─────────────────────────────────────────────────────────────────────────────
# Base
# ─────────────────────────────────────────────────────────────────────────────
class PulseModel(BaseModel):
    """Common base — accept extra fields so live payloads can grow."""
    model_config = ConfigDict(extra="allow", populate_by_name=True)


# ─────────────────────────────────────────────────────────────────────────────
# /api/prices
# ─────────────────────────────────────────────────────────────────────────────
class PriceQuote(PulseModel):
    price: Optional[float] = None
    change_abs: Optional[float] = None
    change_pct: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    stale: Optional[bool] = None
    timestamp: Optional[str] = None


class PricesData(PulseModel):
    brent: Optional[PriceQuote] = None
    wti: Optional[PriceQuote] = None
    henry_hub: Optional[PriceQuote] = None
    gasoline: Optional[PriceQuote] = None
    heating_oil: Optional[PriceQuote] = None
    dxy: Optional[PriceQuote] = None
    sp500: Optional[PriceQuote] = None
    vix: Optional[PriceQuote] = None
    treasury_10y: Optional[PriceQuote] = None
    gold: Optional[PriceQuote] = None
    stale: Optional[bool] = None


class PricesResponse(PulseModel):
    data: PricesData
    timestamp: str
    stale: Optional[bool] = None


# ─────────────────────────────────────────────────────────────────────────────
# /api/signal
# ─────────────────────────────────────────────────────────────────────────────
class SignalIndicator(PulseModel):
    name: str
    raw_value: Any = None          # number OR dict (e.g. IV component)
    reason: Optional[str] = None
    score: Optional[float] = None
    weight: Optional[float] = None


class AssetSignal(PulseModel):
    asset: str
    direction: Optional[int] = None
    score: Optional[float] = None
    signal: Optional[str] = None
    conviction: Optional[str] = None
    bullish_factors: list[str] = Field(default_factory=list)
    bearish_factors: list[str] = Field(default_factory=list)
    key_risk: Optional[str] = None
    history: list[float] = Field(default_factory=list)
    indicators: list[SignalIndicator] = Field(default_factory=list)
    timestamp: Optional[str] = None


class SignalData(PulseModel):
    brent: Optional[AssetSignal] = None
    wti: Optional[AssetSignal] = None
    henry_hub: Optional[AssetSignal] = None


class SignalResponse(PulseModel):
    data: SignalData
    timestamp: str


# ─────────────────────────────────────────────────────────────────────────────
# /api/trade-idea
# ─────────────────────────────────────────────────────────────────────────────
class TradeIdeaData(PulseModel):
    direction: Optional[str] = None         # LONG / SHORT / NEUTRAL
    signal: Optional[str] = None
    conviction: Optional[str] = None
    score: Optional[float] = None
    live_price: Optional[float] = None
    fair_value: Optional[float] = None
    target_level: Optional[float] = None
    stop_level: Optional[float] = None
    time_horizon: Optional[str] = None
    entry_thesis: list[str] = Field(default_factory=list)
    key_risk: Optional[str] = None
    morning_brief: Optional[str] = None
    stale: Optional[bool] = None
    timestamp: Optional[str] = None


class TradeIdeaResponse(PulseModel):
    data: TradeIdeaData
    timestamp: str


# ─────────────────────────────────────────────────────────────────────────────
# /api/fundamentals
# ─────────────────────────────────────────────────────────────────────────────
class CotEntry(PulseModel):
    date: Optional[str] = None
    label: Optional[str] = None
    net: Optional[float] = None
    percentile: Optional[float] = None
    signal: Optional[int] = None


class CotSection(PulseModel):
    crude_oil: Optional[CotEntry] = None
    gasoline: Optional[CotEntry] = None
    heating_oil: Optional[CotEntry] = None
    natural_gas: Optional[CotEntry] = None


class RigCount(PulseModel):
    current: Optional[int] = None
    previous: Optional[int] = None
    change: Optional[int] = None
    date: Optional[str] = None
    source: Optional[str] = None
    note: Optional[str] = None
    stale: Optional[bool] = None
    timestamp: Optional[str] = None


class FundamentalsData(PulseModel):
    # Each sub-payload is intentionally loose — the rich fetcher output is too
    # variable to pin down without churn. We document the top-level keys.
    inventory:    Optional[dict[str, Any]] = None
    snapshot:     Optional[dict[str, Any]] = None
    cot:          Optional[CotSection]     = None
    opec:         Optional[dict[str, Any]] = None
    opec_jodi:    Optional[dict[str, Any]] = None
    opec_eia:     Optional[dict[str, Any]] = None
    geo_risk:     Optional[dict[str, Any]] = None
    rig_count:    Optional[RigCount]       = None
    seasonality:  Optional[dict[str, Any]] = None
    spark_dark:   Optional[dict[str, Any]] = None
    curve_regime: Optional[dict[str, Any]] = None
    order_flow:   Optional[dict[str, Any]] = None
    stale: Optional[bool] = None


class FundamentalsResponse(PulseModel):
    data: FundamentalsData
    timestamp: str


# ─────────────────────────────────────────────────────────────────────────────
# /api/news
# ─────────────────────────────────────────────────────────────────────────────
class NewsArticle(PulseModel):
    title: Optional[str] = None
    headline: Optional[str] = None
    url: Optional[str] = None
    source: Optional[str] = None
    feed: Optional[str] = None
    category: Optional[str] = None
    published: Optional[str] = None
    published_at: Optional[str] = None
    time: Optional[str] = None
    sentiment: Optional[float] = None
    is_negative: Optional[bool] = None


class NewsData(PulseModel):
    articles: list[NewsArticle] = Field(default_factory=list)
    negative_count: Optional[int] = None
    stale: Optional[bool] = None


class NewsResponse(PulseModel):
    data: NewsData
    timestamp: str


# ─────────────────────────────────────────────────────────────────────────────
# /api/paper/positions  +  /api/paper/performance
# ─────────────────────────────────────────────────────────────────────────────
class PaperLeg(PulseModel):
    id: int
    trade_id: int
    contract: str
    direction: str
    qty: float
    entry_price: float
    mtm_price: Optional[float] = None
    mtm_at: Optional[str] = None
    unrealised: Optional[float] = None
    exit_price: Optional[float] = None
    realised: Optional[float] = None


class PaperPosition(PulseModel):
    id: int
    asset: Optional[str] = None
    direction: Optional[str] = None
    status: Optional[str] = None
    source: Optional[str] = None
    conviction: Optional[str] = None
    size: Optional[float] = None
    entry_price: Optional[float] = None
    target_price: Optional[float] = None
    stop_price: Optional[float] = None
    exit_price: Optional[float] = None
    mtm_price: Optional[float] = None
    mtm_at: Optional[str] = None
    opened_at: Optional[str] = None
    closed_at: Optional[str] = None
    close_reason: Optional[str] = None
    realised: Optional[float] = None
    realised_pct: Optional[float] = None
    unrealised: Optional[float] = None
    thesis: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    legs: list[PaperLeg] = Field(default_factory=list)


class PaperPositionsResponse(PulseModel):
    data: list[PaperPosition]
    timestamp: str


class PaperTradeRef(PulseModel):
    id: Optional[int] = None
    asset: Optional[str] = None
    pnl: Optional[float] = None


class EquityPoint(PulseModel):
    closed_at: Optional[str] = None
    cum_pnl: Optional[float] = None
    trade_id: Optional[int] = None


class PaperPerformanceData(PulseModel):
    total_trades: Optional[int] = None
    wins: Optional[int] = None
    losses: Optional[int] = None
    win_rate_pct: Optional[float] = None
    total_pnl: Optional[float] = None
    avg_pnl_per_trade: Optional[float] = None
    avg_win: Optional[float] = None
    avg_loss: Optional[float] = None
    profit_factor: Optional[float] = None
    sharpe_annualised: Optional[float] = None
    max_drawdown: Optional[float] = None
    best_trade: Optional[PaperTradeRef] = None
    worst_trade: Optional[PaperTradeRef] = None
    equity_curve: list[EquityPoint] = Field(default_factory=list)
    timestamp: Optional[str] = None


class PaperPerformanceResponse(PulseModel):
    data: PaperPerformanceData
    timestamp: str


# ─────────────────────────────────────────────────────────────────────────────
# /api/health-detail
# ─────────────────────────────────────────────────────────────────────────────
class HealthStream(PulseModel):
    key: str
    label: str
    status: str                                # "up" | "stale" | "down"
    detail: Optional[str] = None
    age_s: Optional[int] = None
    ttl_s: Optional[int] = None


class HealthCounts(PulseModel):
    up: int = 0
    stale: int = 0
    down: int = 0


class HealthDetailData(PulseModel):
    overall: str                               # "ok" | "degraded" | "down"
    counts: HealthCounts
    total: Optional[int] = None
    streams: list[HealthStream] = Field(default_factory=list)


class HealthDetailResponse(PulseModel):
    data: HealthDetailData
    timestamp: str


# ─────────────────────────────────────────────────────────────────────────────
# Public registry — used by both the route helper and the TS codegen
# ─────────────────────────────────────────────────────────────────────────────
RESPONSE_MODELS: dict[str, type[PulseModel]] = {
    "/api/prices":            PricesResponse,
    "/api/fundamentals":      FundamentalsResponse,
    "/api/news":              NewsResponse,
    "/api/signal":            SignalResponse,
    "/api/trade-idea":        TradeIdeaResponse,
    "/api/paper/positions":   PaperPositionsResponse,
    "/api/paper/performance": PaperPerformanceResponse,
    "/api/health-detail":     HealthDetailResponse,
}


# ─────────────────────────────────────────────────────────────────────────────
# Route helper
# ─────────────────────────────────────────────────────────────────────────────
def respond(
    model: type[PulseModel],
    data: Any,
    timestamp: str,
    **extra_envelope: Any,
):
    """
    Wrap a fetcher payload in the documented envelope, validate against the
    Pydantic model, and return a Flask JSON response.

    On validation failure we log a warning and return the raw payload — the
    goal is to make drift visible without breaking live consumers. Add the
    PULSE_STRICT_SCHEMAS=1 env var to flip this to hard 500s in dev.
    """
    import os

    payload = {"data": data, "timestamp": timestamp, **extra_envelope}
    try:
        model_obj = model.model_validate(payload)
        return jsonify(model_obj.model_dump(mode="json", exclude_none=False))
    except ValidationError as exc:
        log.warning(
            "schema validation failed for %s: %s",
            model.__name__,
            exc.errors()[:3],
        )
        if os.environ.get("PULSE_STRICT_SCHEMAS") == "1":
            raise
        return jsonify(payload)
