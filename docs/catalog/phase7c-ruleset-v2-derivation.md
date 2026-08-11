# Phase 7C — Derivation tool_type.v2 candidate rules

Статус: **Stage 2.7 per-rule review завершён; draft v2 собран и прошёл
локальную валидацию (Stage 3.1–3.7); Stage 4.1–4.3 выполнен: note финализирован,
хэши запинены (pin table ниже)**. Commit, staging, Stage 5/6, официальный
gate — НЕ авторизованы (ожидается решение на checkpoint Stage 4.4).
Дата: 2026-07-22. Исполнитель: кодовый агент; решения по правилам — reviewer (human).

> «Monitoring» — статус review/documentation (обязательная проверка строк
> в gate sample Phase 7D), а НЕ новый runtime tier и НЕ поле схемы ruleset.

## Основание

- Dataset: `phase7c-nomatch-pool.json`, sha256 `0b5a3722…`, pool=all
  (pool_size=1593, no_match=1530), ruleset `tool_type.v1` hash `51b3bbad…`.
- Таксономия: staging snapshot 328 options, hash `b357be60…` (Stage 0).
- Matcher: семантика `apps.catalog.rules_engine` (token/prefix,
  `original_name_keywords_any` матчит только `original_name`,
  многословный keyword = подряд идущие токены, последний — prefix).
- Проверка: локальная симуляция + Stage 3 dry-run реальным engine
  (`scratchpad/phase7c/phase7c-simulation.md`, `phase7c-stage3-dryrun.txt`).

Все правила: ровно 2 измерения (`source_group_any` + `original_name_keywords_any`),
объяснимы одной фразой, precision > recall. Все slug'и сверены со staging
snapshot таксономии; для спорных маппингов выполнены read-only проверки
текущего наполнения slug'ов (`phase7c-slug-usage.txt`, `phase7c-slug-samples.txt`,
`phase7c-slug-samples2.txt`).

Общие свойства контура:

- яя-префикс в `original_name` блокирует token-match — такие товары
  остаются no_match by design (известное ограничение matcher,
  не свойство категории — решение reviewer по правилу 1);
- same-slug multi-match с правилами v1 допустим (прецедент 7B):
  правило 21 (`siz-ochki`) пересекается с v1 `маска щиток` по токену «щиток» —
  тот же slug, не коллизия; подтверждено corpus regression
  (3 items: 36300, 36302, 36304 → [tt-siz-ochki-shitok, tt-siz-ochki-zashchitnye]);
- rules 10 и 20 используют slug'и правил v1 (`nabory-instrumenta`,
  `yashchiki-sumki`), но с непересекающимися измерениями — коллизий нет.

## Итог review Stage 2.7

- APPROVED: 19 правил (1–4, 6, 7, 9–12, 14–16, 18, 19, 21, 23, 24);
- APPROVED WITH MONITORING: 7 правил (5, 8, 13, 17, 20, 22, 26);
- MODIFIED → APPROVED: правило 25 (keyword «пояс для» → «пояс для инструмента»);
- REJECTED: правила 28 (→ taxonomy_gap), 29 (catch-all slug);
- В v2 вошло: **27 новых правил**; состав файла: v1 (11) verbatim + 27 = 38 rules;
  fixtures: v1 (12) verbatim + 27 = 39.

## Правила (29 карточек; 27 вошли в v2)

### 1. tt-hoz-izolenta-izolenta → hoz-izolenta — APPROVED
- dimensions: sg=[Хозтовары, сад, огород]; kw=[изолента]
- derived_from: 39790, 39791; predictions (dry-run): **27**
- объяснение: изолента в хозяйственной группе — это hoz-izolenta.
- negative fixture: fix-izolenta-lom-40677 (40677 «Лом строительный…», sg=Хозтовары).
- решение reviewer: изолента однозначна внутри группы; исключение яя-вариантов
  (43480–43487) — известное ограничение matcher, не свойство категории.

### 2. tt-lomy-gvozdodery-lom → lomy-gvozdodery — APPROVED
- dimensions: sg=[Хозтовары, сад, огород; Строительно-отделочный инструмент]; kw=[лом, гвоздодер]
- derived_from: 40677, 37013; predictions: **20**
- объяснение: ломы и гвоздодёры в двух смежных группах — один tool_type.
- negative fixture: fix-lomy-izolenta-39790 (39790 «Изолента…», sg=Хозтовары).
- решение reviewer: контрольных примеров достаточно.

