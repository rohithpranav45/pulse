# PULSE — Phase 3.D always-on deployment runbook

Goal: run PULSE 24/7 on a cheap/free always-on host so the daily APScheduler
A/B tick accumulates the **tuned-rule** paper book (Phase 2.9.2 exit rule) and
`/api/regime/ab` shows the live win rate climbing — the forward-validation
proof the mentor asked for.

Architecture:

```
internet ──▶ Caddy (:80/:443, basic auth + auto-HTTPS) ──▶ pulse (:5000, internal)
                                                              │  gunicorn -w1 -t8
                                                              │  wsgi:app → APScheduler
                                                              ▼
                                          bind mounts:  ./Data (ro-ish)
                                                        ./backend/db  (the book, RW)
                                                        ./backend/data/research (models, ro)
```

`pulse` is **not** published to the host — Caddy is the only public port, so the
basic-auth gate cannot be bypassed. The APScheduler (data refresh + 60 s paper
MTM + daily A/B tick) runs inside the single gunicorn worker; see
`backend/wsgi.py` for why it must stay `--workers 1`.

---

## 0. What you need

- An always-on Linux host with Docker + the Compose plugin. Two good options:
  - **Oracle Cloud Always Free** — 4-core ARM (Ampere A1), 24 GB RAM, $0 forever.
    Preferred. Section 1A.
  - **A small VPS** (Hetzner CX22 ~€4/mo, DigitalOcean/Vultr $5/mo, x86). Section 1B.
- The repo, the `/Data` lake, the trained model pkls, and a real `.env`
  (all four are gitignored, so they must be copied to the host — section 2).
- (Optional, for HTTPS) a domain or a free `*.duckdns.org` name — section 4.

> **ARM note (Oracle):** all Python deps in `requirements.txt` ship `aarch64`
> manylinux wheels (numpy/pandas/scipy/torch-cpu/xgboost/lightgbm/catboost), so
> the image builds natively on Ampere. Model pkls are architecture-independent
> (pickled Python objects), so the pkls trained on the Windows desk load fine on
> ARM as long as the library versions match `requirements.txt`.

---

## 1A. Provision — Oracle Cloud Always Free (ARM)

1. Console → **Compute → Instances → Create**. Image **Canonical Ubuntu 22.04**,
   shape **VM.Standard.A1.Flex** (set 2–4 OCPU / 12–24 GB — all within Always
   Free). Add your SSH public key. Create.
2. **Open the firewall — this is the #1 Oracle gotcha (TWO layers):**
   - **VCN security list:** Networking → VCN → its Security List → add Ingress
     rules: source `0.0.0.0/0`, TCP **80** and **443**.
   - **Host iptables** (Oracle Ubuntu images block everything but SSH by default):
     ```bash
     sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80  -j ACCEPT
     sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
     sudo netfilter-persistent save        # persist across reboot
     ```
3. Install Docker:
   ```bash
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker $USER && newgrp docker   # run docker without sudo
   ```

## 1B. Provision — generic VPS (x86)

