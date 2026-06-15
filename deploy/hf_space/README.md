---
title: PULSE Energy Terminal
emoji: 🛢️
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: Live energy-trading dashboard + regime engine + paper book
---

# PULSE — Energy Intelligence Terminal

Live energy-trading dashboard: ~35 data sources, a regime-conditional spread
engine, and a tuned-rule paper-trading book running a live pooled-vs-gated A/B
test. Built for the Futures First internship.

- **Source:** https://github.com/rohithpranav45/pulse
- **Stack:** Flask · React + Vite · SQLite · DuckDB/Parquet · sklearn + XGB/LGBM/CatBoost

## How this Space is built

This Space's `Dockerfile` is self-contained:

1. Shallow-clones the **public** GitHub repo (latest `main`) — so a rebuild always
   ships the newest code; nothing is duplicated here.
2. Builds the React bundle and installs the Python deps.
3. Bakes the ~534 MB parquet **data lake** into the image, downloaded at build
   time from a private HF **Dataset** (`HF_DATASET_REPO`) using the `HF_TOKEN`
   build secret.
4. Runs gunicorn (`--workers 1`, no `--preload`) so the APScheduler stays
   singular — data refresh, the 60 s paper MTM, and the **daily A/B tick**.

Because free Spaces have ephemeral storage, the SQLite **paper book** is synced
to the same private Dataset by `backend/hf_persist.py` (pull on boot, push every
2 h + at exit) so the A/B book survives restarts.

## Configuration (Settings → Variables and secrets)

| Kind | Name | Value |
|---|---|---|
| Secret | `HF_TOKEN` | a HF **write** token (used at build to pull data, at runtime to sync the book) |
| Variable | `HF_DATASET_REPO` | `<your-username>/pulse-data` |
| Secret | `EIA_API_KEY`, `FRED_API_KEY`, `GROQ_API_KEY`, `NEWSAPI_KEY`, `MARKETAUX_KEY`, `APIFY_API_TOKEN`, `AISSTREAM_API_KEY`, … | from your local `.env` |

See `deploy/HF_DEPLOY.md` in the repo for the full runbook.
