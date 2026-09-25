# phase6-ruleset-v1-derivation (DRAFT v2, pending final approval)

> Draft для Stage 7 ревью (план Task 7 §6.4). После финального approval
> документ переедет в `docs/catalog/phase6-ruleset-v1-derivation.md`,
> ruleset — в `data/catalog_processing_rules/tool_type.v1.json`.
>
> **v2 (2026-07-21, rework по Stage 7 review):** правило
> `tt-yashchiki-sumki-*` переписано в узкую версию по рецепту ревью
> (cross-product отклонён, 1855 de-scoped); повторные проверки и replay
> выполнены; два corpus hash разведены по именам (hash_registry);
> добавлена DEVIATION-2 (duplicate slug `steplery`).
>
> Ruleset draft: `scratchpad/phase7a/tool_type.v1.json`
> (sha256 `8f31099127ca9413fdf60f7b45c3daed1a6af11d21830d904b6b964a7678eeb8`,
> 12 663 bytes).
> `ruleset_hash = canonical_hash`:
> `edb33cfca3886bc4a17cade026157671120470effd5754025f4fe993dda72ad6`.

Corpus: `staging-tool-type-6ebb8ac9d856`;
`artifact_content_hash = 81c15c5fbcb94c61c0ec2ff9dce7c14d42f5325c9068756c6e32bef69e37361d`
(canonical_hash(doc БЕЗ `extracted_at`), источник corpus_id, стабилен);
`loader_corpus_hash = 58566aef964b846d36fa644da7791c8a4fe0db79a9912dcdcaf0927191f752ce`
(поле `replay.corpus_hash` продакшн-кода: canonical_hash(полный dict
ВКЛЮЧАЯ `extracted_at`), volatile fingerprint файла). Разведение имён —
`extraction_report.hash_registry` (Stage 7, находка 5).
sha256 файла corpus: `d5c0117e737db4b31149c237b60aebc7f02dbb0249da71e42089fb16703b0311`.

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

## Правила (11 candidate; статусы после Stage 7 review)

Правила 1–10 — **APPROVED** (2026-07-21; №6 и №7 — approved with
monitoring: precision этих правил отдельно показать в Phase 7B).
Правило 11 — **REWRITTEN** после review (исходная версия rejected).

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

### 11. tt-yashchiki-sumki-keys-prochee → yashchiki-sumki — REWRITTEN (v1 rejected) [narrow]
- **История:** v1 `tt-yashchiki-sumki-keys-sumka` (`[сумка, кейс] ×
  [Бензоинструмент, Прочее]`, derived_from=[1855, 30223, 30225]) —
  **REJECTED** на Stage 7: декартово обобщение давало неподтверждённые
  комбинации «кейс × Бензоинструмент» и «сумка × Прочее»; fixture
  проверял только отсутствие слов, но не cross-комбинации.
- **v2 (по рецепту ревью, дословно):** оставлена только подтверждённая
  пара кейс + Прочее.
- Группа: 30223, 30225 («Кейс пластиковый Hitachi …», sg «Прочее»).
- Измерения: `source_group_any=[Прочее]`, `original_name_keywords_any=[кейс]`.
- `derived_from=[30223, 30225]` (ровно 2 → narrow).
- Товар 1855 («Сумка для бензопилы CHAMPION») — сознательно синглтон без
  правила до появления второго подтверждённого примера (P0.2 сохраняется).
- Fixtures: `fix-svechi-1817` (товар 1817, sg вне области правила),
  `fix-sumka-1855` (товар 1855 — сама отклонённая cross-комбинация,
  регистрирует, что «сумка» правилом не покрывается).

## Непокрытые товары (22 no_match)

21 товар — label-синглтоны (P0.2: нет ≥ 2 derived_from → нет candidate
правила). Плюс 1855 — de-scoped по решению Stage 7. Создание keyword-only
`shadow_regression` правил из одного примера — спекулятивно, не влияет на
replay (candidate-only); отложено (решение Stage 7: не создавать в v1).

## Отклонения от baseline