### 3. tt-obor-nasosy-nasos → obor-nasosy — APPROVED
- dimensions: sg=[Электроинструмент]; kw=[насос]
- derived_from: 44271, 44276; predictions: **30**
- объяснение: электрические насосы (дренажные/вибрационные) — это obor-nasosy.
- negative fixture: fix-nasosy-gazonokosilka-43773 (43773, sg=Электроинструмент).
- решение reviewer: электрические насосы и насосные станции соответствуют obor-nasosy.

### 4. tt-bp-gazonokosilki-gazonokosilka → bp-gazonokosilki — APPROVED
- dimensions: sg=[Электроинструмент; Аккумуляторный инструмент]; kw=[газонокосилка]
- derived_from: 43773, 429; predictions: **18**
- объяснение: электро- и аккумуляторные газонокосилки — тот же tool_type, что бензиновые.
- negative fixture: fix-gazonokosilki-nasos-44221 (44221, sg=Электроинструмент).
- решение reviewer: тип инструмента не зависит от источника питания.

### 5. tt-svar-apparaty-truby → svar-apparaty — APPROVED WITH MONITORING
- dimensions: sg=[Электроинструмент]; kw=[аппарат для сварки]
- derived_from: 43680, 43691; predictions: **10**
- объяснение: аппараты для сварки полимерных труб — сварочные аппараты.
- negative fixture: fix-svar-nasos-44271 (44271, sg=Электроинструмент).
- решение reviewer: пограничный подтип относительно металлообработки;
  все 10 строк проверить в gate sample, если попадут в выборку (Phase 7D).

### 6. tt-fonari-akkum → fonari — APPROVED
- dimensions: sg=[Аккумуляторный инструмент]; kw=[фонарь]
- derived_from: 665, 671; predictions: **12** (1087 «яяФонарь…» не матчится — by design)
- объяснение: аккумуляторные рабочие фонари — это fonari.
- negative fixture: fix-fonari-trimmer-652 (652, sg=Аккумуляторный).
- решение reviewer: прямое соответствие.

### 7. tt-bp-trimmery-akkum → bp-trimmery — APPROVED
- dimensions: sg=[Аккумуляторный инструмент]; kw=[триммер]
- derived_from: 652, 656; predictions: **7**
- объяснение: аккумуляторные триммеры — тот же tool_type, что бензиновые.
- negative fixture: fix-trimmery-fonar-665 (665, sg=Аккумуляторный).
- решение reviewer: корректное объединение.

### 8. tt-bp-vozdukhoduvki-akkum → bp-vozdukhoduvki — APPROVED WITH MONITORING
- dimensions: sg=[Аккумуляторный инструмент]; kw=[воздуходувка]
- derived_from: 422, 423; predictions: **4** (1064/1065 «яяВоздуходувка…» не матчатся)
- объяснение: аккумуляторные воздуходувки — тот же tool_type, что бензиновые.
- negative fixture: fix-vozdukhoduvki-gazonokosilka-429 (429, sg=Аккумуляторный).
- решение reviewer: семантика точная, support всего 4 → monitoring.

### 9. tt-krep-takelazh-styazhka → krep-takelazh — APPROVED
- dimensions: sg=[Автомобильный инструмент]; kw=[стяжка груза, трос ленточный]
- derived_from: 302, 361; predictions: **27**
- объяснение: стяжки груза и буксировочные ленточные тросы — такелаж.
- negative fixture: fix-takelazh-tros-369 (369 «Трос металлополимерный…», sg=Автомобильный).
- соседи-не-захватывать: 333 «Стяжка пружин…» — корректно исключена двухсловным keyword.
- решение reviewer: двухсловные ключи правильно разделяют семейства.

### 10. tt-nabory-instrumenta-zvezdochki → nabory-instrumenta — APPROVED
- dimensions: sg=[Наборы инструмента]; kw=[набор звездочек]
- derived_from: 22670, 22671; predictions: **9**
- объяснение: наборы торцевых звёздочек — наборы инструмента
  (тот же slug, что v1 dielektr; измерения не пересекаются).
- negative fixture: fix-zvezdochki-shaiby-23255 (23255 «Набор медных шайб…» = v1 fix-shaiby-23255).
- решение reviewer: узкий keyword и отдельная sg дают достаточную precision.

