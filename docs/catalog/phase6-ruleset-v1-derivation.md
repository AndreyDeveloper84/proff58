# phase6-ruleset-v1-derivation — APPROVED (Stage 7 CLOSED 2026-07-21)

> Финальная версия derivation document для ruleset `tool_type.v1` после
> Stage 7 ревью и rework. Процесс и контракты:
> `docs/plans/2026-07-21-PHASE7A_CORPUS_AND_CANDIDATE_RULES_PLAN.md` (v2).
>
> **Repo fixtures:**
> - `data/catalog_processing_rules/tool_type.v1.json` — sha256
>   `93d145e479dfc2c528e849d09bbfc69640f2ca6672766b69f6c7c68cee4b7b8b`,
>   `ruleset_hash = canonical_hash`:
>   `51b3bbad7c65565637711e5bf9ee74eb7b477ff71b9e25183095ede9cb1044bd`
>   (отличается от draft-хэша Stage 7 `edb33cfca3…` только полем `note`:
>   draft-пометка заменена на approved согласно плану §6.1; правила и
>   fixtures байт-в-байт те же, что утверждены).
> - `data/catalog_processing_rules/applied_corpus_tool_type.v1.json` —
>   sha256 `32511e850f732c7419cf6c7164d4a41da7de566ecb3929f15f34baf73aba035e`.
>   Repo fixture = staging-артефакт + утверждённое `"expected_recall": 0.59`
>   (план §6.1: «то же содержимое + expected_recall»); staging-артефакт
>   (до поля): sha256 `d5c0117e737db4b31149c237b60aebc7f02dbb0249da71e42089fb16703b0311`.

Corpus: `staging-tool-type-6ebb8ac9d856`;
`artifact_content_hash = 81c15c5fbcb94c61c0ec2ff9dce7c14d42f5325c9068756c6e32bef69e37361d`
(canonical_hash(doc БЕЗ `extracted_at`), источник corpus_id, стабилен —
относится к staging-артефакту без `expected_recall`);
`loader_corpus_hash` — поле `replay.corpus_hash` продакшн-кода
(`Command._replay`): canonical_hash(полный dict ВКЛЮЧАЯ `extracted_at`),
volatile fingerprint файла. Разведение имён принято на Stage 7
(hash_registry; code change для переименования replay-поля не требуется).

## Метод деривации

Corpus сгруппирован по `source_group` (+ серии по original_name); brand
пуст у всех 54 товаров → измерение `brand_any` недоступно и не используется.
Candidate-правило создаётся только для label с ≥ 2 товарами (P0.2:
≥ 2 уникальных product ID в `derived_from`). Измерения каждого правила:
`source_group_any` + `original_name_keywords_any` (оба непустых → P0.2).
`name` и `original_name` идентичны у всех 54 строк (проверено скриптом),
keyword-измерение взято по `original_name` (сырое имя 1С).
`negative_keywords` не используются (Task 1.3 не в dev; негативную
нагрузку несут rule-scoped fixtures).

## Правила (11 candidate — ALL APPROVED, Stage 7)

Правила 1–10 approved на первом раунде Stage 7 (№6 и №7 — approved with
monitoring: precision этих правил отдельно показать в Phase 7B).
Правило 11 approved после rework (узкая версия по рецепту ревью).

### 1. tt-krep-shplinty-nabor → krep-shplinty — APPROVED
- Группа: 26863, 26864, 26865 (sg «Оснастка», «Набор шплинтов …»).
- Измерения: `source_group_any=[Оснастка]`, `original_name_keywords_any=[шплинт]`.
- Почему slug: все три товара — наборы шплинтов; prefix `шплинт` покрывает
  «шплинтов». Риски: «Набор» общий с krep-shaiby (23255) и puskovye-provoda
  делят sg — keyword `шплинт` их разделяет; вне corpus поведение — gate 7B.
- Fixture: `fix-puskovye-27250` (реальный товар 27250, тот же sg, другой label).

### 2. tt-puskovye-provoda-startovye → puskovye-provoda — APPROVED
- Группа: 27250, 27251, 27254 (sg «Оснастка», «Провода стартовые …»).
- Измерения: `source_group_any=[Оснастка]`, `original_name_keywords_any=[провода стартовые]`.
- Почему slug: двухсловный keyword устойчив («провода» одно было бы шире).
  Риски: шплинт-наборы в том же sg — разделены keyword'ом.
- Fixture: `fix-shplinty-26863` (товар 26863).

