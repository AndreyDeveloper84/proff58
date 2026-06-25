# Runbook: прогон таксономии v2 по всему каталогу (`catalog_build_section`)

Пошаговый сценарий разворачивания v2-дерева каталога на **всех node-разделах**:
создать узлы из словарей, расселить товары по смыслу названия (high-confidence),
сгенерировать авто-правила для новых товаров 1С (E2). Рассчитан на **staging**;
на прод — тем же порядком после приёмки.

> Источники: словари `data/product_type_rules*.json`, команды
> `apps/catalog/management/commands/catalog_build_section.py` и
> `catalog_sync_rules.py`, карта разделов `apps/catalog/semantic.py::SECTION_RULES`.
> План v2 — `docs/plans/catalog-taxonomy-v2.md`.

---

## 0. Что делает прогон (и чего НЕ делает)

`catalog_build_section --section <slug> --commit`:

1. создаёт узлы 2-го (и 3-го для Оснастки) уровня раздела (имена из словаря,
   slug — латиница), корень — из `section`/`section_slug` словаря;
2. расселяет товары с **high-confidence**-классификацией в нужный узел и ставит
   `category_is_manual=True` (защита от перезаписи импортом 1С, ADR-0007);
3. товары `category_is_manual=True` (уже размеченные вручную/предыдущим разделом)
   **пропускает** — отсюда важность порядка (см. §2);
4. пишет снимок отката `var/restructure/build-<section>-<ts>.json`;
5. на commit шлёт `product_updated` (через `on_commit`) — на staging Celery
   реальный, поэтому поедут подписчики (реиндекс/кэши).

**НЕ делает:** не меняет `is_visible`/`status`/цены/остатки; medium/low-классификацию
не трогает (очередь модерации); чужой ручной разбор не перетирает. Видимость
товара — отдельный шаг (`publish_catalog`, §6).

`catalog_sync_rules --section <slug> --commit` (E2): генерирует
`CategoryMappingRule(rule_type=REGEX)` из того же словаря на построенные узлы, чтобы
**новые** товары 1С автоматически попадали в те же узлы при импорте.

---

## 1. Предусловия (выполнить один раз перед прогоном)

```bash
# 1.1 Зайти на staging-хост, в каталог проекта. Все команды — внутри контейнера web.
#     Ниже COMPOSE = "docker compose -f docker-compose.prod.yml" (как в scripts/backup.sh).

# 1.2 ОБЯЗАТЕЛЬНО: свежий бэкап БД (откат на случай форс-мажора целиком).
bash scripts/backup.sh
#   → db-<ts>.sql.gz в $BACKUP_DIR. Проверь, что файл создан и весит адекватно.

# 1.3 Проверить, что словари на месте (должно быть 13) и код задеплоен.
docker compose -f docker-compose.prod.yml exec web ls data/ | grep -c product_type_rules
docker compose -f docker-compose.prod.yml exec web python manage.py help catalog_build_section >/dev/null && echo "команда есть"

# 1.4 Снять «до»-срез дерева для сравнения (аудит пишет отчёты в docs/reports).
docker compose -f docker-compose.prod.yml exec web python manage.py catalog_taxonomy_audit --print | tee /tmp/audit-before.txt
```

> Везде далее: `WEB="docker compose -f docker-compose.prod.yml exec web python manage.py"`.

---

## 2. Порядок разделов (НЕ менять без причины)

Принцип: **специфичное → общее**, **техника → запчасти/хранение**. Кто первый
разметил товар (`category_is_manual=True`), тот и владелец; общие разделы
(Запчасти, Хранение) идут последними, чтобы не перехватывать профильные товары.

