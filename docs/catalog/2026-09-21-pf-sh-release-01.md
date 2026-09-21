# PF-SH-RELEASE-01 — выпуск в индекс перфораторов и шлифмашин

**Дата:** 2026-09-21 · **Деплой:** `50c80b0` (PR #793) · **Основание:** release-gate manifest
`docs/catalog/appendix/2026-09-21-pf-sh-release-gate-01/pf-sh-release-gate-01.json`
(sha256 `112281b5…c866c`, PR #792)

**Verdict: `PF-SH-RELEASE-01 = PASS`**

74 карточки открыты для индексации. 11 заблокированных и остальной каталог закрыты (`noindex`).
Сценарий «краулер → 429 → SSR 500» устранён. Товары, характеристики, фото и таксономия не менялись.

## Что сделано (PR #793)

| Задача | Решение |
|---|---|
| SSR → DRF 429 → 500 | SSR подписывает запросы к Django секретом `SSR_INTERNAL_TOKEN` (`X-SSR-Token`), анонимный лимит его не трогает; стек-nginx вырезает заголовок у внешних запросов |
| robots.txt по средам | Генерирует Next: открыт только при `SEO_INDEXING=production` **и** хосте `proff58.ru`; иначе `Disallow: /` |
| индексация только 74 | По умолчанию `noindex, follow`; `index` — карточки из `data/seo/indexable_products.json` (= INDEXABLE_CANDIDATE manifest, sha сверяет тест) |
| sitemap.xml | Только allowlist ∩ видимые товары |
| canonical | `https://proff58.ru/product/<slug>` |
| title | Убран двойной суффикс «— Профессионал» |

Runbook открытия и отката: `docs/runbooks/seo-indexing-release.md`.

## Проверка до открытия (robots закрыт, `SEO_INDEXING=off`)

Все P0 — PASS: 74/74 кандидата, 11/11 заблокированных, sitemap = ровно 74 canonical,
посторонние страницы `noindex`, burst 170 запросов без 429/5xx. На момент гейта при шаге 0,3 с
было 13 × 500 из 85.

## Открытие

`SEO_INDEXING=production` в `.env` стека `proff58_staging` → пересоздан только `frontend`.

**Важно:** отдельного production-стека нет. `proff58.ru` обслуживает стек, который деплоится из `dev`.
Решение открыть на нём принято владельцем 2026-09-21. Каждый merge в `dev` теперь попадает на
индексируемый сайт, но в индекс идут только карточки из allowlist.

## Состояние после открытия

| Проверка | Результат |
|---|---|
| `https://proff58.ru/robots.txt` | `Allow: /`, `Disallow: /api/`, `Disallow: /*?`, `Sitemap: https://proff58.ru/sitemap.xml` |
| robots на Host `dev.proff58.ru` и по IP | `Disallow: /` |
| `https://dev.proff58.ru/*` | 301 → `proff58.ru` |
| `sitemap.xml` | 200, 74 URL, лишних 0, заблокированных 0 |
| посторонняя карточка, раздел, `/catalog`, главная | `noindex, follow` |
| burst: 85 карточек подряд + 85 в 6 потоков | 200 × 170, 0 × 429/5xx |

### 74 кандидата

| Статус | OK |
|---|---:|
| `INDEXABLE_HTTP_OK` | 74/74 |
| `CANONICAL_OK` | 74/74 |
| `ROBOTS_OK` | 74/74 |
| `META_ROBOTS_OK` (`index, follow`) | 74/74 |
| `SITEMAP_INCLUDED` | 74/74 |
| `JSON_LD_OK` | 74/74 |
| `IMAGE_OK` | 74/74 |
| title без дубля | 74/74 |

### 11 заблокированных

| Статус | OK |
|---|---:|
| `SITEMAP_EXCLUDED` | 11/11 |
| `NOT_INDEXABLE` (`noindex, follow`) | 11/11 |

Статусы по каждому SKU: `docs/catalog/appendix/2026-09-21-pf-sh-release-01/pf-sh-release-01-result.json`.

## Запись

Product 47 225, PAV 85 145, ProductImage 1 125, Attribute 110, Option 678, CategoryAttribute 298,
Category 362 — до и после деплоя одинаковы. Изменены только код, конфигурация и `.env` стека
(`SSR_INTERNAL_TOKEN`, `SEO_INDEXING`; копии `.env.bak-2026-09-21-*` на сервере).

## Откат

`SEO_INDEXING=off` в `.env` стека → `docker compose -f docker-compose.prod.yml up -d frontend`
→ `robots.txt` = `Disallow: /` (секунды). Подробнее — runbook.

## Дальше

1. `PF-SH-BLOCKERS-01` — дешёвые DATA/TAXONOMY-исправления (45125 `voltage=8`; характеристики
   45450/45452/45113; станок 44955) → до ~79 индексируемых. Новые id добавляются в allowlist только
   новым гейтом.
2. `BURY-MEDIA-PILOT-01` — пилот фото на 20–30 SKU `bury`, чтобы замерить долю строгих совпадений.
3. Отдельная OPS-задача: prod-стек из `main`, чтобы индексируемый сайт не зависел от merge в `dev`.