### 3. tt-bp-pnevmosteplery-gvozde → bp-pnevmosteplery — APPROVED
- Группа: 28891, 28892, 28893 («Пневмонейлер ЗУБР …»), 28901
  («Пневмопистолет гвоздезабивной …»), sg «Пневмоинструмент».
- Измерения: `source_group_any=[Пневмоинструмент]`,
  `original_name_keywords_any=[пневмонейлер, гвоздезабивной]`.
- Почему slug: 4/4 товара — гвоздезабивной пневмоинструмент; два keyword'а
  покрывают обе словарные формы. Риски: 28677 (оснастка отбойного молотка)
  в том же sg — разделён keyword'ом.
- Fixture: `fix-pnevmomolotok-28677` (товар 28677).

### 4. tt-siz-ochki-zashchitnye → siz-ochki — APPROVED
- Группа: 36300, 36302, 36304 («Маска щиток защитный …»), 36377, 36378
  («Очки защитные газосварщика …»), sg «Средства индивидуальной защиты».
- Измерения: `source_group_any=[Средства индивидуальной защиты]`,
  `original_name_keywords_any=[маска щиток, очки защитные]`.
- Почему slug: taxonomy value slug'а — «Очки и щитки защитные», поэтому
  включение масок-щитков обосновано (отмечено ревью). Риски: 36713 (пояс
  монтажника) в том же sg — разделён.
- Fixture: `fix-poyas-36713` (товар 36713).

### 5. tt-dinamometricheskie-klyuchi-klyuch → dinamometricheskie-klyuchi — APPROVED [narrow]
- Группа: 12957, 12959 («Ключ динамометрический … KRAFTOOL»),
  sg «Ключи, головки, воротки, удлинители». Семейство ADR-0011 remediation.
- Измерения: `source_group_any=[Ключи, головки, воротки, удлинители]`,
  `original_name_keywords_any=[ключ динамометрический]`.
- Почему slug: двухсловный keyword критичен — однословный
  «динамометрический» НЕ матчит «динамометрическая» (окончание), но stem
  «динамометрическ» матчил бы оба; «ключ динамометрический» не матчит
  13936 («Отвертка динамометрическая», нет токена «ключ») и 10537
  («Адаптер динамометрический», другая sg + нет «ключ»). Проверено fixtures.
- Риски: `derived_from` ровно 2 → narrow; будущие «ключ динамометрический»
  в других sg не покрываются (осознанно, precision > recall).
- Fixtures: `fix-otvertka-13936` (товар 13936, ADR-0011 near-miss),
  `fix-adapter-dinam-10537` (товар 10537).

### 6. tt-adaptery-universal → adaptery — APPROVED with monitoring
- Группа: 1110, 1111 («Адаптер-переходник …», sg «Аккумуляторы и зарядные
  устройства»), 6681, 6682 («Адаптер для АКБ …», sg «Запасные части»),
  10537 («Адаптер динамометрический …», sg «Измерительный инструмент»).