- DEVIATION-1 (F6): `changes_total = 57` (applied 56 + rejected 1) против
  ожидавшихся в истории сессии 58 (2 rejected). На corpus не влияет
  (applied-only контур сошёлся 56/54). **ACCEPTED пользователем как
  non-blocking data finding (Stage 7, 2026-07-21).**
- DEVIATION-2 (Stage 7 находка 6): taxonomy export — 328 строк, 327
  уникальных slug; slug `steplery` продублирован («Степлеры и
  заклёпочники» / «Степлеры (скобозабивные)») → в БД две записи
  AttributeOption с одинаковым slug. Root cause (локальный код):
  `AttributeOption.Meta.unique_together = [(attribute, value)]` — slug не
  уникален; apply по slug использует `.filter(...).first()` без order_by
  (`processing.py:328`, `:581`) — выбор записи недетерминирован
  контрактом. На текущие 11 правил влияния нет (slug не используется).
  Расследование (PK, sort_order, PAV-ссылки, канонический option) — до
  Phase 7B; исправление — отдельная авторизация.
- Иных отклонений: нет (counters 56/54/54/2 сошлись, exclusions = 0,
  инварианты pre ≡ post).

## Replay v2 (informational, НЕ gate; training leakage по построению)

Повторный replay после rework (та же продакшн-логика `Command._replay`):

- `measured_recall = 0.5926` (32/54 correct) — совпало с прогнозом
  ревью (32/54 = 0.592592…).
- Mismatches: 22 — ВСЕ `no_match` (21 синглтон + 1855); wrong-slug
  predictions = 0; rule-коллизии = 0; hits == derived_from для всех 11
  правил; `check_negative_fixtures == []`; `validate_against_taxonomy
  == []`; `derived_from ⊆ corpus` — все проверки пройдены повторно.
- Recall НЕ доказывает precision; gate 6.1 — Phase 7B на независимой
  выборке ≥ 100 predictions.

### F11: measured < 0.90 — ACCEPTED under option (a) (Stage 7, 2026-07-21)

Потолок структурный: 21/54 синглтонов × P0.2 + 1855 de-scoped →
32/54 = 0.5926. Решение пользователя для Decision Log (дословно):
«The candidate-tier recall ceiling is structurally limited by P0.2:
21 of 54 corpus items belong to singleton labels and cannot produce
candidate rules requiring at least two independent derived_from items.
All uncovered items are no_match. Wrong-slug predictions = 0.
Rule collisions = 0.» Плюс 1855 — сознательное непокрытие после
отклонения cross-product (безопасность > покрытие).

### expected_recall — предложение после повторного replay

Ревью: `expected_recall = 0.6111` — **NOT APPROVED** (значение стало
неверным после rework правила). Рекомендованный threshold ревью:
**`expected_recall = 0.59`**, формально утверждается ПОСЛЕ нового replay.
Replay v2 выполнен: measured `0.5926 ≥ 0.59` — условие соблюдено,
threshold `0.59` готов к финальному утверждению пользователем.
Автоматическая запись в fixture ЗАПРЕЩЕНА (P0-2); поле появится в repo
fixture только после строки approval в Decision Log.

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
| expected_recall=0.6111 rejected; threshold 0.59 recommended после нового replay | значение устарело после rework; replay v2: 0.5926 ≥ 0.59 | 2026-07-21 (пользователь, Stage 7) |
| corpus hash ambiguity → hash_registry | два алгоритма (artifact_content_hash / loader_corpus_hash) разведены по именам, зафиксированы | 2026-07-21 (пользователь находка 5; analyst rework) |
| DEVIATION-2 (duplicate slug steplery) recorded | 328 rows / 327 unique slugs; расследование до Phase 7B; исправление — отдельная авторизация | 2026-07-21 (пользователь находка 6; analyst rework) |
| expected_recall = 0.59 — FINAL approval | replay v2 measured 0.5926 ≥ 0.59 | pending (финальное слово пользователя) |
| rules v2 (11 шт.) — финальное закрытие Stage 7 + разрешение PR с fixtures | rework проверен | pending (финальное слово пользователя) |