### 11. tt-sterzhni-kleevye-kleevye → sterzhni-kleevye — APPROVED
- dimensions: sg=[Слесарно-столярный инструмент]; kw=[стержни клеевые]
- derived_from: 34635, 34647; predictions: **8**
- объяснение: клеевые стержни — расходник к клеевым пистолетам.
- negative fixture: fix-sterzhni-tonkonosy-35059 (35059, sg=Слесарно-столярный).
- решение reviewer: прямое соответствие.

### 12. tt-passatizhi-tonkonosy → passatizhi — APPROVED
- dimensions: sg=[Слесарно-столярный инструмент]; kw=[тонконосы]
- derived_from: 35059, 35060; predictions: **6**
- объяснение: тонконосы — подтип плоскогубцев/пассатижей.
- negative fixture: fix-tonkonosy-sterzhni-34635 (34635, sg=Слесарно-столярный).
- решение reviewer: подтверждено.

### 13. tt-obor-mebel-verstak → obor-mebel — APPROVED WITH MONITORING
- dimensions: sg=[Слесарно-столярный инструмент]; kw=[верстак]
- derived_from: 31973, 31976; predictions: **4**
- объяснение: верстаки — прямое попадание в slug.
- negative fixture: fix-verstak-tonkonosy-35060 (35060, sg=Слесарно-столярный).
- решение reviewer: прямое соответствие, support 4 → monitoring.

### 14. tt-payalniki-elektro → payalniki — APPROVED
- dimensions: sg=[Осветительное и электротехническое оборудование]; kw=[паяльник]
- derived_from: 24703, 24705; predictions: **15**
- объяснение: электрические паяльники — прямое попадание в value slug'а
  (payalniki = паяльники, подтверждено staging: 44399–44401;
  payalniki-stancii де-факто смешан).
- negative fixture: fix-payalniki-pripoy-24855 (24855 «Припой…», sg=Осветительное).
- решение reviewer: выбор payalniki обоснован текущим содержимым taxonomy.

### 15. tt-raskhodniki-pajki-pripoy → raskhodniki-pajki — APPROVED
- dimensions: sg=[Осветительное и электротехническое оборудование]; kw=[припой]
- derived_from: 24855, 24867; predictions: **10**
- объяснение: припой — однозначный расходник для пайки.
- negative fixture: fix-pripoy-payalnik-24703 (24703 «Паяльник…», sg=Осветительное).
- решение reviewer: подтверждено.

### 16. tt-izm-ruletki-mernaya-lenta → izm-ruletki — APPROVED
- dimensions: sg=[Измерительный инструмент]; kw=[лента мерная]
- derived_from: 10819, 10823; predictions: **6**
- объяснение: геодезическая мерная лента = рулетка (прецедент: 11458/11464).
- negative fixture: fix-ruletki-koleso-10807 (10807 «Колесо дорожное…», sg=Измерительный).
- решение reviewer: корректная классификация.

### 17. tt-izm-kolesa-dorozhnoe → izm-kolesa — APPROVED WITH MONITORING
- dimensions: sg=[Измерительный инструмент]; kw=[колесо дорожное]
- derived_from: 10807, 10808; predictions: **4**
- объяснение: дорожное колесо = измерительное колесо (курвиметр);
  двухсловный keyword снимает риск обычных колёс.
- negative fixture: fix-kolesa-lenta-10819 (10819 «Лента мерная…», sg=Измерительный).
- решение reviewer: support 4 → monitoring.

### 18. tt-bp-podgotovka-vozduha-vlagootdelitel → bp-podgotovka-vozduha — APPROVED
- dimensions: sg=[Пневмоинструмент]; kw=[влагоотделитель, регулятор давления]
- derived_from: 28320, 29034; predictions: **5** (3 влагоотделителя + 2 регулятора)
- объяснение: влагоотделители и регуляторы давления — FRL-подготовка воздуха
  (прецедент: 28319, 29132).
- negative fixture: fix-vlagootdelitel-pika-28677 (28677 «Пика к отбойному молотку…»
  = v1 fix-pnevmomolotok-28677).
- решение reviewer: подтверждено.

### 19. tt-zap-svechi-zazhiganiya → zap-svechi — APPROVED
- dimensions: sg=[Бензоинструмент и расходники для них]; kw=[свеча зажигания]
- derived_from: 1818, 1819; predictions: **5**
- объяснение: свечи зажигания для 2/4-тактных двигателей — zap-svechi.
- negative fixture: fix-svechi-sumka-1856 (1856 «Сумка для бензопилы…», sg=Бензоинструмент).
- решение reviewer: прямое соответствие.

