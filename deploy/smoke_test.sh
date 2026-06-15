#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# PULSE — Phase 3.D post-deploy smoke test (Task 4 acceptance)
#
# Verifies the always-on deployment:
#   1. /api/health answers (unauthenticated liveness)
#   2. a manual A/B tick fires (authenticated)
#   3. the A/B paper book is accumulating under the tuned exit rule
#
# Usage:
#   PULSE_USER=mentor PULSE_PASS='your-pw' BASE=https://pulse.example.com ./deploy/smoke_test.sh
#   PULSE_USER=mentor PULSE_PASS='your-pw' BASE=http://<host-ip>          ./deploy/smoke_test.sh
#
# Needs: curl + python3 (both present on the host).
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

: "${BASE:?set BASE, e.g. https://pulse.example.com or http://<host-ip>}"
: "${PULSE_USER:?set PULSE_USER (basic-auth user, e.g. mentor)}"
: "${PULSE_PASS:?set PULSE_PASS (basic-auth password)}"

BASE="${BASE%/}"   # strip any trailing slash
pass=0; fail=0
ok()  { echo "  PASS  $1"; pass=$((pass+1)); }
bad() { echo "  FAIL  $1"; fail=$((fail+1)); }

echo "== 1. health (unauthenticated) =="
code=$(curl -sS -o /tmp/pulse_health.json -w '%{http_code}' "$BASE/api/health" || echo 000)
if [ "$code" = "200" ] && grep -q '"status"' /tmp/pulse_health.json && grep -q 'ok' /tmp/pulse_health.json; then
  ok "/api/health -> 200 status:ok"
  cat /tmp/pulse_health.json; echo
else
  bad "/api/health (http $code)"
  cat /tmp/pulse_health.json 2>/dev/null || true; echo
fi

echo "== 2. fire one A/B tick (authenticated POST) =="
code=$(curl -sS -u "$PULSE_USER:$PULSE_PASS" -X POST -H 'Content-Type: application/json' -d '{}' \
  -o /tmp/pulse_tick.json -w '%{http_code}' "$BASE/api/regime/ab/tick" || echo 000)
if [ "$code" = "200" ]; then
  ok "/api/regime/ab/tick -> 200 (pushed, or 'already_open' if today's tick already ran)"
  python3 -m json.tool /tmp/pulse_tick.json 2>/dev/null || cat /tmp/pulse_tick.json
  echo
else
  bad "/api/regime/ab/tick (http $code) — check basic-auth creds + that pulse is (healthy)"
  cat /tmp/pulse_tick.json 2>/dev/null || true; echo
fi

echo "== 3. A/B report — is the tuned-rule book accumulating? =="
code=$(curl -sS -u "$PULSE_USER:$PULSE_PASS" -o /tmp/pulse_ab.json -w '%{http_code}' "$BASE/api/regime/ab" || echo 000)
if [ "$code" != "200" ]; then
  bad "/api/regime/ab (http $code)"
  cat /tmp/pulse_ab.json 2>/dev/null || true; echo
elif python3 - <<'PY'
import json, sys
d = json.load(open('/tmp/pulse_ab.json'))
# Walk the whole envelope so this is robust to nesting (data/arms/pooled/gated).
def walk(o, f):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ('verdict', 'n_open', 'n_closed', 'hit', 'sharpe_net'):
                f.setdefault(k, []).append(v)
            walk(v, f)
    elif isinstance(o, list):
        for x in o:
            walk(x, f)
    return f
f = walk(d, {})
opens  = [x for x in f.get('n_open',   []) if isinstance(x, (int, float))]
closes = [x for x in f.get('n_closed', []) if isinstance(x, (int, float))]
print("  verdict :", f.get('verdict'))
print("  n_open  :", opens, "max =", max(opens)  if opens  else 0)
print("  n_closed:", closes, "max =", max(closes) if closes else 0)
print("  hit     :", f.get('hit'))
# PASS when at least one arm holds or has closed a trade — the book is live.
sys.exit(0 if (opens and max(opens) >= 1) or (closes and max(closes) >= 1) else 3)
PY
then
  ok "A/B book is accumulating (>=1 open or closed trade under the tuned rule)"
else
  bad "A/B book still empty — the first auto-tick is 5 min after boot; wait, then re-run (or POST the tick again)"
fi

echo
echo "==== smoke test: $pass passed, $fail failed ===="
[ "$fail" -eq 0 ]
