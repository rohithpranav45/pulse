# Mentor follow-ups — ready to send

Two messages drafted and ready. **You send these** (they're owner/relationship comms — I can't).
Edit the tone/details to taste, then after sending, jot a line in the mentor communication log
inside `docs/PHASE_HISTORY.md`.

---

## 1. WTI daily-settlement file (alignment Q5)

*Context: she sent `CL_data.csv`, which is the 1-min midprice data we already had — not a daily
settlement file. We're currently synthesising daily WTI settlements from it (flagged ESTIMATE),
which limits WTI history to 2021+.*

> Hi [mentor],
>
> Quick follow-up on the WTI data. The `CL_data.csv` you shared is the 1-min midprice series — we
> already have that, and I've been synthesising daily WTI settlements from it (last mid per session)
> to drive the WTI side of the regime engine. It works, but it's a session-end mid rather than a true
> exchange settlement, so the WTI model fits carry an asterisk and only reach back to 2021.
>
> What would really help is a **daily settlement file for WTI (CL), C1 through ~C6**, in the same
> shape as the Brent C1–C31 daily settlement file we've been using. That would let the WTI models
> train back to 2016 and drop the ESTIMATE flag.
>
> If that file exists on the desk, what's the easiest way for you to drop it on the shared folder?
> If not, no problem — the synthetic version is clearly labelled in the dashboard.
>
> Thanks!

---

## 2. Phase 2 status + sign-off on the provisional scope decisions

*Context: the 7 alignment questions from 2026-06-05. We made provisional calls to keep moving; her
sign-off is still pending.*

> Hi [mentor],
>
> Quick Phase 2 update, plus a few things I'd value your sign-off on.
>
> **Where it stands:** the regime engine is live end-to-end — 6 instruments (Brent + WTI: M1-M2,
> M3-M6, front fly) across a 3-axis regime grid (curve × inventory × vol), a 7-model per-cell
> competition (Ridge / Lasso / ElasticNet / Huber + XGBoost / LightGBM / CatBoost), a walk-forward
> backtest against a rolling-z baseline, and a methodology PDF. Honest headline: regime conditioning
> adds value on a specific gated slice rather than across the board. I've also tuned the exit rule
> (take-profit halfway to fair value, 2.5σ stop, 30-day time-stop) and I'm running a live A/B paper
> test (gated vs un-gated pooled) to validate before changing the production default — going on an
> always-on host so the paper book accumulates win-rate proof 24/7.
>
> **Could you confirm or redirect on these?** (I made provisional calls so I wasn't blocked.)
> 1. **Instrument scope** — 6 spreads (3 Brent + 3 WTI mirrors), inter-product fly dropped. OK?
> 2. **Regime axes** — curve × inventory × vol (27 cells). Keep, or swap the inventory axis for
>    something else (e.g. inventory *surprise* vs forecast)?
> 3. **Horizon** — defaulted to 20-day mean reversion. Want me to also evaluate 5-day / 60-day?
> 4. **Auto-push** — opportunities currently display only (I push to paper manually). Prefer
>    auto-stage for approval, or auto-push above a confidence threshold?
> 5. **Phase 1 coexistence** — kept both (Phase 1 = directional Brent, Phase 2 = spreads/flies).
>    Keep both, or fold one in?
>
> Happy to walk through any of it. Thanks!

---

*Drafted 2026-06-14. Roadmap task T1.3.*
