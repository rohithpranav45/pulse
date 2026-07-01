"""
News impact — headline → {factor, direction, expected % move, t-stat, regime}.
==============================================================================

Sprint 2. The decision layer on top of the event study: take a headline, classify
its FACTOR (classify.py), give it a signed crude SENTIMENT (event_study), and turn
that into an expected Brent % move using the empirically fitted per-factor beta —
**but only when that beta is statistically earned.**

Prior-then-learn gate (the per-spread-gate pattern, gate_config.py):
  * If the factor's measured beta clears |t| ≥ T_MIN on ≥ MIN_N headlines, use the
    MEASURED beta — basis = "measured".
  * Otherwise fall back to a labelled, economically-reasoned PRIOR magnitude —
    basis = "prior" — and say so. A noisy keyword-sentiment tape on a few hundred
    headlines will leave most factors on the prior; that's honest, not a failure.

So the desk never sees a fabricated-precise number: it sees either a measured beta
with its t-stat, or an explicitly-labelled prior.

Public API
----------
  score_headline(title, factor=, ...)   -> dict
  impact_feed(limit=, betas=)           -> list[dict]   (ranked recent headlines)
  factor_table_view(betas=)             -> list[dict]   (per-factor beta table)
  current_regime(frames=)               -> dict
  to_results(betas=)                    -> dict          (the API payload)

Run standalone:  python -m backend.research.news_impact.impact
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from research.news_impact import event_study  # noqa: E402
from research.news_impact.classify import FACTORS  # noqa: E402

log = logging.getLogger("pulse.news_impact.impact")

MIN_N = event_study.MIN_N
T_MIN = event_study.T_MIN

# Labelled priors — the expected |Brent % move| per +1 unit of sentiment magnitude
# when there isn't (yet) a significant measured beta. Economically reasoned and
# deliberately conservative; the gate replaces these with measured betas as the
# corpus grows. (magnitude_pct, one-line rationale)
FACTOR_PRIORS: dict[str, tuple[float, str]] = {
    "GEOPOLITICAL":      (0.90, "supply-risk / chokepoint shocks move oil the most"),
    "SUPPLY_OPEC":       (0.70, "OPEC+ policy is a direct supply lever"),
    "DEMAND_MACRO":      (0.50, "global-growth / China demand re-rates the curve"),
    "INVENTORY":         (0.40, "weekly stock surprise; regime-gated, often noise on flat price"),
    "MONETARY_DOLLAR":   (0.40, "Fed / dollar moves crude via the macro channel"),
    "REFINING_PRODUCTS": (0.30, "crack / run news hits products more than crude"),
    "WEATHER":           (0.30, "transient supply/demand unless a major outage"),
    "POSITIONING":       (0.25, "flow / COT amplifies rather than initiates"),
    "NOISE":             (0.00, "no clear oil-price driver"),
}


def _prior(factor: str) -> tuple[float, str]:
    return FACTOR_PRIORS.get(factor, (0.20, "unclassified driver — small default prior"))


def _betas_index(betas: dict | None, horizon: str | None = None) -> dict:
    """Map factor -> its row from the cached betas table at the headline horizon."""
    if betas is None:
        betas = event_study.load_cached()
    if not betas:
        return {}
    horizon = horizon or betas.get("headline_horizon", "1d")
    table = (betas.get("tables") or {}).get(horizon) or betas.get("factors") or []
    return {r["factor"]: r for r in table if r.get("factor")}


def _classify_one(title: str) -> tuple[str, str, float]:
    """Classify a single headline → (factor, source, confidence). Groq if available,
    else the deterministic keyword fallback (never hard-fails)."""
    from research.news_impact.classify import classify_headlines
    res = classify_headlines([title])[0]
    return res["factor"], res.get("source", "keyword"), float(res.get("confidence", 0.5))


def score_headline(title: str,
                   factor: str | None = None,
                   factor_source: str | None = None,
                   published_at: str | None = None,
                   betas: dict | None = None,
                   regime: dict | None = None,
                   horizon: str | None = None) -> dict:
    """
    Score one headline into the decision shape:
      {title, factor, factor_source, sentiment, direction, expected_pct_move,
       t_stat, n, basis, beta_pct, regime_context, rationale}

    basis="measured" when the factor's fitted beta cleared the gate; else "prior".
    direction is LONG/SHORT/NEUTRAL from sign(beta × sentiment).
    """
    idx = _betas_index(betas, horizon)
    if factor is None:
        factor, factor_source, _ = _classify_one(title)
    factor_source = factor_source or "given"

    sentiment = event_study.signed_sentiment(title)
    row = idx.get(factor) or {}
    measured_beta = row.get("beta_brent_pct")
    t = row.get("t_brent")
    n = int(row.get("n", 0) or 0)
    significant = bool(row.get("significant"))

    if significant and measured_beta is not None:
        beta = float(measured_beta)
        basis = "measured"
        rationale = (f"measured beta {beta:+.2f}%/unit (t={t}, n={n}) — "
                     f"{factor} headlines historically moved Brent this way")
    else:
        mag, why = _prior(factor)
        beta = float(mag)               # priors are stated as positive magnitudes
        basis = "prior"
        rationale = (f"prior {beta:.2f}%/unit ({why}); "
                     + ("not enough significant evidence yet"
                        if factor != "NOISE" else "treated as non-driver"))

    expected = round(beta * sentiment, 3)
    if factor == "NOISE" or abs(expected) < 0.05 or sentiment == 0:
        direction = "NEUTRAL"
    else:
        direction = "LONG" if expected > 0 else "SHORT"

    # regime context — the factor's beta inside today's curve regime, if measured
    reg = regime if regime is not None else current_regime()
    curve = reg.get("curve")
    reg_beta = None
    if curve and row.get("by_curve"):
        rb = (row["by_curve"].get(curve) or {})
        reg_beta = rb.get("slope")

    return {
        "title": title,
        "published_at": published_at,
        "factor": factor,
        "factor_source": factor_source,
        "factor_label": FACTORS.get(factor, ""),
        "sentiment": round(sentiment, 3),
        "direction": direction,
        "expected_pct_move": expected,
        "beta_pct": round(beta, 3),
        "t_stat": t,
        "n": n,
        "basis": basis,
        "regime_context": {"curve": curve, "regime_beta_pct": reg_beta,
                           "as_of": reg.get("as_of")},
        "rationale": rationale,
    }


def current_regime(frames: dict | None = None) -> dict:
    """Today's Brent curve regime (BACK/CONTANGO) + trailing vol, from the tape.
    Returns {curve: None} gracefully when the tape isn't available (e.g. tests)."""
    try:
        if frames is None:
            frames = event_study._load_price_frames()
        curve = frames["brent_curve"]
        rvol = frames["rvol"]
        if curve is None or len(curve) == 0:
            return {"curve": None, "as_of": None}
        last = curve.iloc[-1]
        as_of = str(curve.index[-1].date())
        regime = "BACK" if float(last["c1"]) > float(last["c3"]) else "CONTANGO"
        vol = float(rvol.iloc[-1]) if len(rvol) and rvol.iloc[-1] == rvol.iloc[-1] else None
        return {"curve": regime, "as_of": as_of, "baseline_vol_pct": vol}
    except Exception as exc:
        log.info("current_regime unavailable (%s)", type(exc).__name__)
        return {"curve": None, "as_of": None}


