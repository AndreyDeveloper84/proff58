#!/usr/bin/env bash
# Smoke-проверка production/staging после деплоя.
# Не требует Python-окружения — только curl и bash.
#
# Использование:
#   bash scripts/smoke_prod.sh https://proff58.ru
#   bash scripts/smoke_prod.sh https://dev.proff58.ru
set -euo pipefail

BASE_URL="${1:?Укажите URL: bash scripts/smoke_prod.sh https://proff58.ru}"
# Убираем trailing slash
BASE_URL="${BASE_URL%/}"

PASS=0
FAIL=0
WARN=0

check() {
    local label="$1"
    local result="$2"
    if [[ "$result" == "ok" ]]; then
        echo "  ✓ $label"
        PASS=$((PASS + 1))
    elif [[ "$result" == "warn" ]]; then
        echo "  ⚠ $label"
        WARN=$((WARN + 1))
    else
        echo "  ✗ $label — $result"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== Smoke-проверка: $BASE_URL ==="
echo ""

# --- 1. Healthcheck ---
echo "1. Healthcheck"
HC=$(curl -s -o /tmp/smoke_hc.json -w '%{http_code}' "$BASE_URL/healthz/" 2>/dev/null || echo "000")
if [[ "$HC" == "200" ]]; then
    HC_STATUS=$(python3 -c "import json; print(json.load(open('/tmp/smoke_hc.json'))['status'])" 2>/dev/null || echo "?")
    if [[ "$HC_STATUS" == "ok" ]]; then
        check "GET /healthz/ → 200, status=ok" "ok"
    else
        check "GET /healthz/ → 200, но status=$HC_STATUS" "status не ok"
    fi
else
    check "GET /healthz/ → HTTP $HC" "ожидался 200"
fi

# --- 2. Каталог API ---
echo ""
echo "2. Каталог API"

CAT_CODE=$(curl -s -o /tmp/smoke_cat.json -w '%{http_code}' "$BASE_URL/api/catalog/categories/" 2>/dev/null || echo "000")
if [[ "$CAT_CODE" == "200" ]]; then
    check "GET /api/catalog/categories/ → 200" "ok"
else
    check "GET /api/catalog/categories/ → HTTP $CAT_CODE" "ожидался 200"
fi

PROD_CODE=$(curl -s -o /tmp/smoke_prod.json -w '%{http_code}' "$BASE_URL/api/catalog/products/?limit=3" 2>/dev/null || echo "000")
if [[ "$PROD_CODE" == "200" ]]; then
    HAS_COUNT=$(python3 -c "import json; d=json.load(open('/tmp/smoke_prod.json')); print('ok' if 'count' in d and 'results' in d else 'no')" 2>/dev/null || echo "no")
    if [[ "$HAS_COUNT" == "ok" ]]; then
        COUNT=$(python3 -c "import json; print(json.load(open('/tmp/smoke_prod.json'))['count'])" 2>/dev/null || echo "0")
        check "GET /api/catalog/products/ → 200, count=$COUNT" "ok"
    else
        check "GET /api/catalog/products/ → 200, но нет count/results" "формат ответа неверный"
    fi
else
    check "GET /api/catalog/products/ → HTTP $PROD_CODE" "ожидался 200"
fi

# Карточка товара (берём первый slug из списка)
SLUG=$(python3 -c "
import json
d = json.load(open('/tmp/smoke_prod.json'))
r = d.get('results', [])
print(r[0]['slug'] if r else '')
" 2>/dev/null || echo "")

if [[ -n "$SLUG" ]]; then
    DETAIL_CODE=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/api/catalog/products/$SLUG/" 2>/dev/null || echo "000")
    if [[ "$DETAIL_CODE" == "200" ]]; then
        check "GET /api/catalog/products/$SLUG/ → 200" "ok"
    else
        check "GET /api/catalog/products/$SLUG/ → HTTP $DETAIL_CODE" "ожидался 200"
    fi
else
    check "Карточка товара (нет товаров для проверки)" "warn"
fi

# --- 3. 1С API (без ключа = 403) ---
echo ""
echo "3. 1С API (авторизация)"

ONEC_CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/api/1c/products/import" \
    -H 'Content-Type: application/json' -d '{"items":[]}' 2>/dev/null || echo "000")
if [[ "$ONEC_CODE" == "403" ]]; then
    check "POST /api/1c/products/import без ключа → 403" "ok"
else
    check "POST /api/1c/products/import без ключа → HTTP $ONEC_CODE" "ожидался 403"
fi

# --- 4. Админка ---
echo ""
echo "4. Админ-панель"

ADMIN_CODE=$(curl -s -o /dev/null -w '%{http_code}' -L "$BASE_URL/admin/login/" 2>/dev/null || echo "000")
if [[ "$ADMIN_CODE" == "200" ]]; then
    check "GET /admin/login/ → 200" "ok"
else
    check "GET /admin/login/ → HTTP $ADMIN_CODE" "ожидался 200"
fi

# --- 5. Статика ---
echo ""
echo "5. Статика"

STATIC_CODE=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/static/admin/css/base.css" 2>/dev/null || echo "000")
if [[ "$STATIC_CODE" == "200" ]]; then
    check "GET /static/admin/css/base.css → 200" "ok"
else
    check "GET /static/admin/css/base.css → HTTP $STATIC_CODE" "ожидался 200 (collectstatic?)"
fi

# --- Итог ---
echo ""
echo "=== Итог: $PASS passed, $FAIL failed, $WARN warnings ==="

if [[ "$FAIL" -gt 0 ]]; then
    echo "⚠ Есть проблемы — проверьте логи перед продолжением."
    exit 1
fi

echo "✓ Smoke-проверка пройдена."
