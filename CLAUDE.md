# PULSE — Project State

**PULSE** — Energy Intelligence Terminal (Futures First internship). A live energy-trading
dashboard: ingests ~35 data sources, runs quant models (fair value + a regime-conditional
spread engine), and serves a React dashboard with a paper-trading book.

- **Stack:** Flask 3 · React 18 + Vite + Tailwind · SQLite (cache + paper book) ·
  DuckDB/Parquet over a 3.5 GB `/Data` desk feed · sklearn + XGBoost/LightGBM/CatBoost
- **Run (local):** `python start.py` from the repo root → http://127.0.0.1:5000
- **Last updated:** 2026-06-14

> 🧭 **Three docs, one per tense:**
> **this file = present** (current state · how to run · architecture · gotchas) ·
> [`docs/ROADMAP.md`](docs/ROADMAP.md) **= future** (pending tasks · timeline · copy-paste session prompts) ·
> [`docs/PHASE_HISTORY.md`](docs/PHASE_HISTORY.md) **= past** (full sprint-by-sprint log).

---

## 1. Current status

### ✅ Shipped
- **Phase 1 — dashboard** (PR #2): 32 live data streams, health monitoring, source provenance,
  directional Brent signal engine, Groq morning brief, paper-trading sandbox, pattern analogs.
- **Phase 2 — regime engine** (PR #3 + follow-ups): regime-conditional spread/butterfly engine over
  **6 instruments** (Brent + WTI {M1-M2, M3-M6, fly}) × a **3-axis regime grid** (curve × inventory × vol).
  **7-model per-cell competition** (Ridge/Lasso/ElasticNet/Huber + XGB/LGBM/CatBoost). Walk-forward
  backtest + methodology PDF. Dedicated Regime tab, 2-leg paper trading, drill/evidence modal.
- **Tuned exit rule (Phase 2.9.x):** the live book closes on **TP = halfway-to-fair · SL = 2.5σ ·
  30-trading-day time-stop**, trading **4 spreads** (drops brent/wti M3-M6). Backtest win rate 82.9%;
  robustness-checked → win-rate robust OOS (~74-75%), but quote NET Sharpe/PF as *in-sample-optimistic*.
- **A/B paper harness:** a daily tick dual-pushes a `pooled` arm and a `gated` arm; `/api/regime/ab`
  reports per-arm NET win rate + Welch/paired t-tests + a verdict. This is the live forward-validation.
- **Phase 3.D deploy artifacts:** multi-stage `Dockerfile`, `docker-compose.yml` (app + Caddy reverse
  proxy w/ basic-auth + auto-HTTPS), `backend/wsgi.py` (gunicorn entry, single worker), SQLite WAL.

### 🔄 In progress — **always-on deployment** (details in memory `pulse-deployment-pending`)
Goal: a public link so the A/B book accumulates 24/7. Host = **Oracle Cloud Always Free (ARM)**,
region `ap-hyderabad-1`; network ready (VCN `pulse-vcn` + public subnet). The free ARM shape is
**out of capacity**, so an **auto-retry loop runs on this PC** (`~/.oci/pulse_launch.py`, hidden via a
Startup-folder launcher, 90s loop; logs to `~/.oci/pulse_launch.log`). On success it writes
`~/.oci/pulse_instance.txt`. **Next:** when it lands → SSH in (`ssh -i ~/.ssh/oracle_pulse ubuntu@<ip>`),
open 80/443 (security list + iptables), `docker compose up -d --build`, hand over the link.

### ⬜ Next / backlog
> **Full backlog + timeline + per-task copy-paste prompts → [`docs/ROADMAP.md`](docs/ROADMAP.md).** Highlights:
- **Phase 3.0** — `tests/test_invariants.py`: assert the cross-module mirrors in §5 stay in sync.
- **Read the A/B verdict** once ≥30 closed trades/arm (or 14 days) → keep gated default or flip to pooled.
- **Phase 2.8 model backlog** (optional): 2.8.4 global model w/ regime-as-feature · 2.8.5 soft regime
  probabilities · 2.8.7 multi-horizon sweep · 2.8.8 extend walk-forward to 2018-2026 · 2.8.9 HMM/
  change-point regimes · 2.8.10 portfolio vol targeting.

---

## 2. How to run

| Task | Command |
|---|---|
| Local dev (serves built React from `backend/static`) | `python start.py` → http://127.0.0.1:5000 |
| Frontend hot-reload | `cd frontend && npm run dev` → :5173 (proxies `/api` to :5000) |
| Rebuild frontend after UI edits | `cd frontend && npm run build` |
| Retrain regime models | `python -m backend.research.models --mode composite` (also `--mode pooled`) |
| Walk-forward backtest (~3 h) | `python -u -m backend.research.walkforward` |
| Regenerate methodology PDF | `python -m backend.research.methodology_pdf` |
| Production container | `docker compose up -d --build` (full runbook: `deploy/README.md`) |

> Fresh machine? `/Data`, the model pkls, and `.env` are all gitignored — restore or rebuild them (§5).

---

## 3. Architecture

```
pulse/
├── start.py                         local launcher
├── Dockerfile · docker-compose.yml · .dockerignore · deploy/   Phase 3.D deployment
├── Data/                            3.5 GB desk feed (gitignored) + parquet/ (DuckDB)
├── backend/
│   ├── app.py                       Flask API: routes + APScheduler (scheduler.start only in __main__)
│   ├── wsgi.py                      gunicorn entry — starts scheduler + warm-up (MUST be --workers 1)
│   ├── data_lake.py                 /Data loaders via DuckDB/parquet
│   ├── paper_trading.py             SQLite paper book + 60s MTM (WAL pragmas)
│   ├── db/cache.py                  SQLite TTL cache (WAL pragmas) → pulse_cache.db
│   ├── fetchers/                    ~30 data-source modules
│   ├── models/                      fair value · signal engine · trade idea · patterns
│   ├── research/                    Phase 2 regime engine (table below)
│   └── schemas/                     Pydantic response models → generated frontend types
└── frontend/                        React + Vite (builds into backend/static)
```

**`backend/research/` — the regime engine:**

| File | Role |
|---|---|
| `regimes.py` | composite 27-cell + pooled 3-cell curve grids |
| `spread_universe.py` | 6 instruments + outright-leg decomposition |
| `features.py` | point-in-time feature matrix (22 features: curve, COT, cracks, macro, …) |
| `models.py` | 7-model per-cell competition + quantile bands |
| `live_ranker.py` | classify → predict → rank; **applies the tuned exit rule** (TP/SL/time-stop) |
| `walkforward.py` | expanding-window backtest; writes trade tapes + `walkforward_report.json` |
| `exit_sim.py` · `exit_tuning.py` · `exit_robustness.py` | TP/SL simulator · tuning sweep · OOS robustness |
| `ab_test.py` | pooled-vs-gated live A/B harness |
| `methodology_pdf.py` | mentor-facing PDF |

---

## 4. API · Env · Data

**API (37 endpoints).** Groups: health · prices/charts · models · fundamentals · news/intel ·
risk/structure · paper trading (`/api/paper/*`) · **regime engine** (`/api/regime`,
`/api/regime/recommendation`, `/api/regime/backtest`, `/api/regime/drill/<spread>`,
`/api/regime/walkforward`, `/api/regime/ab[/tick|/reset]`) · RAG (`/api/ask`).
*New endpoint pattern:* add a Pydantic model in `backend/schemas/` → register it → return via
`respond(...)` → run `python scripts/generate_ts_types.py`.

**Env keys (`.env`, gitignored).** `EIA_API_KEY`, `FRED_API_KEY`, `GROQ_API_KEY`, `NEWSAPI_KEY`,
`MARKETAUX_KEY`, `APIFY_API_TOKEN`, `AISSTREAM_API_KEY`, `SENTRY_DSN`/`VITE_SENTRY_DSN`,
`BETTER_STACK_TOKEN`. Optional regime flags: `PULSE_REGIME_MODE=pooled`, `PULSE_GATED_BLEND=1`,
`PULSE_GATED_SIZE=full|half|kelly`, `PULSE_AB_TEST_DISABLED=1`.

**/Data lake.** Brent C1-C31 daily settlements (real); WTI C1-C6 (synth from 1-min mids → flagged
ESTIMATE via `data_lake.get_wti_settlements()`); 1-min mids (Brent/WTI/HO/Gasoil); spread/OHLCV xlsx.
Converted to `Data/parquet/` for DuckDB. Research caches (COT, FRED/external, crude stocks) live in
`backend/data/research/`.

---

## 5. Gotchas (load-bearing)

**Dev loop**
1. Frontend edits don't show until `npm run build` (app serves `backend/static/`). Use `npm run dev` for HMR.
2. Two python processes on :5000 = stale code running — `taskkill /F /PID` both before restarting.
3. Never edit `frontend/src/**/*.tsx` via PowerShell (mangles multibyte chars) — use the Read/Edit tools.
4. Run the walk-forward with `python -u`; it writes the report *before* the final summary print, which
   trips cp1252 on the `μ` glyph (cosmetic only).

**Fresh-machine setup** (everything below is gitignored — restore or rebuild)
5. `.env` must be named `.env` (not `env`). Needs `xlrd` for COT `.xls`; if `external_history.parquet`
   is missing FRED columns, rebuild with `python -m backend.research.external_history`.
6. Model pkls (`backend/data/research/models*/`) — copy from another machine or rebuild via
   `python -m backend.research.models --mode composite|pooled`.

**Regime-engine invariants** (the mirrors `test_invariants.py` should assert)
7. **Gate rule** is mirrored: `live_ranker._pooled_passes_gate` ↔ `walkforward._pooled_passes_gate`
   (`GATED_WINNERS`, `GATED_Z_THRESHOLD`, `ROLLING_WIN` must match bit-for-bit).
8. **Tuned exit rule** lives in `live_ranker.py` (TP/SL frac + excluded spreads) **and** `paper_trading.py`
   (`TUNED_MAX_HOLD_TRADING_DAYS` mirrors `live_ranker.TUNED_MAX_HOLD_DAYS`). The walk-forward deliberately
   still trades all 6 spreads at p50/1.5σ/20d — **do not** fold the exit rule into it (separate layers).
9. A/B cost table `ab_test.COST_PER_SPREAD_RT` mirrors `walkforward.COST_PER_SPREAD_RT`.
10. Composite regime labels contain `/` → `models._safe()` maps it to `-` for pkl filenames.
11. WTI settlements are synth/ESTIMATE — swap in a real daily file inside `data_lake.get_wti_settlements()`.

**Deployment (Phase 3.D)**
12. gunicorn MUST stay `--workers 1` (scheduler must be singular) and **no `--preload`** (APScheduler
    threads don't survive `fork()`); the scheduler starts in `wsgi.py`, not app.py's `__main__`.
13. `backend/db` bind-mount must be writable by the container uid (`PULSE_UID=$(id -u)` or chown 10001).
    The app is internal-only behind Caddy; basic auth gates everything except `/api/health`.

---

## 6. Conventions

- **One sprint per session** — read this file, do the sprint, update §1, stop. Don't multitask sprints.
  *(Full session rules + a copy-paste prompt for every pending task live in [`docs/ROADMAP.md`](docs/ROADMAP.md).)*
- **Honesty over polish** — every number traces to a named source; stale data shown as stale; report
  failures plainly (the walk-forward & robustness verdicts are deliberately graded, not spun).
- **Interpretability over R²** (mentor mandate) · **type safety on the backend↔frontend seam**
  (Pydantic → generated TS) · **ship narrow, then broaden**.
- **Git:** branch off `main`, PR back. Last shipped: PR #3 (Phase 2 engine). `main` is the default branch.
- **End-of-turn footer** (when a sprint ships): one line recommending *continue here* vs *new chat*, plus a
  ready-to-paste prompt for the next task.

---

*Deep-cleaned 2026-06-14: history moved to `docs/PHASE_HISTORY.md`; dead docs removed; tree committed on a clean branch.*
