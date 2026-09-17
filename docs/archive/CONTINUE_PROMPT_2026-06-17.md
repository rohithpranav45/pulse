# Continue-from-here prompt

Copy-paste this whole block into your next session. It's self-contained — the new agent doesn't need to read anything else first.

---

```
Continuing from yesterday's session (full handoff at docs/SESSION_2026-06-17.md — read it first).

Where we left off:
- Replaced the per-cell regime model with a production "global" model
  (regime-as-feature, LightGBM point regressor per spread, empirical OOS
  residual bands). Code in backend/research/models_global.py.
- Wired into live_ranker as mode="global" (now the default).
- 17 pytest passing, frontend build clean, both committed and pushed to main.
- 18-month seeded paper book: 374 trades, +$110,183 net, PF 1.75 across
  4 tradeable spreads (brent_m1_m2 + brent_fly_123 + wti_m1_m2 + wti_fly_123).
- HF Space at https://rohithpranav45-pulse.hf.space pulls from GitHub main
  at build time. If the deploy didn't auto-rebuild after my push, see
  step 1 of the backlog.

Known caveats (not bugs — known and surfaced honestly):
- /Data daily file ends 2026-05-26; slow features (inv/COT/vol/cracks/rates)
  are stale → some live signals trip the |z|>8 sanity gate today.
- wti_m1_m2 PF=0.76 — the documented SYNTH caveat; WTI models trained on
  synthetic settlements built from 1-min mids.
- backend/data/research/models_global/ is gitignored (matches the existing
  models* pattern). Run `python -m backend.research.models_global` after
  pulling on any new machine; takes ~30 seconds.

What I want to do next (pick one or push back if you think something else
should come first):

  PRIORITY 1 — Push the production model to HF
    Make sure the global model artifacts ship to HF. Two options:
    (a) Bake into the HF private Dataset alongside the parquet lake, OR
    (b) Add a `python -m backend.research.models_global` step to the HF
        Dockerfile so models train at container boot (~30s on HF's CPU).
    Then trigger a rebuild via:
        huggingface-cli upload <username>/pulse \
            deploy/hf_space/Dockerfile Dockerfile --repo-type space
    Verify at https://rohithpranav45-pulse.hf.space/api/regime/recommendation
    that the response carries `winner_model: LightGBM`.

  PRIORITY 2 — Live feature overlay
    The slow features being 3 weeks stale is making live signals look
    extreme. Build a `live_features.py` that overlays today's brent_close,
    m1_m2_lag1, m3_m6_lag1, fly_lag1, wti_brent_spread, and (if computable
    from the recorder's history) realised_vol_20d into the feature row
    before `predict()`. The cell models will then score on today's market
    state, not yesterday's daily. Should drop the live z-scores from -11/-7
    down to defensible -2 to -3 range without touching the model itself.

  PRIORITY 3 — Refresh /Data pipeline
    Investigate why the daily file (backend/data_lake.py → get_brent_settlements)
    stopped advancing on 2026-05-26. Either the source upstream of /Data
    froze, or the cache isn't being refreshed. This is the cleanest fix.

  PRIORITY 4 — Retrain WTI on real daily settlements
    `data_lake.get_wti_settlements()` returns ESTIMATE from 1-min mids.
    If a real WTI daily settle file is available somewhere (CME EOD,
    a desk share, anywhere), swap it in and rerun
    `python -m backend.research.models_global`. Should lift wti_m1_m2
    PF above 1.

For all of the above:
- Don't break the existing test suite (17 tests, run with `python -m pytest tests/ -q`).
- Production env knob is PULSE_REGIME_MODE=global (default). Falling back
  to pooled is supported but the legacy per-cell models are documented as
  broken (see backend/research/model_health.py top docstring).
- I'm on my laptop now, not the office desk, so PULSE_LIVE_SIGNALS_DISABLED
  may be set or the live feed share I:\ won't resolve. Skip live-feed work
  if that's the case and focus on training/deploy.

Start by reading docs/SESSION_2026-06-17.md end-to-end so you have the full
context, then propose which priority to attack first. Don't dive in
without telling me what you're about to do.
```

---

## Why this prompt works

- **Self-contained** — links to the canonical handoff file but doesn't require it to be opened to understand the situation.
- **Names the artefacts** — the new agent knows exactly which files were touched and where the model lives.
- **Sets prioritised options** — gives the agent productive directions while letting it push back.
- **Honest about constraints** — laptop ≠ desk, share path may not resolve, what's tested vs not.
- **Asks for plan before action** — protects you from a 30-message tangent.