| # | slug | раздел | почему здесь |
|---|---|---|---|
| 1 | `osnastka` | Оснастка | самый специфичный лексикон (буры, диски, биты) |
| 2 | `krepezh` | Крепёж | болт/гайка/саморез — узкие термины |
| 3 | `izmeritelnyy` | Измерительный | приборы с однозначными названиями |
| 4 | `svarka` | Сварка | «сварочн…», электроды |
| 5 | `elektrika` | Электрика и освещение | кабель/розетка/лампа |
| 6 | `silovaya` | Силовая, пневмо, компрессоры | генератор/компрессор/насос |
| 7 | `avto` | Автоинструмент | домкрат/съёмник (до Запчастей!) |
| 8 | `sadovaya` | Садовая техника | газонокос/триммер/бензопила (до Запчастей!) |
| 9 | `stroitelnyy` | Строительный/отделочный | ЛКМ, шпатели, валики |
| 10 | `siz` | СИЗ | перчатки/очки/каска |
| 11 | `hranenie` | Хранение | кейсы/сумки/тележки — «общий» инвентарь |
| 12 | `zapchasti` | Запчасти, аккумуляторы | аккумуляторы/подшипники — последними |
| 13 | `ruchnoy` | Ручной инструмент | широкие термины (ключ/нож/головка) — в конце |

> **Электроинструмент** в этот runbook НЕ входит: это facet-раздел по `tool_type`
> (навигация TypePanel уже на dev), узлы дерева для него не строим.
> **Внутренняя часть Садовой** («Садовая техника» как набор типов) — гибрид;
> здесь строим только node-узлы из словаря `sadovaya`.

---

## 3. Шаблон шага на ОДИН раздел

Повторить для каждого `<slug>` строго в порядке §2. Пример на `osnastka`.

```bash
# 3.1 DRY-RUN — ничего не меняет, печатает узлы и сколько товаров привяжет.
$WEB catalog_build_section --section osnastka | tee /tmp/dry-osnastka.txt
```

