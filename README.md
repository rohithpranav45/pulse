# PULSE — Energy Intelligence Terminal

A live energy-trading dashboard built for a Futures First internship: it ingests ~35 data
sources, runs quant models (fair value + a regime-conditional spread/butterfly engine), and
serves a React dashboard with a paper-trading book.

## Quick start

```bash
python start.py        # serves the dashboard at http://127.0.0.1:5000
```

A fresh machine also needs the gitignored `/Data` feed, the model pkls, and `.env`
(see [CLAUDE.md](CLAUDE.md) §2 + §5 for restore/rebuild steps).

## Where to look

| Doc | Purpose |
|---|---|
| **[CLAUDE.md](CLAUDE.md)** | **Present** — current state, how to run, architecture, gotchas. **Start here.** |
| [docs/ROADMAP.md](docs/ROADMAP.md) | **Future** — pending tasks, timeline, copy-paste session prompts |
| [docs/PHASE_HISTORY.md](docs/PHASE_HISTORY.md) | **Past** — full sprint-by-sprint log |
| [deploy/README.md](deploy/README.md) | Always-on deployment runbook (Docker + Caddy) |

## Stack

Flask 3 · React 18 + Vite + Tailwind · SQLite (cache + paper book) · DuckDB/Parquet over a
3.5 GB `/Data` desk feed · sklearn + XGBoost / LightGBM / CatBoost.
