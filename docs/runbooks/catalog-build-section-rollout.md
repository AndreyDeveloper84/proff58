# Runbook: миграция каталога на v2 (скрытый build → секционный swap)

Сценарий **варианта A** («скрыто → секционный swap»): v2-дерево строится **скрытым**
параллельно живому legacy-дереву; по готовности раздела делается **секционный swap**
(показать v2, скрыть парный legacy). Каждый раздел проверяется и откатывается
независимо. Рассчитан на **staging**; на прод — тем же порядком после приёмки.

Сокращение: `WEB="docker compose -f docker-compose.prod.yml exec web python manage.py"`.

> Команды: `catalog_build_section` (строит скрыто + расселяет),
> `catalog_v2_report` (пред-swap отчёт по DoD), `catalog_v2_swap` (включение раздела),
> `catalog_sync_rules` (E2 — авто-классификация новых товаров 1С).
> Карта разделов — `apps/catalog/semantic.py::SECTION_RULES`. План v2 —
> `docs/plans/catalog-taxonomy-v2.md`.

---

## 0. Механика (вариант A)

`catalog_build_section --section <slug> --commit`:
- создаёт v2-узлы **скрытыми** (`is_active=False` + `on_site=False` — нужны ОБА: первый
  убирает из API-дерева/чипов, второй из меню; см. карту видимости);
- заводит на раздел скрытый узел **«На модерацию»**;
- **high** → нормальный узел (`category_is_manual=True`, защита от 1С);
- **medium/low** → «На модерацию» (`category_is_manual=False` — ждут разбора);
- **no_match** (раздел не матчит) → не трогает (глобальный хвост, см. отчёт);
- ручные (`category_is_manual=True`) не перетирает;
- пишет снимок отката + **CSV модерации** `var/restructure/moderation-<section>-<ts>.csv`.

`catalog_v2_swap --section <slug> --hide-legacy <slug,...> --commit`:
- v2-узлы → видимы (КРОМЕ «На модерацию»); указанные legacy-корни → скрыты;
- снимок отката видимости + **CSV плана 301** (реальные redirect не создаются — модели
  нет, Фаза 3).

### 0.1 Два сценария наполнения раздела

Перед build смотри состояние парного легаси (товаров / `manual`):

- **Легаси НЕ размечен** (товары `manual=False`) → `catalog_build_section` (словарная
  классификация по названию товара). Это база (напр. оснастка, сварка).
- **Легаси УЖЕ вручную разложен** (`manual=True`, подкатегории совпадают с v2-скелетом по
  именам — напр. крепёж) → `catalog_build_section` его НЕ возьмёт (manual-защита, «high→0»).
  Используй **`catalog_remap_legacy --section <slug> --from <legacy-slug>`**: переносит
  товары каждой легаси-подкатегории в **одноимённый** v2-узел, сохраняя курацию
  (`manual=True`). Несопоставленные легаси-узлы (нет v2-пары) остаются в легаси — хвост на
  разбор (по нему потом `build_section` или ручной разбор). Dry-run / снимок отката
  `var/restructure/remap-<section>-<ts>.json` / откат `--rollback`.

  ```bash
  $WEB catalog_remap_legacy --section krepezh --from krepezh-i-metizy            # dry-run
  $WEB catalog_remap_legacy --section krepezh --from krepezh-i-metizy --commit    # применить
  ```
  Дальше — как обычно: `catalog_v2_report` → `catalog_seed_filters` → `catalog_v2_swap`.

**Важно:** товары остаются видимы по `Product.is_active/status` независимо от флагов
категории. На staging «обеднённые» legacy-категории в окне между build и swap — норма.

---

## 1. Предусловия (один раз)

```bash
# 1.1 На staging-хосте, в каталоге проекта.
# 1.2 ОБЯЗАТЕЛЬНО бэкап БД (полный откат):
bash scripts/backup.sh

# 1.3 Снимок дерева ИЗ БД «до» (НЕ catalog_taxonomy_audit — он читает статический дамп):
$WEB shell -c "
from apps.catalog.models import Category, Product
print('Всего:', Product.objects.count(),
      '| ручных:', Product.objects.filter(category_is_manual=True).count(),
      '| без категории:', Product.objects.filter(category__isnull=True).count())
for root in Category.get_root_nodes():
    nodes=[root]+list(root.get_descendants())
    print(f'{root.slug:24s} on_site={root.on_site} act={root.is_active} '
          f'товаров={Product.objects.filter(category__in=nodes).count()}')
" | tee /tmp/tree-before.txt

# 1.4 НОРМАЛИЗАЦИЯ ПИЛОТА: v2-osnastka был построен СТАРОЙ командой ВИДИМЫМ — скрыть его
#     поддерево, чтобы соответствовать варианту A (видимость включит только swap).
$WEB shell -c "
from apps.catalog.models import Category
root=Category.objects.get(slug='osnastka')
ids=[root.id]+list(root.get_descendants().values_list('id',flat=True))
Category.objects.filter(id__in=ids).update(is_active=False, on_site=False)
print('скрыто узлов osnastka:', len(ids))
"
```