### 20. tt-yashchiki-sumki-benzopila → yashchiki-sumki — APPROVED WITH MONITORING
- dimensions: sg=[Бензоинструмент и расходники для них]; kw=[сумка для бензопилы]
- derived_from: 1856, 1857; predictions: **4**
- объяснение: сумки для бензопил — сумки/органайзеры; второе подтверждение
  cross-комбинации, отложенной v1 review (fix-sumka-1855).
- negative fixture: fix-sumka-svecha-1818 (1818 «Свеча зажигания…», sg=Бензоинструмент).
- решение reviewer: узкий трёхсловный keyword, достаточное второе подтверждение.

### 21. tt-siz-ochki-shitok → siz-ochki — APPROVED
- dimensions: sg=[Средства индивидуальной защиты]; kw=[щиток]
- derived_from: 36877, 36881; predictions: **5**
- объяснение: лицевые защитные щитки — тот же slug, что маски-щитки v1.
- negative fixture: fix-shitok-champion-2069 (2069 «Щиток защитный сетчатый CHAMPION»,
  sg=Бензоинструмент — щиток вне СИЗ не матчится).
- same-slug multi-match с tt-siz-ochki-zashchitnye: подтверждён corpus regression
  (36300, 36302, 36304), не коллизия — зафиксировано в Stage 3 evidence.
- решение reviewer: соответствует значению slug.

### 22. tt-siz-pozh-inventar-polotno → siz-pozh-inventar — APPROVED WITH MONITORING
- dimensions: sg=[Пожарка]; kw=[полотно противопожарное]
- derived_from: 29733, 29734; predictions: **3**
- объяснение: противопожарные полотна — пожарный инвентарь.
- negative fixture: fix-polotno-gromkogovoritel-29557 (29557 «Громкоговоритель…», sg=Пожарка).
- решение reviewer: семантика точная, support 3 → monitoring.

### 23. tt-bp-kompressory-avto → bp-kompressory — APPROVED
- dimensions: sg=[Автомобильный инструмент]; kw=[компрессор]
- derived_from: 180, 192; predictions: **10**
- объяснение: автомобильные 12В компрессоры — тот же tool_type, что стационарные
  (прецедент: 28364).
- negative fixture: fix-kompressory-styazhka-302 (302 «Стяжка груза…», sg=Автомобильный).
- решение reviewer: компрессоры независимо от напряжения и исполнения.

### 24. tt-obor-pena-shampun → obor-pena — APPROVED
- dimensions: sg=[Герметики, пены, клеи и пр отделочные материалы]; kw=[шампунь]
- derived_from: 6214, 6217; predictions: **5**
- объяснение: шампуни для минимоек — автохимия внутри obor-pena (прецедент: 6213).
- negative fixture: fix-shampun-antikor-5315 (5315 «Антикор полимерно-битумный…»,
  sg=Герметики — строка без целевого keyword «шампунь»).
- решение reviewer: соответствие подтверждено; формулировка fixture скорректирована
  (без утверждения о семантике продукта 5315).

### 25. tt-sumki-poyasnye-podsumok → sumki-poyasnye — MODIFIED → APPROVED
- dimensions: sg=[Средства индивидуальной защиты]; kw=[подсумок, **пояс для инструмента**]
  (изменено reviewer: «пояс для» слишком широко — «пояс для работы на высоте»
  попал бы ошибочно)
- derived_from: 36660, 36708; predictions: **3** (было 4; пересчёт после сужения:
  36709 «Пояс для подсумка, кобуры…» более не матчится — «подсумка» не покрывается
  prefix «подсумок», «пояс для подсумка» ≠ «пояс для инструмента»;
  зафиксирован фактический результат, правило не подгонялось)
- объяснение: подсумки и инструментальные пояса — поясные сумки.
- negative fixture: fix-podsumok-poyas-36720 (36720 «Пояс монтерский ПМ-20», sg=СИЗ).
- соседи-не-захватывать: 36720, 36721 (монтерские), 36709 (пояс для подсумка —
  осознанная потеря recall ради precision).
- решение reviewer: после изменения keyword — approved.

