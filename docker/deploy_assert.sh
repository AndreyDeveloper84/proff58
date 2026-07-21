#!/usr/bin/env bash
# Post-deploy safety checks for staging/production.
#
# This script is intentionally stricter than a smoke test: it verifies that
# migrations are fully applied, the app containers are running, the web
# container was recreated from the current compose image, and nginx can reach
# /healthz/. If any check fails, the deploy must be red.
set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
compose="docker compose -f $COMPOSE_FILE"

fail() {
    echo "::error::$*"
    $compose ps || true
    $compose logs --tail=120 web || true
    exit 1
}

echo "==> Post-deploy: web container is running"
web_container="$($compose ps -q web)"
[[ -n "$web_container" ]] || fail "web container not found"

web_state="$(docker inspect -f '{{.State.Status}}' "$web_container")"
[[ "$web_state" == "running" ]] || fail "web container is not running (state=$web_state)"

echo "==> Post-deploy: web runs the current compose image"
compose_web_image="$($compose images -q web | head -n1)"
[[ -n "$compose_web_image" ]] || fail "compose image for web not found"

compose_web_image_id="$(docker image inspect -f '{{.Id}}' "$compose_web_image")"
running_web_image_id="$(docker inspect -f '{{.Image}}' "$web_container")"
if [[ "$running_web_image_id" != "$compose_web_image_id" ]]; then
    fail "web runs a stale image (running=$running_web_image_id, compose=$compose_web_image_id)"
fi

echo "==> Post-deploy: migrations plan is empty"
$compose exec -T web python manage.py migrate --check

echo "==> Post-deploy: app services are running"
for service in frontend celery celery-onec celery-beat nginx; do
    container="$($compose ps -q "$service")"
    [[ -n "$container" ]] || fail "$service container not found"
    state="$(docker inspect -f '{{.State.Status}}' "$container")"
    [[ "$state" == "running" ]] || fail "$service container is not running (state=$state)"
done

echo "==> Post-deploy: nginx /healthz/ returns 200"
$compose exec -T web python - <<'PY'
import json
import sys
import urllib.request

url = "http://nginx/healthz/"
try:
    with urllib.request.urlopen(url, timeout=10) as response:
        body = response.read().decode("utf-8")
        if response.status != 200:
            print(f"healthz returned HTTP {response.status}", file=sys.stderr)
            sys.exit(1)
except Exception as exc:  # noqa: BLE001 - deploy diagnostics must be explicit.
    print(f"healthz request failed: {exc}", file=sys.stderr)
    sys.exit(1)

try:
    data = json.loads(body)
except json.JSONDecodeError:
    print(f"healthz returned non-json body: {body[:200]}", file=sys.stderr)
    sys.exit(1)

if data.get("status") != "ok":
    print(f"healthz status is not ok: {data}", file=sys.stderr)
    sys.exit(1)
PY

echo "==> Post-deploy assertions passed"