> Опционально для osnastka можно прогнать новый `build_section --section osnastka --commit`
> ещё раз (идемпотентно): добавит узел «На модерацию» и уведёт его medium/low-хвост.
> high-узлы (manual) не тронутся.

---

## 2. Порядок разделов (specific → generic, техника → запчасти)

| # | slug | раздел | парный(ые) legacy для --hide-legacy (уточнить по /tmp/tree-before.txt) |
|---|---|---|---|
| 1 | `osnastka` | Оснастка | `osnastka-i-rashodniki` |
| 2 | `krepezh` | Крепёж | `krepezh-i-metizy` |
| 3 | `izmeritelnyy` | Измерительный | `izmeritelnyy-instrument` |
| 4 | `svarka` | Сварка | `svarochnoe-oborudovanie` |
| 5 | `elektrika` | Электрика/освещение | `elektrika-i-osveschenie` |
| 6 | `silovaya` | Силовая/пневмо | `benzo-i-pnevmoinstrument`, `oborudovanie` (частично) |
| 7 | `avto` | Автоинструмент | (нет точного парного — swap без --hide-legacy или частично) |
| 8 | `sadovaya` | Садовая | `hoztovary-sad-ogorod` |
| 9 | `stroitelnyy` | Строительный | `stroitelnoe-i-otdelochnoe` |
| 10 | `siz` | СИЗ | `spetsodezhda-i-zaschita` |
| 11 | `hranenie` | Хранение | (нет парного — без --hide-legacy) |
| 12 | `zapchasti` | Запчасти | `zapchasti` |
| 13 | `ruchnoy` | Ручной | `ruchnoy-instrument` |

> Парность legacy↔v2 **не 1:1** (один legacy кормит несколько v2 и наоборот). Перед
> swap раздела свериться с отчётом: legacy-корень скрывать, только когда его остаток —
> это либо no_match-хвост, либо то, что уже мигрировало. `--hide-legacy` принимает список.
> Электроинструмент (`elektroinstrument`) — facet-раздел (TypePanel), его НЕ строим и
> при свапах node-разделов **не скрываем**.

---

## 3. Шаблон на ОДИН раздел (пример — `krepezh`)

### 3.1 Build (скрыто)
```bash
$WEB catalog_build_section --section krepezh | tee /tmp/dry-krepezh.txt      # dry-run
$WEB catalog_build_section --section krepezh --commit | tee /tmp/commit-krepezh.txt
```
Проверить в dry-run: число узлов = словарю; «high → норма» ожидаемо; «medium/low →
модерация» разумно; **нет slug-конфликтов** (иначе разобрать; `--strict` остановит commit).

### 3.2 Отчёт (DoD)
```bash
$WEB catalog_v2_report --section krepezh | tee /tmp/report-krepezh.txt
```
Смотреть: расселение норма/модерация; stock>0; хвост no_match; **утечек скрытого v2 нет**;
slug-конфликтов нет; sample breadcrumb корректен.

### 3.2b Посев фильтров (характеристики)
Характеризация (`CategoryAttribute`) сидит на **легаси-корнях**, v2-листы наследуют её
от родителя. Новый v2-корень голый → фильтры пропадут. Копируем конфиг с легаси-корня:
```bash
$WEB catalog_seed_filters --section krepezh --from krepezh-i-metizy | tee /tmp/seed-krepezh.txt
$WEB catalog_seed_filters --section krepezh --from krepezh-i-metizy --commit
```
Проверка: `GET /api/catalog/categories/<v2-slug>/facets/` → в `facets[]` есть характеристики
(не только price/brand/stock). Источник `--from` — те же легаси-корни, что и `--hide-legacy`.