### 26. tt-siz-izveshchateli-gromkogovoritel → siz-izveshchateli — APPROVED WITH MONITORING
- dimensions: sg=[Пожарка]; kw=[громкоговоритель]
- derived_from: 29557, 29558; predictions: **3**
- объяснение: рупорные громкоговорители — устройства оповещения
  (значение taxonomy прямо включает «оповещатели»).
- negative fixture: fix-gromkogovoritel-polotno-29733 (29733 «Полотно противопожарное…», sg=Пожарка).
- решение reviewer: допустимо; monitoring обязателен — нет текущего прецедента
  в наполнении slug.

### 27. tt-kobury-dlya-instrumenta-kobura → kobury-dlya-instrumenta — APPROVED
- dimensions: sg=[Средства индивидуальной защиты]; kw=[кобура]
- derived_from: 36136, 36140; predictions: **2**
- объяснение: кобуры для шуруповёртов — буквальное соответствие slug
  (36137–36139 уже в slug).
- negative fixture: fix-kobura-podsumok-36660 (36660 «Подсумок поясной…», sg=СИЗ).
- решение reviewer: несмотря на support 2, соответствие буквальное и прецедент
  в наполнении slug есть — сильнее обычного singleton-кандидата.

### 28. tt-zap-korpusa-kryshki-karter → zap-korpusa-kryshki — REJECTED → taxonomy_gap
- предполагалось: sg=[Запасные части Хитачи]; kw=[картер]; 7 predictions.
- решение reviewer: картер действительно корпусная деталь, но текущая taxonomy
  не подтверждает, что zap-korpusa-kryshki должен включать картеры (0 прецедентов
  в наполнении slug — проверено staging). Не расширять смысл slug догадкой.
  Кластер (7 строк: 8507–8513) перенесён в **taxonomy_gap**.

### 29. tt-prochaya-osnastka-tarelka → prochaya-osnastka — REJECTED
- предполагалось: sg=[Запасные части]; kw=[тарелка опорная]; 6 predictions.
- решение reviewer: prochaya-osnastka — catch-all на 2041 товар; использование
  такого slug скрывает отсутствие нормального типа для опорных тарелок и ухудшает
  управляемость taxonomy. Кластер (6 строк: 7269–7275) остаётся no_match
  до отдельного taxonomy-решения.

## Singleton-кластеры (support < 3, правила не предложены)

- «пояс монтерский» (36720, 36721) — 2 строки + slug-неоднозначность
  (siz-vysota / sumki-poyasnye рассогласованы, см. правило 25).

## Неоднозначные кластеры (правила не предложены)

- «вал гибкий / вибронаконечник» @ Строительное оборудование — 11 строк:
  части глубинных вибраторов, а не машины; slug `vibratory-betona` содержит
  только машины (проверено: 43740–43748, 38358–38363). Нужно решение по
  таксономии (вне scope 7C).
- «пояс монтерский» — см. singleton.

## taxonomy_gap (slug отсутствует; создание options вне scope 7C)

- рукоятки для ЭЛЕКТРОинструмента (Хитачи/дядько склад) — 32 строки:
  slug `rukoyatki-dlya-instrumenta` семантически занят рукоятками для РУЧНОГО
  инструмента (проверено: 41957–41962 деревянные для кувалд).
- радиостанции Motorola TLKR @ Электроинструмент — 12 строк (9 token-matchable).
- щетки бескаркасные для стекол (дворники) @ Автомобильный — 7 строк.
- валы запчастей @ Хитачи — 21 строка (после отказа от правила из-за FP «вальцы»).
- боек ударного механизма @ Хитачи/Запчасти — ~10 строк (вкл. 6702 «Боек»).
- глушитель (~6), маслонасос (~6) @ Хитачи.
- головка триммерная @ Запчасти — 3 строки.
- режущая пластина для бензокос — 4 строки.
- ЭХО запчасти бензопил — 10 строк.
- **картер КШМ @ Хитачи — 7 строк (per Stage 2.7 review, правило 28 REJECTED).**

## Отклонённые кластеры (rejected, с причинами)

- «рукоятка» → rukoyatki-dlya-instrumenta (32): семантика slug'а = рукоятки
  РУЧНОГО инструмента (подтверждено staging), кластер = запчасти электроинструмента
  → taxonomy_gap, а не stretch.
- «вал» → zap-shpindeli-valy (21): prefix-match ловит 8045 «Вальцы (сухарики)» —
  известный FP; переработка на multi-word keywords фрагментирует кластер
  (ведущий/вторичный/триммера/шпинделя…) → precision>recall: reject.
