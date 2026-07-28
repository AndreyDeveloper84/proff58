# Парсер сайтов производителей (Phase 2 MVP)

Донор характеристик для каталога: собирает карточки товаров (пилот —
«перфораторы») с сайтов производителей и выгружает их в валидированный
JSON (схема `Export` / `ErrorsExport`). В БД ничего не пишет, кода Django
не касается.

Источники: `resanta`, `vihr`, `interskol`, `zubr` (+ `--source all`).

## Установка

```
.venv/Scripts/pip install -r parser/requirements.txt
```

## Запуск (одна команда)

```
.venv/Scripts/python.exe -m parser.main --source all --limit 8 \
  --category-name "Перфораторы" \
  --output scratchpad/parser-mvp/output \
  --cache-dir scratchpad/parser-mvp/http-cache \
  --fetch-log scratchpad/parser-mvp/phase2-fetch-log.jsonl
```

Результат: `<output>/<source>.products.json` и `<output>/<source>.errors.json`
на каждый источник; запись атомарная (`.tmp` → `os.replace`).

Опции: `--source` (обязателен), `--category-url` (маска sitemap / URL
листинга zubr; дефолт — пилот «перфораторы»; только одиночный источник),
`--limit` (дефолт 20 в http, 100 в browser, максимум 150 в browser),
`--errors-output` (только одиночный источник), `--cache-dir`,
`--fetch-log` (JSONL, append), `--throttle` (с, минимум 2.0, дефолт 3.0),
`--category-name`, `--mode {http,browser}` (дефолт http), `--bootstrap`
(только с `--mode browser`), `--browser-profile`.

## Режим доступа (обязателен к соблюдению)

Сеть — только через этот CLI (`parser.client.PoliteClient`):

- троттлинг 3 с между запросами на один хост (не настраивается ниже 2 с);
- соблюдение `robots.txt`;
- честный `User-Agent`;
- HTTP-кэш в `--cache-dir`, повторные запросы отдаются из кэша;
- журнал доступа в `--fetch-log` (JSONL: ts, url, статус, cache_hit);
- при 401/403/стойком 429 или запрете robots — `AccessDeniedError`,
  остановка с exit code 1, частичные результаты записываются. Повторный
  запуск «в лоб» и обходы запрещены — разбираться по журналу;
- 4xx на `robots.txt` — ограничений нет; 5xx/сетевая ошибка — ретрай
  (до 3), при повторной неудаче — `AccessDeniedError`: обход хоста
  без robots не выполняется (RFC 9309).

## Режим B (браузер)

Для источников, закрытых для HTTP (403/401, например `vseinstrumenti.ru`,
`dns-shop.ru`), карточки добираются через браузер: Playwright (chromium),
persistent context + `storage_state` — профиль и куки живут между запусками
(`parser/browser_client.py`, `BrowserClient`). Извлекатели карточек закрытых
источников — отдельный этап (fixtures нет).

Включается только явным флагом: `--mode browser` (по умолчанию — `http`).

### Первичный bootstrap (делает человек, один раз)

```
.venv/Scripts/python.exe -m parser.main --source resanta --mode browser --bootstrap
```

Откроется видимое окно браузера: перейдите на сайт источника, пройдите
проверку вручную (челлендж проходит ЧЕЛОВЕК; автоматического решения капчи
нет — ни своими силами, ни внешними сервисами), вернитесь в консоль и
нажмите Enter — сессия сохранится рядом с профилем
(`--browser-profile`, дефолт `scratchpad/parser-mvp/browser-profile`,
storage_state — `<профиль>.storage-state.json`). Дальше обход идёт headless
на сохранённой сессии.

### Жёсткие правила режима B

- человеческий темп: случайная пауза 5–10 с между карточками, никакого
  параллелизма;
- лимит карточек за прогон: дефолт 100 (`--limit`), верхняя планка 150 —
  параметром выше не поднять. Лимит общий на весь прогон: при
  `--source all --mode browser` первый источник может израсходовать весь
  бюджет, поэтому рекомендуемый сценарий режима B — одиночный источник;
- при 403/429 или маркерах челленджа в HTML — `BrowserChallengeError`,
  СТОП всего прогона и доклад в stderr. Никаких «подождать и повторить»:
  сработала защита → профиль неверен → решение владельца (новый bootstrap);
- фотографии не берём: загрузка image/media/font режется route abort;
- общее с режимом A: дисковый кэш (`<хост>/<хэш>.html`), журнал JSONL
  (те же поля + `mode: "browser"`), соблюдение robots.txt (сам robots
  получается один раз лёгким httpx-запросом — это не карточка).

Запуск обхода (после bootstrap):

```
.venv/Scripts/python.exe -m parser.main --source <источник> --mode browser \
  --limit 100 --fetch-log scratchpad/parser-mvp/browser-fetch-log.jsonl
```

## Структура модулей

- `parser/schemas.py` — pydantic-схемы `Export`, `ErrorsExport`,
  `ProductCard`, `ErrorRecord`;
- `parser/client.py` — `PoliteClient` (режим A): троттлинг, robots, кэш,
  журнал, `AccessDeniedError`;
- `parser/browser_client.py` — `BrowserClient` (режим B): Playwright,
  темп 5–10 с, лимит прогона, стоп на челлендже (`BrowserChallengeError`,
  `BrowserRunLimitError`);
- `parser/_fetch_common.py` — общее для режимов A/B: кэш-пути, журнал
  JSONL, robots.txt (`RobotsGate`);
- `parser/category.py` — сбор URL карточек: sitemap-источники (маска
  подстроки по `<loc>`) и листинг zubr;
- `parser/product.py` — извлечение карточки из HTML (таблицы
  характеристик, сырые значения с подписями единиц);
- `parser/main.py` — CLI-оркестратор: сбор → скачивание → извлечение →
  атомарная запись + статистика; флаги `--mode`, `--bootstrap`,
  `--browser-profile`;
- `parser/tests/` — тесты на записанных fixtures и фейках, сети и
  реального браузера нет (кроме smoke на `about:blank`).

## Тесты

```
.venv/Scripts/python.exe -m pytest parser/tests -q
```

114 тестов: без сети и без реального браузера (фейки page/context), кроме
одного smoke-теста (`pytest.mark.smoke`) — реальный headless chromium
открывает `about:blank`, внешней сети нет.