### 3.3 Section swap (gated — после твоего «go»)
```bash
# dry-run: что покажем / что скроем
$WEB catalog_v2_swap --section krepezh --hide-legacy krepezh-i-metizy | tee /tmp/swap-krepezh.txt
# применить:
$WEB catalog_v2_swap --section krepezh --hide-legacy krepezh-i-metizy --commit --force
```

### 3.4 E2 — авто-классификация новых товаров 1С (ПОСЛЕ swap)
```bash
$WEB catalog_sync_rules --section krepezh --commit
```
> E2 запускать только ПОСЛЕ swap: до swap v2 скрыт, и новые товары 1С не должны утекать
> в невидимые узлы.

### 3.5 Проверка витрины
Открыть раздел на staging: v2 в меню/чипах, breadcrumbs целые, фасеты/фильтры работают,
старый legacy-раздел исчез из меню, дублей нет.

---

## 4. DoD перед swap раздела (обязательный чек-лист)

- [ ] v2-root создан скрытым (`is_active=False, on_site=False`);
- [ ] товары stock>0 классифицированы; high перенесены в нормальные узлы;
- [ ] medium/low в «На модерацию» (CSV модерации снят);
- [ ] нет дублей категорий (по отчёту);
- [ ] нет slug-конфликтов;
- [ ] нет утечек скрытого v2 (отчёт: все не-свапнутые узлы скрыты);
- [ ] sample breadcrumbs корректны;
- [ ] filters/facets на v2-разделе работают;
- [ ] парный legacy-root определён и его остаток понятен (no_match/хвост);
- [ ] rollback понятен (снимки build + swap на месте).

---

## 5. Откат

**Build раздела** (вернуть категории + удалить пустые узлы):
```bash
$WEB catalog_build_section --rollback var/restructure/build-<section>-<ts>.json
```
**Swap раздела** (вернуть видимость v2/legacy):
```bash
$WEB catalog_v2_swap --rollback var/restructure/swap-<section>-<ts>.json
```
**E2-правила раздела** (снять авто-правила):
```bash
$WEB shell -c "from apps.catalog.models import CategoryMappingRule; CategoryMappingRule.objects.filter(note__startswith='[auto:<slug>]').delete()"
```
**Всё целиком** (форс-мажор) — из дампа §1.2:
```bash
gunzip -c $BACKUP_DIR/db-<ts>.sql.gz | docker compose -f docker-compose.prod.yml exec -T db psql -U $POSTGRES_USER -d $POSTGRES_DB
```

---

## 6. Завершение (после всех swap)

```bash
$WEB catalog_v2_report | tee /tmp/report-final.txt      # глобальный отчёт по всем разделам
$WEB rebuild_attrs_cache                                 # кэш фасетов
# снимок дерева «после» и diff с «до»:
$WEB shell -c "
from apps.catalog.models import Category, Product
for root in Category.get_root_nodes():
    nodes=[root]+list(root.get_descendants())
    print(f'{root.slug:24s} on_site={root.on_site} act={root.is_active} '
          f'товаров={Product.objects.filter(category__in=nodes).count()}')
" | tee /tmp/tree-after.txt
diff /tmp/tree-before.txt /tmp/tree-after.txt
```
Публикация скрытых товаров (если нужно) — `publish_catalog --all --dry-run` затем без
`--dry-run`, по согласованию. Хвост в «На модерацию» разбирается отдельно (CSV модерации).

---

## 7. Нюансы

1. **legacy↔v2 не 1:1** — swap гасит legacy-корень через явный `--hide-legacy`; команда
   с guard сообщит, сколько товаров в нём останется не видно в дереве (требует `--force`).
2. **Хвост no_match** остаётся в legacy; если его legacy-корень скрыт — товары уходят из
   дерева (видны только по прямой ссылке/поиску). Перед скрытием — проверить отчётом.
3. **`zapchasti:Аккумуляторы`** ловит аккумуляторный инструмент → порядок (техника
   раньше Запчастей) + спот-чек.
4. **Redirects/canonical** — модели в проекте нет (Фаза 3); swap пишет только CSV-план.
5. **Идемпотентность** — повторный build безопасен; повторный swap создаёт новый снимок.

---

## 8. Чек-лист прогона

- [ ] §1 бэкап + tree-before + нормализация пилота osnastka
- [ ] для каждого раздела по §2: build(скрыто) → report → **[твоё go]** → swap → E2 → проверка витрины
- [ ] §6 финальный report, rebuild_attrs_cache, tree-after + diff
- [ ] публикация/разбор «На модерацию» — по согласованию