Same as above minus the Oracle iptables dance (most VPS images allow 80/443 by
default; if not, open them in the provider's firewall panel). Install Docker
with the same `get.docker.com` one-liner.

---

## 2. Get the code + data + secrets onto the host

```bash
# code
git clone https://github.com/rohithpranav45/pulse.git
cd pulse

# secrets — copy your working .env from the desk (NEVER commit it)
scp youruser@desk:/path/to/pulse/.env  ./.env

# the 3.5 GB lake + the gitignored model pkls + research reports.
# rsync is resumable; -z compresses in flight.
rsync -avz youruser@desk:/path/to/pulse/Data/                  ./Data/
rsync -avz youruser@desk:/path/to/pulse/backend/data/research/ ./backend/data/research/
```

> **Minimal-bandwidth variant:** the A/B book itself only needs
> `Data/LCO_Brent_daily_settlement_c1_to_c31_2016_2026.csv`,
> `Data/parquet/`, and `backend/data/research/` (models + the cot/external/
> inventory parquets + `walkforward_report.json`). Copy the full `Data/` only
> if you want every dashboard panel to render.

---

## 3. Configure `.env` for the deployment

Append to the `.env` you copied:

```bash
# ── Caddy basic auth (required — the site won't serve without a hash) ─────────
BASIC_AUTH_USER=mentor
# generate the bcrypt hash (raw hash, NO escaping needed — env_file passes it literally):
#   docker run --rm caddy:2.8-alpine caddy hash-password --plaintext 'choose-a-strong-pw'
BASIC_AUTH_HASH=<paste the $2a$... hash here>

# ── HTTPS (optional) ──────────────────────────────────────────────────────────
# Set to a domain pointing at this host's public IP → Caddy auto-issues a
# Let's Encrypt cert. Leave UNSET for HTTP-only (IP access, browser warning).
# PULSE_DOMAIN=pulse.example.com

# ── Bind-mount ownership (recommended — avoids a chown) ───────────────────────
# Run the container as your host user so it can write ./backend/db with no chown.
# On the host:  echo "PULSE_UID=$(id -u)"; echo "PULSE_GID=$(id -g)"
PULSE_UID=1000
PULSE_GID=1000
```

The A/B harness is **enabled by default** (there is no `PULSE_AB_TEST_DISABLED`
in `.env`), so the daily tick will run. The Phase 2.9.2 tuned exit rule is
always-on in `live_ranker.py` + `paper_trading.py`, so every A/B trade closes
under TP-halfway-to-fair / 2.5σ / 30-day time-stop with the M3-M6 laggards
dropped — exactly the rule whose live win rate we want to prove.

**Bind-mount permissions** — pick ONE:
- *Recommended:* set `PULSE_UID`/`PULSE_GID` as above (container runs as you).
- *Or* keep the image's uid and chown the writable dir once:
  `sudo chown -R 10001:10001 backend/db`

---

## 4. (Optional) DNS for HTTPS

- **Own a domain:** add an `A` record `pulse.<domain> → <host public IP>`, set
  `PULSE_DOMAIN=pulse.<domain>` in `.env`.
- **Zero-cost:** create a free name at <https://www.duckdns.org>, point it at the
  host IP, set `PULSE_DOMAIN=<name>.duckdns.org`. Caddy's HTTP-01 challenge works
  over port 80 as long as the name resolves to the host.
- **No domain:** leave `PULSE_DOMAIN` unset — Caddy serves HTTP on `:80`
  (`http://<host-ip>/`, browser will not show a padlock). Still basic-auth gated.

---

## 5. Launch

```bash
docker compose up -d --build      # first run builds the image (~5–10 min on ARM)
docker compose ps                 # both services Up; pulse shows (healthy)
docker compose logs -f pulse      # watch warm-up + "APScheduler started under gunicorn"
```

> If the frontend build stage fails on `npm ci` with a lockfile-mismatch error,
> run `npm install` in `frontend/` on the desk and commit the refreshed
> `package-lock.json`, then rebuild.

The pulse container reports `(healthy)` once `/api/health` answers (after the
~60–120 s cold warm-up). Caddy waits for that before starting (compose
`depends_on: service_healthy`).

---

## 6. Verify (Task 4 acceptance)

Run the smoke test from anywhere (it needs the basic-auth creds):

```bash
PULSE_USER=mentor PULSE_PASS='your-pw' BASE=https://pulse.example.com ./deploy/smoke_test.sh
# HTTP-only host:  PULSE_USER=mentor PULSE_PASS='your-pw' BASE=http://<host-ip> ./deploy/smoke_test.sh
```

It checks, in order:
1. `GET /api/health` (no auth) → `status: ok`.
2. `POST /api/regime/ab/tick` (auth) → fires one A/B generation immediately
   (don't wait 5 min for the scheduled tick). Reports pooled/gated pushes (or
   `already_open` if the scheduled tick already ran today — both mean the book
   is live).
3. `GET /api/regime/ab` (auth) → prints the verdict + per-arm `n_open`/`n_closed`
   and NET win rate. **Acceptance: at least one arm shows `n_open ≥ 1`** the
   first day; the win rate populates as trades close under the tuned rule.

The unattended daily proof: the scheduler fires `_ab_tick` **5 minutes after
boot, then every 24 h**. Re-run step 3 over the following days — `n_closed` and
the NET win rate on both arms should climb. That live, climbing win rate is the
Phase 3.D deliverable.

Manual peek without the script:
```bash
curl -fsS https://pulse.example.com/api/health
curl -fsS -u mentor:'your-pw' https://pulse.example.com/api/regime/ab | python3 -m json.tool
```

---

## 7. Restart / operate runbook

| Task | Command |
|---|---|
| Restart the app | `docker compose restart pulse` |
| Apply a code update | `git pull && docker compose up -d --build` |
| Tail app logs | `docker compose logs -f pulse` |
| Tail proxy logs | `docker compose logs -f caddy` |
| Fire an A/B tick now | `curl -fsS -u mentor:PW -X POST https://DOMAIN/api/regime/ab/tick` |
| Read the A/B report | `curl -fsS -u mentor:PW https://DOMAIN/api/regime/ab` |
| Reset the A/B book | `curl -fsS -u mentor:PW -X POST https://DOMAIN/api/regime/ab/reset` |
| Stop everything | `docker compose down` (volumes/cert survive) |
| Full reset incl. certs | `docker compose down -v` |
| Rotate the password | regenerate `BASIC_AUTH_HASH`, `docker compose up -d caddy` |

The host survives reboots: `restart: unless-stopped` brings both containers back,
and the SQLite book (WAL, on the bind mount) plus the issued cert (in the
`caddy_data` volume) persist.

---

## 8. Gotchas (read before debugging)

1. **`--workers 1` is mandatory.** The scheduler must be singular or the daily
   tick / MTM / refresh fire once per worker. The Dockerfile hard-codes it.
2. **bcrypt hash needs NO escaping here.** It's passed via `env_file` (literal),
   not compose `${}` interpolation — so the `$` chars are safe as-is. (If you
   ever switch to `environment: ${BASIC_AUTH_HASH}`, you'd have to escape each
   `$` as `$$`. Don't — use env_file.)
3. **`backend/db` must be writable by the container uid.** This is the book.
   Use `PULSE_UID=$(id -u)` (section 3) or `chown -R 10001:10001 backend/db`.
4. **Parquet cache.** The image does not pre-build `Data/parquet/`. Copy it from
   the desk (it's in the rsync). If absent, `data_lake` falls back to CSV (slower
   first query) and regenerates the WTI synth parquet on demand (needs `Data/`
   writable — it's mounted RW).
5. **Image size.** torch + the three boosters make the image large (~3–4 GB on
   x86 with CUDA torch; smaller on ARM, which is CPU-only). To shrink x86,
   uncomment the CPU-torch `--extra-index-url` in the Dockerfile (see the note
   there). Oracle's 50 GB boot volume has ample room either way.
6. **`/api/health` is intentionally unauthenticated** so an uptime monitor
   (e.g. Better Stack) can probe it. It returns only `{status, timestamp}` — no
   market data. Everything else is gated.
7. **First A/B tick is 5 min after boot**, not instant — APScheduler waits so the
   data lake + regime models warm up before generating signals. Use
   `POST /api/regime/ab/tick` to force one immediately for verification.
