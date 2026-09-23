# Индексация витрины: открытие и откат (PF-SH-RELEASE-01)

## Как устроено

Два независимых уровня.

| Уровень | Где | Поведение |
|---|---|---|
| **robots.txt** — обход всей среды | `frontend/app/robots.ts`, политика в `frontend/lib/seo.ts` | Открыт только при `SEO_INDEXING=production` **и** запросе на хосте `SITE_URL`. Любая другая/пустая среда, `dev.`, IP, localhost → `Disallow: /`. Открытый: `Allow: /`, `Disallow: /api/`, `Disallow: /*?`, `Sitemap: <SITE_URL>/sitemap.xml`. |
| **meta robots** — что индексировать | `frontend/app/layout.tsx` (по умолчанию), `frontend/app/product/[slug]/page.tsx` | Все страницы `noindex, follow`. `index, follow` — только карточки из allowlist. |
| **allowlist** | `data/seo/indexable_products.json` → `apps/catalog/seo_index.py` | Ровно `INDEXABLE_CANDIDATE` замороженного release-gate manifest (ссылка и sha256 внутри файла; тест `apps/catalog/test_seo_indexing.py` сверяет). API карточки отдаёт `seo_indexable`. Нет/битый файл → не индексируется ничего. |
| **sitemap.xml** | `frontend/app/sitemap.ts` ← `GET /api/catalog/seo/sitemap-products/` | Только allowlist ∩ видимые (active + published). |
| **canonical** | `productSeoMetadata` | `<SITE_URL>/product/<slug>` (без хвостового слэша; со слэшем — 308). |

Отдельно — **SSR и лимит API.** SSR ходит в Django напрямую (`http://web:8000`) без
`X-Forwarded-For`, поэтому раньше все посетители делили один анонимный лимит (200/мин) →
429 → карточка 500 при обходе краулером. Теперь SSR подписывает запросы секретом
`SSR_INTERNAL_TOKEN` (заголовок `X-SSR-Token`, `frontend/lib/ssr.ts`), а
`apps/core/throttling.AnonRateThrottle` его не лимитирует. Стек-nginx вырезает
`X-SSR-Token` у внешних запросов. Прямые запросы к `/api/` снаружи лимитируются как раньше.

## Переменные `.env` стека

| Переменная | Значение | Кто читает |
|---|---|---|
| `SSR_INTERNAL_TOKEN` | секрет, одинаковый для web и frontend (`python -c "import secrets; print(secrets.token_urlsafe(32))"`) | web (`env_file`), frontend (`environment` в `docker-compose.prod.yml`) |
| `SEO_INDEXING` | `off` (по умолчанию) / `production` | frontend |
| `SITE_URL` | `https://proff58.ru` | web, frontend |

Пустой `SSR_INTERNAL_TOKEN` не ломает сайт — просто возвращает старое поведение (общий лимит).

## Проверки перед открытием (robots ещё закрыт)

1. `/robots.txt` → `Disallow: /`.
2. Все карточки allowlist (сейчас 107 = партия 1 «74» + партия 2 «33 дрели»): 200, `<meta name="robots" content="index, follow">`, canonical, title без
   двойного суффикса, JSON-LD Product, главное фото 200.
3. 11 заблокированных release-gate: 200, `noindex`, нет в sitemap.
4. Посторонняя карточка и разделы каталога: `noindex`.
5. `/sitemap.xml`: ровно `count` из allowlist URL, все = canonical.
6. Burst: 85 карточек подряд без пауз — 0 × 429/500.

## Добавление партии

Allowlist (`data/seo/indexable_products.json`) — объединение партий; каждая партия ссылается на
свой замороженный manifest гейта и его sha256 (`batches[]`). Порядок:

1. Гейт партии (read-only): commercial + фото с main + обязательные оси типа + HTTP-проверка карточки,
   display-фото и JSON-LD. Результат — manifest в `docs/catalog/appendix/<дата>-<партия>/`.
2. В allowlist добавить запись в `batches[]` (id, tool_types, manifest, sha256, count) и id в
   `product_ids`; `count` = длина списка. Пересечение партий запрещено — это проверяет тест.
3. PR с manifest и allowlist; после merge — деплой frontend (`up -d frontend`).
4. Проверка на проде: `/sitemap.xml` = новый `count`, новые карточки `index, follow`.

Откат партии — убрать её id и запись `batches[]`, задеплоить frontend.

## Открытие

```bash
cd ~/proff58-staging        # стек, который обслуживает proff58.ru
# в .env: SEO_INDEXING=production
docker compose -f docker-compose.prod.yml up -d frontend
curl -s https://proff58.ru/robots.txt        # Allow: / … Sitemap: https://proff58.ru/sitemap.xml
```

После открытия повторить: robots.txt, sitemap.xml, canonical образцовой карточки, заблокированная
карточка (`noindex`), посторонняя карточка (`noindex`), HTTP-смоук, burst.

## Откат

- **Закрыть обход целиком (секунды):** в `.env` `SEO_INDEXING=off` (или удалить строку) →
  `docker compose -f docker-compose.prod.yml up -d frontend` → `/robots.txt` = `Disallow: /`.
- **Снять отдельный товар с индексации:** убрать его id из `data/seo/indexable_products.json`
  (PR) → после деплоя карточка `noindex` и вне sitemap. Удалить из индекса быстрее —
  Search Console / Вебмастер.
- **Вернуть старое поведение лимита:** очистить `SSR_INTERNAL_TOKEN` и перезапустить web и frontend.
- Кодовый откат — revert PR PF-SH-RELEASE-01: вернётся статический `robots.txt` (`Disallow: /`).

Товары, характеристики, фото и таксономию выпуск не меняет — откатывать в данных нечего.