def impact_feed(limit: int = 40, betas: dict | None = None,
                regime: dict | None = None, order: str = "impact") -> list[dict]:
    """
    Recent classified headlines, scored. ``order="impact"`` (default) ranks by
    |expected % move| — the desk's 'biggest movers' view; ``order="recent"`` ranks
    newest-first — the live tape view (used by /api/news/impact once the live news
    wire is feeding the corpus, so today's headlines lead instead of high-impact
    historical ones). Reads the live corpus.
    """
    from research.news_impact import corpus
    if betas is None:
        betas = event_study.load_cached()
    if regime is None:
        regime = current_regime()
    # Exclude NOISE — the impact feed is "what's worth something"; the raw tape
    # (incl. non-oil/NOISE items) lives in the Live Headlines panel.
    rows = [r for r in corpus.recent(limit=max(limit * 6, 300))
            if r.get("factor") and r["factor"] != "NOISE"]
    scored = [score_headline(
        r.get("title", ""), factor=r["factor"], factor_source="corpus",
        published_at=r.get("published_at"), betas=betas, regime=regime) for r in rows]
    if order == "recent":
        scored.sort(key=lambda s: (s.get("published_at") or ""), reverse=True)
    else:
        scored.sort(key=lambda s: abs(s["expected_pct_move"] or 0), reverse=True)
    return scored[:limit]


