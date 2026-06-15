# PULSE on Hugging Face Spaces — deploy runbook (Phase 3.E)

A **free, no-card** always-on deployment: a public dashboard link whose A/B paper
book accumulates 24/7. Free HF Spaces have ephemeral storage and sleep after
~48 h idle, so this setup adds two things to make it a *real* accumulator:

- the parquet **data lake** is hosted in a private HF **Dataset** and baked into
  the image at build time;
- the SQLite **paper book** is synced to that same Dataset at runtime
  (`backend/hf_persist.py` — pull on boot, push every 2 h + at exit);
- an external **keep-alive** ping defeats the 48 h idle-sleep.

```
GitHub (public repo)                HF Dataset  <username>/pulse-data  (private)
   │  shallow clone @ main             ├── parquet/*.parquet   ← baked into image @ build
   ▼                                   └── db/pulse_cache.db   ← synced @ runtime
HF Space  <username>/pulse  (Docker) ──┘
   ▲  external cron pings /api/health every few minutes (keep-alive)
```

---

## 0. Prerequisites (you do these once — they need your account)

1. A Hugging Face account — https://huggingface.co/join (email + password, **no card**).
2. A **write** token — https://huggingface.co/settings/tokens → *New token* → role
   **Write**. Copy it (looks like `hf_…`). Used to push data + the Space and to
   sync the book.
3. Locally: `pip install huggingface-hub` (already in `requirements.txt`).

> Replace `<username>` below with your HF username throughout.

---

## 1. Seed the private Dataset (parquet lake + paper book)

From the repo root, with `/Data` present:

```bash
python deploy/hf_space/upload_data.py --repo <username>/pulse-data --token hf_xxx
```

This creates the private dataset `<username>/pulse-data` and uploads
`Data/parquet/` (~534 MB) plus the current `pulse_cache.db` as a seed. The
parquet upload is bandwidth-bound — expect several minutes on a home connection.

---

## 2. Create the Space and push its two files

The Space repo contains only `deploy/hf_space/Dockerfile` + `README.md`; the
Dockerfile pulls everything else from GitHub + the Dataset at build time.

```bash
# log in once (paste the write token)
huggingface-cli login

# create an empty Docker Space
huggingface-cli repo create pulse --type space --space_sdk docker -y

# stamp your dataset repo into the Dockerfile, then push README + Dockerfile
#   (the Dockerfile defaults ARG HF_DATASET_REPO=USERNAME/pulse-data)
huggingface-cli upload <username>/pulse deploy/hf_space/README.md README.md --repo-type space
huggingface-cli upload <username>/pulse deploy/hf_space/Dockerfile Dockerfile --repo-type space
```

> If `huggingface-cli upload` of the Dockerfile keeps `USERNAME/pulse-data`, set
> `HF_DATASET_REPO` as a Space **variable** (step 3) — the runtime reads it from
> env, and you can also override the build ARG in the Space's build settings.

---

## 3. Configure secrets + variables (Space → Settings → *Variables and secrets*)

| Kind | Name | Value |
|---|---|---|
| **Secret** | `HF_TOKEN` | your write token (build pulls data; runtime syncs the book) |
| **Variable** | `HF_DATASET_REPO` | `<username>/pulse-data` |
| **Secret** | `EIA_API_KEY` | from `.env` |
| **Secret** | `FRED_API_KEY` | from `.env` |
| **Secret** | `GROQ_API_KEY` | from `.env` (morning brief / RAG) |
| **Secret** | `NEWSAPI_KEY` | from `.env` |
| **Secret** | `MARKETAUX_KEY` | from `.env` |
| **Secret** | `APIFY_API_TOKEN` | from `.env` (optional — NewsAPI fallback) |
| **Secret** | `AISSTREAM_API_KEY` | from `.env` (optional — tanker watch) |
| **Secret** | `BLS_API_KEY` | from `.env` (optional) |

`SENTRY_*` / `BETTER_STACK_*` are optional. Saving secrets triggers a rebuild.

---

## 4. Keep-alive (defeat the 48 h idle-sleep)

Free Spaces sleep after ~48 h with no HTTP traffic; the internal scheduler does
**not** count as traffic. Add an external ping to `…/api/health` (exempt from any
auth, cheap):

- **UptimeRobot** (free, no card) — https://uptimerobot.com → *Add monitor* →
  HTTP(s) → URL `https://<username>-pulse.hf.space/api/health` → interval 5 min.

This doubles as an uptime dashboard.

---

## 5. Verify

- Space **Logs** tab → build succeeds, then:
  - `baked parquet:` lists the parquet files (build),
  - `hf_persist: restored paper book from <username>/pulse-data` *or* `…starting fresh`,
  - `APScheduler started under gunicorn … daily A/B tick active`.
- Open `https://<username>-pulse.hf.space` → dashboard loads.
- `https://<username>-pulse.hf.space/api/health` → `{"status":"ok",…}`.
- `…/api/regime/ab` → the A/B arms render.
- After a restart (Settings → *Restart*), confirm the book persisted:
  `…/api/regime/ab` should show the same `days_elapsed` / trade counts, not zeros.

---

## 6. Updating the deployment

- **Code changes:** merge to `main` on GitHub, then **Factory rebuild** the Space
  (it shallow-clones the latest `main`).
- **New/refreshed data:** re-run `upload_data.py`, then rebuild.
- **Force a book sync now:** restart the Space (atexit pushes) or wait for the 2 h timer.

---

## 7. Gotchas

1. **`--workers 1`, no `--preload`** — the scheduler must be singular and
   APScheduler threads don't survive `fork()` (mirrors the Oracle/compose deploy).
   Don't raise the worker count.
2. **First boot has no book** — `hf_persist.pull_db()` logs "starting fresh"; the
   first push (≤2 h later, or on restart) seeds `db/pulse_cache.db` in the Dataset.
3. **`HF_TOKEN` is build *and* runtime** — build uses it as a mounted secret to
   pull parquet; runtime reads it from env to sync the book. Same write token.
4. **Token scope** — a *write* token is required (it commits the book to the
   Dataset). A read token will fail the runtime push.
5. **Ephemeral disk** — anything not in the image or the Dataset is lost on
   restart. Only the paper book is stateful, and it's synced; everything else
   (cache, logs) is rebuildable.
6. **`app_port: 7860`** in `README.md` must match the gunicorn bind + `EXPOSE`.
