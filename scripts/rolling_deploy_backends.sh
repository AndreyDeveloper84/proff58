#!/usr/bin/env bash
# DRF-2972: zero/near-zero-downtime rolling replacement for Django backends.
#
# Preconditions:
# - backend image already built as proff58-backend:latest;
# - docker/release.sh already completed backup + migrations;
# - current stack nginx/web may be serving the previous release.
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
compose="docker compose -f $COMPOSE_FILE"

retry() {
  local n=1 max=3 delay=15
  until "$@"; do
    if [ "$n" -ge "$max" ]; then
      echo "ERROR: failed after $max attempts: $*" >&2
      return 1
    fi
    echo "WARN: attempt $n/$max failed; retry in ${delay}s" >&2
    sleep "$delay"
    n=$((n + 1))
    delay=$((delay * 2))
  done
}

wait_healthy() {
  local service="$1" cid status
  for _ in $(seq 1 90); do
    cid="$($compose ps -q "$service" 2>/dev/null || true)"
    if [ -n "$cid" ]; then
      status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" 2>/dev/null || true)"
      case "$status" in
        healthy)
          echo "$service=healthy"
          return 0
          ;;
        unhealthy|exited|dead)
          echo "ERROR: $service entered terminal health state: $status" >&2
          $compose logs --tail=100 "$service" || true
          return 1
          ;;
      esac
    fi
    sleep 2
  done

  echo "ERROR: timeout waiting for $service health" >&2
  $compose ps "$service" || true
  $compose logs --tail=100 "$service" || true
  return 1
}

# Slot B first. On the first migration from the single-web topology, the historic
# web(A) remains live behind the currently loaded stack-nginx config.
retry $compose up -d --no-deps web-b
wait_healthy web-b

# Stable router now has two healthy/available backend names and dynamically resolves
# Docker DNS changes. --no-deps prevents Compose from touching slot A.
retry $compose up -d --no-deps backend-router
wait_healthy backend-router
$compose exec -T backend-router nginx -t
$compose exec -T backend-router nginx -s reload

# Next SSR/BFF must stop depending directly on slot A before A is replaced.
retry $compose up -d --no-deps frontend
wait_healthy frontend

# Apply stack-nginx routing via graceful reload, never restart.
$compose exec -T nginx nginx -t
$compose exec -T nginx nginx -s reload

# Safe pre-roll smoke. The 1C endpoint without a key must return 403; it does not
# export or mutate any order and proves nginx -> router -> Django is available.
$compose exec -T web-b python - <<'PY'
import urllib.error
import urllib.request

targets = (
    ("http://nginx/healthz/", 200),
    ("http://nginx/api/1c/orders/new", 403),
)
for url, expected in targets:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            code = response.status
    except urllib.error.HTTPError as exc:
        code = exc.code
    if code != expected:
        raise SystemExit(f"pre-roll availability failed: {url} -> {code}, expected {expected}")
print("pre_roll_availability=PASS")
PY

# Continuously probe the externally relevant compose-nginx route while slot A is
# recreated. Do not use a real API key and do not replay any mutating request.
availability_log=/tmp/drf2972-availability.log
$compose exec -T web-b python - <<'PY' >"$availability_log" 2>&1 &
import time
import urllib.error
import urllib.request

targets = (
    ("http://nginx/healthz/", 200),
    ("http://nginx/api/1c/orders/new", 403),
)
for tick in range(90):
    for url, expected in targets:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                code = response.status
        except urllib.error.HTTPError as exc:
            code = exc.code
        except Exception as exc:
            raise SystemExit(f"availability tick={tick} {url}: {exc}")
        if code != expected:
            raise SystemExit(
                f"availability tick={tick} {url} -> {code}, expected {expected}"
            )
    time.sleep(1)
print("rolling_availability=PASS")
PY
availability_pid=$!

# Slot A updates only after B + router + frontend + nginx route are ready.
retry $compose up -d --no-deps web
wait_healthy web

if ! wait "$availability_pid"; then
  cat "$availability_log" || true
  echo "ERROR: DRF-2972 rolling availability probe observed an outage" >&2
  exit 1
fi
cat "$availability_log"

# Workers are outside the synchronous HTTP path and can update after both web slots.
retry $compose up -d --no-deps celery celery-onec celery-images celery-beat

echo "rolling_backend_deploy=PASS"