def live_scored(articles: list, betas: dict | None = None,
                regime: dict | None = None, limit: int = 60) -> list[dict]:
    """
    Score the LIVE news wire directly (for the Live Headlines strip): every
    headline gets a factor + expected % move with a clean ISO timestamp, without
    depending on whether it's been ingested into the corpus yet.

    Factor source, in order: the corpus's stored (Groq) factor when the URL is
    already classified, else the deterministic keyword classifier. Timestamps are
    normalised through the corpus parser so GDELT's compact ``YYYYMMDDTHHMMSSZ``
    (which JS Date.parse can't read) becomes ISO-8601.
    """
    from research.news_impact import corpus, classify
    if betas is None:
        betas = event_study.load_cached()
    if regime is None:
        regime = current_regime()
    known = corpus.factors_by_url([a.get("url") for a in articles])
    out = []
    for a in articles[:limit]:
        title = (a.get("title") or a.get("headline") or "").strip()
        if not title:
            continue
        url = a.get("url")
        ts = corpus._norm_ts(a.get("published_at") or a.get("published") or a.get("time"))
        kf = known.get(url)
        if kf:
            factor, fsrc = kf[0], "corpus"
        else:
            factor, _ = classify.keyword_factor(title)
            fsrc = "keyword"
        s = score_headline(title, factor=factor, factor_source=fsrc,
                           published_at=ts, betas=betas, regime=regime)
        s["url"] = url
        s["source"] = a.get("source")
        s["category"] = a.get("category")
        s["news_sentiment"] = (a.get("sentiment_score")
                               if a.get("sentiment_score") is not None else a.get("sentiment"))
        out.append(s)
    return out


def factor_table_view(betas: dict | None = None, horizon: str | None = None) -> list[dict]:
    """
    Per-factor beta table for /api/news/factors: every factor in the taxonomy with
    its measured beta (when significant) or labelled prior, plus the basis, the
    curve-regime split, and sample size — the at-a-glance 'what each factor is worth'.
    """
    idx = _betas_index(betas, horizon)
    rows = []
    for factor, label in FACTORS.items():
        row = idx.get(factor) or {}
        significant = bool(row.get("significant"))
        prior_mag, prior_note = _prior(factor)
        rows.append({
            "factor": factor,
            "label": label,
            "n": int(row.get("n", 0) or 0),
            "basis": "measured" if significant else "prior",
            "beta_pct": row.get("beta_brent_pct") if significant else prior_mag,
            "t_stat": row.get("t_brent"),
            "r2": row.get("r2_brent"),
            "beta_wti_pct": row.get("beta_wti_pct"),
            "aligned_mean_move": row.get("aligned_mean_move"),
            "aligned_hit_rate": row.get("aligned_hit_rate"),
            "significant": significant,
            "prior_note": prior_note,
            "by_curve": row.get("by_curve") or {},
        })
    rows.sort(key=lambda r: (r["significant"], abs((r["t_stat"] or 0))), reverse=True)
    return rows


def to_results(betas: dict | None = None, limit: int = 40, order: str = "recent") -> dict:
    """The composed payload behind /api/news/impact and /api/news/factors. The live
    feed defaults to ``order="recent"`` (newest headlines lead) now that the news
    wire feeds the corpus."""
    if betas is None:
        betas = event_study.load_cached()
    reg = current_regime()
    feed = impact_feed(limit=limit, betas=betas, regime=reg, order=order)
    factors = factor_table_view(betas=betas)
    return {
        "available": bool(betas and betas.get("available")),
        "as_of": reg.get("as_of"),
        "regime": reg,
        "horizon": (betas or {}).get("headline_horizon", "1d"),
        "n_headlines": (betas or {}).get("n_headlines", 0),
        "span": (betas or {}).get("span"),
        "min_n": MIN_N,
        "t_min": T_MIN,
        "feed": feed,
        "factors": factors,
        "source": "backend/research/news_impact/impact",
    }


if __name__ == "__main__":
    import io, json
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.WARNING)

    betas = event_study.load_cached()
    if not betas:
        print("No cached betas yet — run event_study.compute_and_cache() first.")
    reg = current_regime()
    print(f"Current Brent regime: {reg.get('curve')} (as of {reg.get('as_of')})\n")

    print("=== PER-FACTOR TABLE (measured beta where earned, else prior) ===")
    for r in factor_table_view(betas):
        tag = "MEASURED" if r["significant"] else "prior   "
        print(f"  {r['factor']:18s} [{tag}] beta={r['beta_pct']:+.2f}%/unit  "
              f"t={r['t_stat']}  n={r['n']}")

    print("\n=== IMPACT FEED (top by |expected move|) ===")
    for s in impact_feed(limit=12, betas=betas, regime=reg):
        print(f"  {s['direction']:7s} {s['expected_pct_move']:+.2f}%  "
              f"[{s['factor']}/{s['basis']}]  {s['title'][:72]}")
