# syntax=docker/dockerfile:1
# ─────────────────────────────────────────────────────────────────────────────
# PULSE — Energy Intelligence Terminal · Phase 3.D always-on deployment image
#
# Multi-stage:
#   1. frontend  — node builds the React/Vite bundle into backend/static
#   2. runtime   — python:3.13-slim, deps installed with uv, served by gunicorn
#
# Build:  docker build -t pulse:latest .
# Run:    docker compose up -d   (see docker-compose.yml + deploy/README.md)
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: build the React frontend ────────────────────────────────────────
FROM node:22-slim AS frontend
WORKDIR /build/frontend

# Install deps first so the npm layer caches on package.json/lock changes only.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# vite.config.ts builds to ../backend/static (emptyOutDir), i.e. /build/backend/static.
COPY frontend/ ./
RUN npm run build


# ── Stage 2: python runtime ───────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

# uv: fast, reproducible installer (copied from the official distroless image).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Runtime system libs:
#   libgomp1 — OpenMP runtime required by xgboost / lightgbm / catboost wheels
#   curl     — used by the container HEALTHCHECK below
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=5000

WORKDIR /app

# Install Python deps + gunicorn into the system interpreter. Cached on
# requirements.txt alone so source edits don't re-trigger the (heavy) install.
#
# NOTE on image size: on linux/amd64 the default PyPI torch wheel bundles CUDA
# (~2 GB). On linux/arm64 (Oracle Always-Free) PyPI torch is already CPU-only.
# To force the smaller CPU build on x86 hosts, append to the install line:
#     --extra-index-url https://download.pytorch.org/whl/cpu
# (torch==2.11.0 matches 2.11.0+cpu per PEP 440.) Left off by default so the
# build resolves identically on both architectures.
COPY requirements.txt ./
RUN uv pip install --system --no-cache -r requirements.txt gunicorn==23.0.0

# App source + the frontend bundle from stage 1.
COPY backend/ ./backend/
COPY --from=frontend /build/backend/static ./backend/static

# Non-root user. The two writable mount points are pre-created + owned so a plain
# `docker run` works; under compose these are bind-mounted — see deploy/README.md
# for the one-time host chown so uid 10001 can write the book.
RUN useradd --create-home --uid 10001 pulse \
    && mkdir -p /app/backend/db /app/backend/data/research \
    && chown -R pulse:pulse /app
USER pulse

EXPOSE 5000

# Liveness on the public health endpoint. start-period covers the cold import of
# torch/models + the ~60 s cache warm-up before failures count against retries.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD curl -fsS http://127.0.0.1:5000/api/health || exit 1

# gunicorn loads backend/wsgi.py, which starts the APScheduler (data refresh +
# 60 s paper MTM + daily A/B tick) and the cache warm-up.
#   --workers 1  : the scheduler MUST be singular (see wsgi.py docstring)
#   --threads 8  : request concurrency for this I/O-bound app
#   no --preload : APScheduler threads must start in the worker, not the master
CMD ["gunicorn", "--chdir", "/app/backend", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "1", "--threads", "8", \
     "--timeout", "120", "--graceful-timeout", "30", \
     "--access-logfile", "-", "--error-logfile", "-", \
     "wsgi:app"]