- Измерения: `source_group_any=[3 sg]`, `original_name_keywords_any=[адаптер]`.
- Почему slug: общий токен «адаптер» (дефис — разделитель токенов:
  «адаптер-переходник» → «адаптер»); sg-список ограничивает три provenance
  группы. Риски: cross-group обобщение внутри трёх sg (любой «адаптер…»
  там → adaptery) — семантически приемлемо (review), но precision правила
  отдельно показать в Phase 7B; 22473 («…с адаптером 3/4"», sg «Мойки»)
  keyword матчит, но sg-конъюнкт отсекает — sg несущее.
- Fixture: `fix-derzhatel-10631` (товар 10631, sg из списка, без «адаптер»).

### 7. tt-izm-shtativy-derzhatel → izm-shtativy — APPROVED with monitoring [narrow]
- Группа: 10631, 10632 («Держатель … KRAFTOOL», sg «Измерительный инструмент»).
- Измерения: `source_group_any=[Измерительный инструмент]`,
  `original_name_keywords_any=[держатель]`.
- Почему slug: taxonomy — «Штативы, отражатели, держатели» (отмечено
  ревью); provenance подтверждает оба товара. Риски: «держатель» —
  generic-слово; точность проверяется gate 7B; narrow.
- Fixture: `fix-adapter-dinam-10537` (товар 10537, тот же sg, другой label).

### 8. tt-svar-reduktory-regulyator → svar-reduktory — APPROVED [narrow]
- Группа: 31106, 31109 («Регулятор расхода газа …», sg «Сварочное оборудование»).
- Измерения: `source_group_any=[Сварочное оборудование]`,
  `original_name_keywords_any=[регулятор расхода газа]`.
- Почему slug: трёхсловный keyword точен. Риски: 30870 (кабель с клеммой)
  в том же sg — разделён; narrow.
- Fixture: `fix-klemmy-30870` (товар 30870).

### 9. tt-hoz-lenty-malyarnaya → hoz-lenty — APPROVED [narrow]
- Группа: 37269, 37270 («Лента малярная креповая …», sg
  «Строительно-отделочный инструмент»).
- Измерения: `source_group_any=[Строительно-отделочный инструмент]`,
  `original_name_keywords_any=[лента малярная]`.
- Риски: 37594 (плиткорез) в том же sg — разделён; narrow.
- Fixture: `fix-plitkorez-37594` (товар 37594).

### 10. tt-nabory-instrumenta-dielektr → nabory-instrumenta — APPROVED [narrow]
- Группа: 22650, 22651 («Набор диэлектрического инструмента до 1000 в …»,
  sg «Наборы инструмента»).
- Измерения: `source_group_any=[Наборы инструмента]`,
  `original_name_keywords_any=[набор диэлектрического]`.
- Почему slug: двухсловный keyword отделяет от «Набор медных шайб» (23255,
  тот же sg). Риски: narrow.
- Fixture: `fix-shaiby-23255` (товар 23255).

### 11. tt-yashchiki-sumki-keys-prochee → yashchiki-sumki — APPROVED [narrow]
- **История:** v1 `tt-yashchiki-sumki-keys-sumka` (`[сумка, кейс] ×
  [Бензоинструмент, Прочее]`, derived_from=[1855, 30223, 30225]) —
  REJECTED на Stage 7: декартово обобщение давало неподтверждённые
  комбинации «кейс × Бензоинструмент» и «сумка × Прочее». v2 (узкая
  версия по рецепту ревью) — APPROVED.
- Группа: 30223, 30225 («Кейс пластиковый Hitachi …», sg «Прочее»).
- Измерения: `source_group_any=[Прочее]`, `original_name_keywords_any=[кейс]`.
- `derived_from=[30223, 30225]` (ровно 2 → narrow).
- Товар 1855 («Сумка для бензопилы CHAMPION») — сознательно синглтон без
  правила до появления второго подтверждённого примера (P0.2 сохраняется);
  защищён negative fixture `fix-sumka-1855`.
- Fixtures: `fix-svechi-1817` (товар 1817, sg вне области правила),
  `fix-sumka-1855` (товар 1855 — отклонённая cross-комбинация:
  «сумка + Бензоинструмент» правилом не классифицируется).

## Непокрытые товары (22 no_match)

21 товар — label-синглтоны (P0.2: нет ≥ 2 derived_from → нет candidate
правила). Плюс 1855 — de-scoped по решению Stage 7. Keyword-only
`shadow_regression` правила из одного примера не создавались
(спекулятивно; не влияют на replay; решение Stage 7 — не в v1).

## Отклонения

- **DEVIATION-1 (F6)** — ACCEPTED as non-blocking data finding
  (Stage 7): `changes_total = 57` (applied 56 + rejected 1) против
  исторического ожидания 58; pre/post идентичны, applied counters 56/54,
  non-final = 0, provenance corpus не затронут.
- **DEVIATION-2** — RECORDED, non-blocking for fixture PR, блокирует
  Phase 7B до расследования: taxonomy export — 328 строк, 327 уникальных
  slug; slug `steplery` продублирован («Степлеры и заклёпочники» /
  «Степлеры (скобозабивные)») → в БД две записи AttributeOption с
  одинаковым slug. Root cause (локальный код):
  `AttributeOption.Meta.unique_together = [(attribute, value)]` — slug не
  уникален; apply по slug использует `.filter(...).first()` без order_by
  (`processing.py:328`, `:581`) — выбор записи недетерминирован
  контрактом. На текущие 11 правил влияния нет (slug не используется).
  До Phase 7B: PK/sort_order обеих записей, PAV-ссылки, канонический
  option, поведение importer/facets; исправление — отдельная авторизация.

## Replay (informational, НЕ gate; training leakage по построению)

Replay на repo fixtures (продакшн-логика `Command._replay`):

- `measured_recall = 0.5926` (correct = 32, items = 54).
- Mismatches: 22 — ВСЕ `no_match` (21 синглтон + 1855); wrong-slug
  predictions = 0; rule-коллизии = 0; hits == derived_from для всех 11
  правил; `check_negative_fixtures == []`; `validate_against_taxonomy
  == []`; `derived_from ⊆ corpus` — все проверки пройдены на repo
  fixtures перед PR.
- Recall НЕ доказывает precision; gate 6.1 — Phase 7B на независимой
  выборке ≥ 100 predictions.

### F11: measured < 0.90 — ACCEPTED under option (a) (Stage 7, 2026-07-21)

Потолок структурный: 21/54 синглтонов × P0.2 + 1855 de-scoped →
32/54 = 0.5926. Решение пользователя (дословно): «The candidate-tier
recall ceiling is structurally limited by P0.2: 21 of 54 corpus items
belong to singleton labels and cannot produce candidate rules requiring
at least two independent derived_from items. All uncovered items are
no_match. Wrong-slug predictions = 0. Rule collisions = 0.» Плюс 1855 —
сознательное непокрытие после отклонения cross-product
(безопасность > покрытие).

### expected_recall = 0.59 — APPROVED (2026-07-21)

Решение пользователя (дословно): «Measured candidate-tier recall:
32 / 54 = 0.592592… The threshold preserves all 32 currently covered
corpus items. A loss of one covered item reduces recall below 0.59 and
fails the gate.» Порог ниже measured 0.5926, не зависит от сравнения с
округлённым значением на границе float; 31/54 ≈ 0.5741 < 0.59 → тест
упадёт при потере любого покрытого товара. Поле записано в corpus
fixture (`"expected_recall": 0.59`, схема
`applied_tool_type_corpus_v1.json`, `load_corpus` читает его) — НЕ в
ruleset (схема ruleset его не содержит).

## Human Decision Log

| Decision | Reason | Timestamp (UTC) |
|---|---|---|
| План Task 7 v2 approved; Phase 7A authorized | ревью плана 9.4/10, P0/P1/P2 закрыты | 2026-07-21 (пользователь) |
| corpus run accepted: staging-tool-type-6ebb8ac9d856 | hash/id стабильны в 2 прогонах, counters сверены, exclusions=0, load_corpus принят | 2026-07-21 (пользователь, Stage 7) |
| DEVIATION-1 accepted as non-blocking data finding | applied-контур не затронут; rejected-расхождение вне scope | 2026-07-21 (пользователь, Stage 7) |
| F11 accepted under option (a) | структурный потолок P0.2: 21/54 синглтонов; все непокрытые — no_match; wrong-slug=0; collisions=0 | 2026-07-21 (пользователь, Stage 7) |
| rules №1–10 approved (№6, №7 — with monitoring) | per-rule review Stage 7 | 2026-07-21 (пользователь, Stage 7) |
| rule v1 tt-yashchiki-sumki-keys-sumka rejected | неподтверждённые cross-комбинации [сумка,кейс]×[Бензоинструмент,Прочее] | 2026-07-21 (пользователь, Stage 7) |
| rule v2 tt-yashchiki-sumki-keys-prochee written per reviewer recipe | только подтверждённая пара кейс+Прочее; 1855 de-scoped | 2026-07-21 (analyst rework) |
| corpus hash ambiguity → hash_registry | artifact_content_hash / loader_corpus_hash разведены по именам | 2026-07-21 (пользователь находка 5; analyst rework; принято на финальном ревью) |
| DEVIATION-2 (duplicate slug steplery) recorded | 328 rows / 327 unique slugs; расследование до Phase 7B; исправление — отдельная авторизация | 2026-07-21 (пользователь находка 6; analyst rework; accepted на финальном ревью) |
| rule tt-yashchiki-sumki-keys-prochee — APPROVED [narrow] | replay v2: hits == derived_from, fixtures фиксируют отклонённую комбинацию | 2026-07-21 (пользователь, финальное решение) |
| expected_recall = 0.59 — APPROVED | replay v2 measured 32/54 = 0.5926; порог сохраняет все 32 совпадения и падает при потере одного | 2026-07-21 (пользователь, финальное решение) |
| Ruleset v2 — APPROVED, 11/11 rules; Stage 7 — CLOSED | все проверки на repo fixtures зелёные | 2026-07-21 (пользователь, финальное решение) |
| Fixture PR — AUTHORIZED | ruleset + corpus fixture + derivation + replay regression test | 2026-07-21 (пользователь, финальное решение) |
| Phase 7B — NOT AUTHORIZED | blocked pending DEVIATION-2 investigation + отдельная авторизация | 2026-07-21 (пользователь, финальное решение) |