**Что проверить в dry-run перед commit:**
- «создать узлов ~N» — соответствует словарю (нет мусорных узлов);
- «привязать товаров M» — порядок величины ожидаемый (ориентиры — таблица в PR #243);
- «пропущено ручных (category_is_manual) K» — на 1-м разделе ≈0, далее растёт
  (это и есть работа порядка: товар уже занят более специфичным разделом);
- нет узла с подозрительно огромным числом (признак жадного ключевого слова).

```bash
# 3.2 COMMIT — в транзакции, со снимком отката.
$WEB catalog_build_section --section osnastka --commit | tee /tmp/commit-osnastka.txt
#   → запомни путь снимка: var/restructure/build-osnastka-<ts>.json  (нужен для отката)

# 3.3 E2 — авто-правила для новых товаров 1С этого раздела.
$WEB catalog_sync_rules --section osnastka | tee /tmp/dry-rules-osnastka.txt   # dry-run
$WEB catalog_sync_rules --section osnastka --commit                            # применить

# 3.4 VERIFY — точечная проверка раздела (см. §4).
```

> По умолчанию `build_section` берёт только `--min-confidence high`. Не понижать до
> `medium` в массовом прогоне — medium идёт в модерацию вручную.

---

## 4. Проверка после каждого раздела

```bash
# 4.1 Узлы и счётчики раздела (через shell). Пример для osnastka:
$WEB shell -c "
from apps.catalog.models import Category
root = Category.objects.get(slug='osnastka')
for n in root.get_descendants():
    print(f'{n.depth:>2} {n.name:40s} товаров={n.products.count()}')
print('ИТОГО в разделе:', sum(c.products.count() for c in root.get_descendants()))
"

# 4.2 Спот-чек на ложные срабатывания: 10 случайных названий из «подозрительного» узла.
$WEB shell -c "
from apps.catalog.models import Category
n = Category.objects.get(slug='<slug-узла>')
for p in n.products.order_by('?')[:10]:
    print(p.name)
"
```

**Критерий приёмки раздела:** счётчики совпадают с dry-run; в спот-чеке нет товаров
из чужого раздела; «пропущено ручных» растёт по мере продвижения по порядку.

После всех 13 разделов — общий аудит и сравнение с «до»:

```bash
$WEB catalog_taxonomy_audit --print | tee /tmp/audit-after.txt
diff /tmp/audit-before.txt /tmp/audit-after.txt | head -60
```

---

## 5. Откат

**Один раздел** (точечно, безопасно — восстанавливает прежние категории и удаляет
только пустые созданные узлы):

```bash
$WEB catalog_build_section --rollback var/restructure/build-<section>-<ts>.json
# авто-правила E2 раздела при необходимости снять отдельно:
$WEB shell -c "
from apps.catalog.models import CategoryMappingRule
CategoryMappingRule.objects.filter(note__startswith='[auto:<slug>]').delete()
"
```

**Всё целиком** (форс-мажор) — восстановить дамп БД из §1.2:

```bash
gunzip -c $BACKUP_DIR/db-<ts>.sql.gz | docker compose -f docker-compose.prod.yml exec -T db psql -U $POSTGRES_USER -d $POSTGRES_DB
```

---

## 6. Завершение прогона

```bash
# 6.1 Пересобрать кэш атрибутов/фасетов.
$WEB rebuild_attrs_cache

# 6.2 (опционально) Опубликовать новые расселённые товары, если нужно их показать.
#     build_section видимость НЕ меняет. Сначала dry-run, смотрим число.
$WEB publish_catalog --all --dry-run
$WEB publish_catalog --all          # применить (переводит imported/needs_review → published)

# 6.3 Отчёт покрытия характеристик по типам (для последующей характеризации).
$WEB coverage_report --format md > docs/reports/coverage-after-rollout.md
```

> Публикацию (6.2) согласовать с заказчиком: возможно, часть разделов должна
> оставаться скрытой до ручной модерации medium-классификации.

---

## 7. Известные нюансы (держать в голове на прогоне)

1. **`zapchasti:Аккумуляторы`** ловит аккумуляторный инструмент
   (*«Газонокосилка аккумуляторная»*). На массовом прогоне это лечит порядок:
   Садовая/Силовая/Авто идут раньше Запчастей и занимают такие товары первыми.
   Для **новых** товаров 1С (E2) этого недостаточно — кросс-секционная
   приоритизация авто-правил вынесена в отдельную задачу; до неё спот-чекать
   узел «Аккумуляторы» после импортов.
2. **Пустые узлы** (структура есть, товаров 0 на текущем срезе): Сварка→Сопла/Пайка,
   Силовая→Лебёдки/Виброплиты, Авто→Пуско-зарядные/Автохимия, Хранение→Тара/Крюки,
   Запчасти→Кнопки/Корпусные, СИЗ→Аптечки, Садовая→Снегоуборка, Электрика→Звонки.
   Это норма (структура ≠ снапшот); часть — кандидаты на расширение ключевых слов
   после анализа промахов.
3. **Идемпотентность.** Повторный `build_section --commit` того же раздела безопасен:
   существующие узлы переиспользуются, уже размеченные (manual) товары пропускаются.
4. **E2-правила** пересоздаются на каждом `sync_rules --commit` (note `[auto:<slug>]`);
   ручные `CategoryMappingRule` не трогаются.

---

## 8. Чек-лист прогона

- [ ] §1 Бэкап БД снят, словари (13) на месте, audit-before сохранён
- [ ] 1. osnastka — dry → commit → sync_rules → verify
- [ ] 2. krepezh
- [ ] 3. izmeritelnyy
- [ ] 4. svarka
- [ ] 5. elektrika
- [ ] 6. silovaya
- [ ] 7. avto
- [ ] 8. sadovaya
- [ ] 9. stroitelnyy
- [ ] 10. siz
- [ ] 11. hranenie
- [ ] 12. zapchasti
- [ ] 13. ruchnoy
- [ ] §4 Общий audit-after, diff просмотрен
- [ ] §6 rebuild_attrs_cache; публикация согласована/выполнена; coverage-отчёт снят
