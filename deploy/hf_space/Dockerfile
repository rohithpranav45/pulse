# syntax=docker/dockerfile:1
# ─────────────────────────────────────────────────────────────────────────────
# PULSE — Hugging Face Space (Docker SDK) build · Phase 3.E
#
# Self-contained: this is the ONLY app file in the Space repo. The build
#   1. shallow-clones the public GitHub repo (latest main),
#   2. builds the React bundle + installs Python deps,
#   3. bakes the parquet data lake from a private HF Dataset (build secret), and
#   4. serves gunicorn on the HF app port (7860) with the scheduler running.
#
# The SQLite paper book is synced to the same Dataset at runtime by
# backend/hf_persist.py so it survives HF's ephemeral storage.
#
# Configure in the Space (Settings → Variables and secrets):
#   secret   HF_TOKEN          — HF write token (build + runtime)
#   variable HF_DATASET_REPO   — e.g. your-username/pulse-data
#   secret   EIA_API_KEY, FRED_API_KEY, GROQ_API_KEY, …  (from your .env)
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: clone repo + build the React frontend ───────────────────────────
FROM node:22-slim AS frontend
# ca-certificates is required for git to verify GitHub's TLS cert (node:22-slim
# ships without it, and --no-install-recommends won't pull it in via git).
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
ARG PULSE_REPO=https://github.com/rohithpranav45/pulse
ARG PULSE_REF=main
# Shallow clone — depth 1 skips the (large) history; tracked working tree is small.
RUN git clone --depth 1 --branch ${PULSE_REF} ${PULSE_REPO} .
WORKDIR /build/frontend
RUN npm ci && npm run build
# vite builds into ../backend/static, i.e. /build/backend/static


# ── Stage 2: python runtime ───────────────────────────────────────────────────
FROM python:3.13-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# libgomp1 — OpenMP for xgboost/lightgbm/catboost · curl — healthcheck
# ca-certificates — TLS verification for the runtime parquet/book sync to HF
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=7860 \
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

# App source + built bundle from the clone (includes backend/, requirements.txt,
# and the versioned regime model pkls under backend/data/research/).
COPY --from=frontend /build/backend ./backend
COPY --from=frontend /build/requirements.txt ./requirements.txt

# Python deps (requirements.txt now includes huggingface-hub) + gunicorn.
RUN uv pip install --system --no-cache -r requirements.txt gunicorn==23.0.0

# Bake the parquet data lake into the image from the private HF Dataset. The
# token is mounted as a build secret (never baked into a layer). data_lake.py
# expects it at /app/Data/parquet.
ARG HF_DATASET_REPO=USERNAME/pulse-data
# `hf` is the current CLI (huggingface-cli is deprecated in hub 1.x). It reads
# the token from the HF_TOKEN env var, set here from the mounted build secret.
RUN --mount=type=secret,id=HF_TOKEN,required=true \
    HF_TOKEN="$(cat /run/secrets/HF_TOKEN)" \
    hf download "${HF_DATASET_REPO}" --repo-type dataset \
        --include "parquet/*" --local-dir /app/Data \
    && echo "baked parquet:" && ls -1 /app/Data/parquet | head

# Train the production "global" regime model artifacts (Phase 4 — see
# backend/research/models_global.py). The model_global pkls are gitignored
# locally per the existing models* pattern, so we train them here at build
# time. Takes ~30 seconds on HF's CPU and writes to
# /app/backend/data/research/models_global/.
RUN cd /app/backend && python -m research.models_global

# HF Spaces run the container as uid 1000. Make the writable paths owned by it:
#   backend/db        — the SQLite paper book (pulled/pushed by hf_persist)
#   .cache/huggingface — hf_hub_download cache for the runtime book sync
RUN useradd --create-home --uid 1000 user \
    && mkdir -p /app/backend/db /app/.cache/huggingface \
    && chown -R user:user /app
USER user

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
    CMD curl -fsS http://127.0.0.1:7860/api/health || exit 1

# --workers 1 (scheduler must be singular) · no --preload (APScheduler threads
# don't survive fork()). wsgi.py restores the paper book before the app opens it.
CMD ["gunicorn", "--chdir", "/app/backend", \
     "--bind", "0.0.0.0:7860", \
     "--workers", "1", "--threads", "8", \
     "--timeout", "120", "--graceful-timeout", "30", \
     "--access-logfile", "-", "--error-logfile", "-", \
     "wsgi:app"]