- «вал гибкий/вибронаконечник» → vibratory-betona (11): части ≠ машины (см. выше).
- «патрубок д/пылесосов» → obor-shlangi (3): semantic stretch + низкая ценность.
- «пресс-масленки» @ Смазочное оборудование (3): строки — приспособления
  и наборы сменных ниппелей (35646, 35773, 35774), не пресс-маслёнки;
  obor-smazka был бы неточным.
- **«картер» → zap-korpusa-kryshki (7): REJECTED на Stage 2.7 — taxonomy не
  подтверждает включение картеров; перенесён в taxonomy_gap.**
- **«тарелка опорная» → prochaya-osnastka (6): REJECTED на Stage 2.7 —
  catch-all slug скрывает отсутствие нормального типа.**

## Итоговая оценка yield (после Stage 2.7 + Stage 3.7 dry-run)

- В v2 вошло 27 новых правил; состав: 38 rules, 39 fixtures (v1-часть verbatim,
  parsed diff = ∅).
- new_independent (локальная оценка, Stage 3.7 dry-run на dataset):
  **262** (= 276 − 7 (rule 28) − 6 (rule 29) − 1 (сужение rule 25));
  `new_rule_overlap = 0`; v1-правила на dataset дают 0 (by construction).
- Без monitoring-правил (5, 8, 13, 17, 20, 22, 26): 262 − 32 = **230**.
- Целевой коридор 120–150+ new_independent: **выполнен с запасом**
  (262 > 150; даже 230 > 150); доказательство исчерпания кластеров не требуется.
- Прогноз v2 shadow (Stage 5, не авторизован): 63 + 262 = 325 predictions;
  gate sample 100 — выполним.

## Stage 3 validation summary (локально, draft note)

- 3.2 `load_ruleset`: OK; ruleset_hash (draft) `14aab84b…` — НЕ pin
  (изменится после финализации note в Stage 4);
- 3.3 `check_negative_fixtures`: 0 violations;
- 3.4 `validate_against_taxonomy` (328 options snapshot): 0 missing slugs;
- 3.5 corpus regression: correct=37/54 (baseline v1 = 32; рост +5 за счёт новых
  правил — зафиксирован, `expected_recall=0.59` не пересматривается),
  collisions=0, wrong_slug=0; same-slug multi-match: 3 items (36300, 36302,
  36304 → tt-siz-ochki-shitok + tt-siz-ochki-zashchitnye, slug siz-ochki);
- 3.6 rules-ветка тестов: 93 passed, 1 skipped;
- 3.7 dry-run: predicted=262, new_rule_overlap=0.

## Stage 4 freeze (4.1–4.3)

- 4.1 note финализирован: `"approved 2026-07-22, Phase 7C Stage 2.7 per-rule
  review (27/29 rules accepted, incl. 1 modified); base tool_type.v1 + 27 new rules"`;
- 4.2 pinning выполнен ПОСЛЕ финализации note (canonical hash — из `load_ruleset`;
  byte sha256 — LF-представление, урок F-1 фазы 7B):
- 4.3 повторные проверки после финализации note — все зелёные:
  `load_ruleset` OK; fixtures 0 violations; taxonomy 0 missing;
  v1-часть parsed deep-equality (rules + fixtures) = True.

### Pin table (tool_type.v2, FINAL)

| Артефакт | Значение |
|---|---|
| ruleset_id / version | `tool_type.v2` / 1 |
| rules / fixtures | 38 (11 v1 verbatim + 27 new) / 39 (12 v1 verbatim + 27 new) |
| new_independent estimate (Stage 3.7 dry-run) | 262 |
| **canonical ruleset_hash** | `9bf0271a61e729a900cda57705bdf785b96496efc462448894b27650a04bf330` |
| **LF byte sha256** (Git blob reference) | `ff449701939e993e6bf3e0d68de20d07a672884a54df602c7b2807316f8728ec` |
| working-copy (CRLF) sha256, справочно | `5c12db44bc73813ec27f980b1ac593411adb0960358950e7830d0901cf590f66` |

CRLF-хэш рабочей копии — platform-specific, НЕ использовать как cross-platform
integrity reference (прецедент F-1 фазы 7B); канонический byte-референс — LF.

Commit (Stage 4.5) — **не авторизован**; ожидается решение на checkpoint 4.4.
