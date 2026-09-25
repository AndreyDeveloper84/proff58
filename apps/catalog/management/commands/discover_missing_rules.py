"""Кандидаты на блоки правил характеристик: какой tool_type писать следующим.

Команда отвечает на один вопрос — «какое правило написать следующим, чтобы
получить максимум». До неё карта считалась разовыми скриптами и устаревала
через месяц; здесь та же арифметика зафиксирована в репозитории и
воспроизводится одной командой.

**Строго read-only.** Ни одной записи в БД: ни PAV, ни ``attrs_cache``, ни
``ImportRun``. Это её главное свойство — команду можно гонять на живом стенде.

Что делает
----------
1. Берёт скоуп товаров (``--in-stock-only`` / ``--active-only`` /
   ``--tool-type`` — как у ``enrich_attributes``, пересечением).
2. Группирует по ``tool_type`` и сверяет с блоками ``attribute_rules.json``:
   у типа блока нет вовсе, блок есть, но покрывает не всё, или блок полный.
3. Гоняет по названиям каталог частотных шаблонов
   (:mod:`apps.catalog.rule_discovery`) и считает, сколько товаров реально
   поддаются извлечению — и **сколько названий наивная регулярка ловит
   ошибочно** (``(\\d+)\\s*м`` читает «ф 3,2 мм» как «3,2 метра»: на стенде у
   свёрл это 188 ложных срабатываний против 124 верных).
4. Считает по **каждой оси отдельно** три числа — потенциал, исполнимое сейчас и
   запертое — и выдаёт список типов по убыванию ``actionable_score``.

Три числа на ось
----------------
``potential_values``
    Сколько значений технически извлекается шаблоном.
``actionable_values``
    Сколько из них можно **безопасно записать и показать покупателю сейчас**.
``blocked_values``
    Разница: значения, упирающиеся в отсутствие ``Attribute``, в отсутствие
    facet-привязки, в мёртвую категорию, в разнородный пул или в шум шаблона.

Считать это одним коэффициентом на весь тип нельзя: усреднение маскирует
различие между осями и ухудшает приоритизацию. Доказанный случай —
``klyuchi-gaechnye``: у оси ``wrench_type`` 142 значения видны покупателю
полностью, у оси ``material`` все 74 не видны (атрибут в БД есть, но к
категориям ключей не привязан). Один коэффициент на тип показал бы «блок на 216
значений», хотя безопасно реализуемы только 142.

Итог типа **агрегируется снизу вверх, из осей**:
``potential_score = Σ potential_values × sales_weight``,
``actionable_score = Σ actionable_values × sales_weight``. Рейтинг сортируется
по ``actionable_score``, ``potential`` показывается рядом — их разница и есть
объём работы, запертой за архитектурой.

Видимость оси
-------------
Ось видима, если её ``Attribute`` существует в БД **и** привязан через
``CategoryAttribute(is_filter=True)`` к категории товара **или любому её живому
предку** — фасеты наследуются вниз. Проверка идёт по каждому товару, а не долей
на тип.

Rule Impact Score (legacy)
--------------------------
Поле ``score`` осталось прежним — оно считает потенциал типа одним
коэффициентом и сохранено для преемственности отчётов. Рейтинг им больше не
управляет.
Метрика приоритета, воспроизводимая по числам самого отчёта::

    RIS = products × attributes × sales_weight × extraction_confidence
          × facet_visibility

``products``
    Товаров типа в скоупе.
``attributes``
    Сколько **новых** характеристик даст блок: шаблоны, прошедшие порог
    ``--min-pattern-share`` и ещё не описанные в блоке типа. Ноль новых
    характеристик — ноль выгоды, тип уже закрыт.
``sales_weight``
    Продажи за окно ``SALES_WINDOW_DAYS`` (``ProductSalesStat``, наполняется
    из фактов ``ProductSalesFact``: заказы сайта и выгрузка
    ``/api/1c/sales/upload``)::

        доля товаров скоупа с продажами за окно < --sales-min-share
            → 1.0 для всех типов + флаг sales_data_absent: коммерческого веса
              в рейтинге нет, и это ограничение ДАННЫХ, а не кода
        иначе → 0.5 + 1.5 × доля товаров типа с продажами, диапазон [0.5, 2.0]

    Тип без продаж получает 0.5 — вдвое ниже среднего, но **не ноль**: иначе
    товар, который не продавался просто потому, что у него нет характеристик и
    его не находят фильтром, навсегда остался бы без правил.

    Деградация нейтральная (1.0), а не нулевая, намеренно: с нулём весь рейтинг
    схлопнулся бы в ноль и команда стала бы бесполезной ровно там, где она
    нужнее всего. Порог ``--sales-min-share`` отсекает не только пустую
    таблицу, но и единичные строки: на стенде это 1 факт продажи на 47 225
    товаров — таблица формально не пуста, а сигнала в ней нет. Долевой порог
    (а не абсолютный) выбран потому, что осмысленность продаж зависит от
    размера каталога, а не от числа строк.  Пока 1С не начнёт слать ``sales/upload``,
    приоритизация идёт без коммерческого веса — команда обязана сказать об этом
    вслух, а не молча посчитать.
``extraction_confidence``
    Средняя доля товаров типа под одним предложенным шаблоном (100 % → 1.0,
    половина → 0.5). Правило, срабатывающее у четверти корпуса, стоит вчетверо
    меньше правила, срабатывающего у всех.
``facet_visibility``
    Будет ли характеристика видна на витрине::

        доля товаров в живой категории (is_active AND on_site)
        × 1.0, если у этих категорий (или предков) уже есть хотя бы одна
              привязка CategoryAttribute(is_filter=True)
        × 0.75, если привязок нет — фасет придётся заводить с нуля

    Значение без фасетной привязки к категории товара или её предку витрине не
    видно, поэтому мёртвая категория обнуляет выгоду правила.

Статусы оси
-----------
``READY``
    Ось готова к работе (``next_action: WRITE_RULE``).
``BLOCKED_BY_ATTRIBUTE``
    ``Attribute`` нет в БД. Лечится ``load_attributes`` **после** того, как
    правило появится в ``attribute_rules.json`` (``LOAD_ATTRIBUTES``).
``BLOCKED_BY_FACET``
    Атрибут есть, но не привязан к нужным категориям — витрине значение не
    видно. Лечится решением владельца о привязке (``FACET_BINDING_AUDIT``).
``BLOCKED_BY_CATEGORY``
    Все товары оси стоят в мёртвых категориях (``CATEGORY_REVIVAL``).
``BLOCKED_BY_CLASSIFICATION``
    Тип — «свалка», сначала разбор на подтипы (``SPLIT_TOOL_TYPE``).
``BLOCKED_BY_PURITY``
    Пул грязный: шаблон ошибается чаще ``--max-false-positive-rate``, значения
    получились бы мусорными (``POOL_PURITY_AUDIT``).
``SKIP_SET``
    Тип-набор: ось описывает состав набора, а не предмет
    (``SET_COMPOSITION_REVIEW``).

Очередь facet-binding
---------------------
Агрегат по каталогу: «привязка атрибута X к категории Y разблокирует N значений
на M товарах», по убыванию выигрыша. Привязка к предку накрывает всех потомков,
поэтому у каждого предложения посчитан **blast radius** (сколько товаров скоупа
окажется под фасетом) и заполненность; ниже ``--min-facet-fill-rate``
предложение помечено как малополезное — фасет с заполненностью в единицы
процентов не помогает выбрать, а засоряет фильтры.

Статусы типа
------------
``CREATE_RULE``
    Можно писать блок правил.
``SKIP_SET``
    Тип-набор: по конвенции у набора пишутся характеристики самого набора, а не
    его элементов. ``piece_count`` — число предметов, ``package_quantity`` —
    фасовка, путать нельзя.
``TAIL_GENERIC``
    Длинный хвост (< ``--tail-threshold`` товаров): отдельный блок правил на
    такой тип не окупается.
``BLOCKED_BY_CLASSIFICATION``
    Разнородный корпус — «свалка», а не тип. Определяется **по признаку**
    (ведущие слова названий не сходятся), а не списком slug'ов: сначала разбор
    на подтипы, правила бессмысленны.
``BLOCKED_BY_ATTRIBUTE``
    Предложенных ``Attribute`` нет в БД — сначала ``load_attributes``.
``BLOCKED_BY_CATEGORY``
    Товары типа стоят в мёртвых категориях — фасет не появится на витрине.

Форматы выхода
--------------
Консольная таблица — всегда; кроме неё два независимых файла, флаги можно
указывать вместе:

``--json-report`` — machine-readable снимок отчёта (тот же словарь, что строит
``_analyse``), для скриптов и сверок.
``--md-report`` — тот же отчёт в Markdown: для чтения человеком и для вставки в
задачу без переверстки.

Примеры::

    ./manage.py discover_missing_rules --in-stock-only --active-only --limit 20
    ./manage.py discover_missing_rules --in-stock-only --json-report /tmp/dmr.json
    ./manage.py discover_missing_rules --in-stock-only --md-report /tmp/dmr.md
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.ingest import data_dir
from apps.catalog.models import (
    Attribute,
    Category,
    CategoryAttribute,
    Product,
    ProductAttributeValue,
    ProductSalesStat,
)
from apps.catalog.rule_discovery import PATTERNS, corpus_heterogeneity, head_token, scan_items
from apps.catalog.sales import sales_window

TOOL_TYPE_SLUG = "tool_type"
RULES_FILE = "attribute_rules.json"

# Пороги по умолчанию. Вынесены в флаги: числа отчёта зависят от них, поэтому
# любой прогон обязан печатать использованные значения (см. _scope_meta).
DEFAULT_MIN_PATTERN_SHARE = 0.25
# Доля ложных срабатываний наивной регулярки, выше которой шаблон НЕ предлагается.
# Шаблон, который на своём же корпусе ошибается чаще, чем в трети случаев, —
# это не характеристика, а совпадение символов: у свёрл наивный «N м» даёт 124
# попадания и 188 ложных («ф 3,2 мм» → «2 м»). Предлагать такое правило значит
# советовать оператору заведомый мусор, поэтому шаблон уходит в отдельный список
# «отклонено по шуму» — с числами, а не молча.
DEFAULT_MAX_FALSE_POSITIVE_RATE = 0.33
DEFAULT_TAIL_THRESHOLD = 6
DEFAULT_HETEROGENEITY_DOMINANCE = 0.35
DEFAULT_HETEROGENEITY_MIN_HEADS = 10
DEFAULT_HETEROGENEITY_MIN_PRODUCTS = 20
# Доля товаров скоупа с продажами за окно, ниже которой коммерческий вес
# нейтрализуется. 1 % — не круглое число «на глаз», а точка, где множитель
# перестаёт что-либо различать: при базовой частоте продаж 1 % у типа медианного
# размера (6 товаров) ожидаемое число продавшихся — 0.06, то есть почти все типы
# получают sold_share=0 и один и тот же вес 0.5. Такой множитель не приоритизирует,
# а просто делит весь рейтинг на два, изображая при этом учёт продаж.
DEFAULT_SALES_MIN_SHARE = 0.01

STATUS_CREATE = "CREATE_RULE"
STATUS_SET = "SKIP_SET"
STATUS_TAIL = "TAIL_GENERIC"
STATUS_CLASSIFICATION = "BLOCKED_BY_CLASSIFICATION"
STATUS_ATTRIBUTE = "BLOCKED_BY_ATTRIBUTE"
STATUS_CATEGORY = "BLOCKED_BY_CATEGORY"

# --- статусы уровня ОСИ ---------------------------------------------------- #
#
# Причины блокировки не смешиваются: у «атрибута нет в БД» и «атрибут есть, но
# не привязан» разная цена и разное лечение, поэтому это два разных статуса, а
# не один «что-то не так с осью». К каждому блокирующему статусу приложен
# next_action — конкретный следующий шаг, а не общее пожелание.
AXIS_READY = "READY"
AXIS_ATTRIBUTE = "BLOCKED_BY_ATTRIBUTE"
AXIS_FACET = "BLOCKED_BY_FACET"
AXIS_CATEGORY = "BLOCKED_BY_CATEGORY"
AXIS_CLASSIFICATION = "BLOCKED_BY_CLASSIFICATION"
AXIS_PURITY = "BLOCKED_BY_PURITY"
AXIS_SET = "SKIP_SET"

NEXT_ACTION = {
    AXIS_READY: "WRITE_RULE",
    AXIS_ATTRIBUTE: "LOAD_ATTRIBUTES",
    AXIS_FACET: "FACET_BINDING_AUDIT",
    AXIS_CATEGORY: "CATEGORY_REVIVAL",
    AXIS_CLASSIFICATION: "SPLIT_TOOL_TYPE",
    AXIS_PURITY: "POOL_PURITY_AUDIT",
    AXIS_SET: "SET_COMPOSITION_REVIEW",
}

# Заполненность фасета, ниже которой привязку предлагать вредно: фильтр с
# единицами процентов заполнения не помогает выбрать, а засоряет сайдбар
# (прецедент каталога — фасет на 1,5 %). Порог не блокирует предложение, а
# помечает его флагом: решение о привязке всё равно за владельцем.
DEFAULT_MIN_FACET_FILL_RATE = 0.10

# Признаки типа-набора: slug семейства nabory-* или ведущее слово названий.
SET_SLUG_PREFIX = "nabory-"
SET_HEADS = frozenset({"набор", "наборы", "комплект", "комплекты"})
# Доля названий, начинающихся с «Набор…», при которой тип считается типом-набором.
# Порог именно долевой: у почти любого обычного типа найдётся один-два товара
# «Набор головок», и признак «есть хоть одно такое название» пометил бы наборами
# половину каталога (проверено на стенде: golovki, otvertki, klyuchi-gaechnye).
# Отдельные наборы внутри обычного типа — это задача карантина, а не статуса типа.
SET_HEAD_SHARE = 0.5


def _set_head_share(names) -> float:
    """Доля названий, у которых ведущее слово — «набор»/«комплект»."""
    total = 0
    sets = 0
    for name in names:
        head = head_token(name)
        if not head:
            continue
        total += 1
        sets += head in SET_HEADS
    return (sets / total) if total else 0.0


def _is_set_type(slug: str, set_head_share: float) -> bool:
    return slug.startswith(SET_SLUG_PREFIX) or set_head_share >= SET_HEAD_SHARE


class Command(BaseCommand):
    help = "Кандидаты на блоки правил характеристик по типам инструмента (read-only)."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=None, help=f"Каталог с {RULES_FILE}")
        parser.add_argument(
            "--tool-type",
            dest="tool_type",
            action="append",
            default=None,
            metavar="SLUG",
            help="Ограничить анализ типом (можно несколько раз). Без флага — все типы.",
        )
        parser.add_argument(
            "--in-stock-only",
            dest="in_stock_only",
            action="store_true",
            help="Только товары в наличии (available_quantity > 0).",
        )
        parser.add_argument(
            "--active-only",
            dest="active_only",
            action="store_true",
            help="Только активные товары (is_active=True).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            metavar="N",
            help="Показать только N первых типов таблицы (0 — все). Итоги считаются "
            "по всему скоупу, срез влияет только на вывод.",
        )
        parser.add_argument(
            "--json-report",
            dest="json_report",
            default=None,
            metavar="FILE",
            help="Записать machine-readable отчёт в файл (без флага — только таблица).",
        )
        parser.add_argument(
            "--md-report",
            dest="md_report",
            default=None,
            metavar="FILE",
            help="Записать отчёт в Markdown (для чтения человеком и вставки в задачу). "
            "Независим от --json-report, можно указывать оба.",
        )
        parser.add_argument(
            "--examples",
            type=int,
            default=3,
            metavar="N",
            help="Сколько примеров названий показывать на шаблон (по умолчанию 3).",
        )
        parser.add_argument(
            "--min-pattern-share",
            type=float,
            default=DEFAULT_MIN_PATTERN_SHARE,
            metavar="DOLYA",
            help="Порог доли товаров типа, с которого шаблон предлагается как "
            f"характеристика (по умолчанию {DEFAULT_MIN_PATTERN_SHARE}).",
        )
        parser.add_argument(
            "--max-false-positive-rate",
            type=float,
            default=DEFAULT_MAX_FALSE_POSITIVE_RATE,
            metavar="DOLYA",
            help="Доля ложных срабатываний, выше которой шаблон не предлагается, а "
            f"уходит в «отклонено по шуму» (по умолчанию {DEFAULT_MAX_FALSE_POSITIVE_RATE}).",
        )
        parser.add_argument(
            "--tail-threshold",
            type=int,
            default=DEFAULT_TAIL_THRESHOLD,
            metavar="N",
            help=f"Тип с числом товаров меньше N — длинный хвост, статус {STATUS_TAIL} "
            f"(по умолчанию {DEFAULT_TAIL_THRESHOLD}).",
        )
        parser.add_argument(
            "--sales-min-share",
            type=float,
            default=DEFAULT_SALES_MIN_SHARE,
            metavar="DOLYA",
            help="Минимальная доля товаров скоупа с продажами за окно, при которой "
            "коммерческий вес учитывается. Меньше — sales_weight=1.0 у всех типов "
            f"с явной пометкой «н/д» (по умолчанию {DEFAULT_SALES_MIN_SHARE}).",
        )
        parser.add_argument(
            "--min-facet-fill-rate",
            type=float,
            default=DEFAULT_MIN_FACET_FILL_RATE,
            metavar="DOLYA",
            help="Заполненность фасета, ниже которой предложение о привязке помечается "
            f"как малополезное (по умолчанию {DEFAULT_MIN_FACET_FILL_RATE}).",
        )
        parser.add_argument(
            "--heterogeneity-dominance",
            type=float,
            default=DEFAULT_HETEROGENEITY_DOMINANCE,
            metavar="DOLYA",
            help="Доля самого частого ведущего слова, ниже которой корпус считается "
            f"разнородным (по умолчанию {DEFAULT_HETEROGENEITY_DOMINANCE}).",
        )

    # ------------------------------------------------------------------ #

    def handle(self, *args, **options):
        base = options["path"] or data_dir()
        rules_path = Path(base) / RULES_FILE
        try:
            raw = json.loads(rules_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise CommandError(f"Не читается файл правил {rules_path}: {exc}") from exc
        block_attrs = {
            block["tool_type"]: {a["slug"] for a in block.get("attributes", ())}
            for block in raw.get("tool_types", ())
        }
        # Имя категории из блока — это НЕ справочная информация: именно по нему
        # load_attributes создаёт привязку, и именно туда уйдёт фасет новой оси.
        block_categories = {
            block["tool_type"]: block.get("category") or "" for block in raw.get("tool_types", ())
        }

        scope = self._collect_scope(options)
        if not scope["products"]:
            self.stdout.write(self.style.WARNING("Скоуп пуст — ни одного товара."))
        report = self._analyse(scope, block_attrs, block_categories, options)
        self._render(report, options)

        # Форматы независимы: можно попросить оба сразу, можно ни одного.
        json_report = options["json_report"]
        if json_report:
            Path(json_report).write_text(
                json.dumps(report, ensure_ascii=False, indent=2, sort_keys=False),
                encoding="utf-8",
            )
            self.stdout.write(f"\nJSON-отчёт: {json_report}")

        md_report = options["md_report"]
        if md_report:
            Path(md_report).write_text(
                render_markdown(report, limit=options["limit"]),
                encoding="utf-8",
            )
            self.stdout.write(f"\nMarkdown-отчёт: {md_report}")
        return ""

    # ------------------------------------------------------------------ #
    # Сбор данных (только чтение)
    # ------------------------------------------------------------------ #

    def _collect_scope(self, options) -> dict:
        """Прочитать товары скоупа и всё, что нужно для метрик. Ни одной записи."""
        filters: dict[str, object] = {}
        if options["in_stock_only"]:
            # available_quantity, как у enrich_attributes и остальных операционных
            # команд каталога (витрина считает по stock_quantity — другой контур).
            filters["available_quantity__gt"] = 0
        if options["active_only"]:
            filters["is_active"] = True

        products = {
            row["pk"]: row
            for row in Product.objects.filter(**filters).values(
                "pk", "name", "original_name", "category_id", "available_quantity"
            )
        }
        product_ids = list(products)

        # tool_type товара — из PAV (value_option.slug), не из attrs_cache:
        # там русский ярлык, а правила знают slug.
        product_tt = {
            row["product_id"]: row["value_option__slug"]
            for row in ProductAttributeValue.objects.filter(
                product_id__in=product_ids,
                attribute__slug=TOOL_TYPE_SLUG,
                value_option__isnull=False,
            ).values("product_id", "value_option__slug")
        }

        # «Есть характеристики» = хотя бы один PAV с атрибутом, отличным от
        # tool_type. Сам тип характеристикой не считается — иначе покрытие
        # было бы 100 % у всех типизированных товаров.
        with_attrs = set(
            ProductAttributeValue.objects.filter(product_id__in=product_ids)
            .exclude(attribute__slug=TOOL_TYPE_SLUG)
            .values_list("product_id", flat=True)
            .distinct()
        )

        sold = set(
            ProductSalesStat.objects.filter(product_id__in=product_ids).values_list(
                "product_id", flat=True
            )
        )
        sales_total = ProductSalesStat.objects.count()

        categories = {
            row["pk"]: row
            for row in Category.objects.values(
                "pk", "name", "path", "depth", "is_active", "on_site"
            )
        }
        faceted = set()
        # Привязки поимённо: ось видна витрине, только если фасетом объявлен
        # ИМЕННО её атрибут. «У категории есть хоть какой-то фильтр» — другой,
        # более слабый признак, и путать их нельзя: у ключей `wrench_type`
        # привязан, а `material` — нет, при одном и том же наборе категорий.
        bound_by_attribute: dict[str, set[int]] = {}
        for slug, category_id in CategoryAttribute.objects.filter(is_filter=True).values_list(
            "attribute__slug", "category_id"
        ):
            faceted.add(category_id)
            bound_by_attribute.setdefault(slug, set()).add(category_id)

        requested_tt = sorted(set(options["tool_type"] or ()))
        if requested_tt:
            allowed = set(requested_tt)
            product_ids = [pid for pid in product_ids if product_tt.get(pid) in allowed]
            products = {pid: products[pid] for pid in product_ids}

        return {
            "products": products,
            "product_tt": product_tt,
            "with_attrs": with_attrs,
            "sold": sold,
            "sales_total": sales_total,
            "categories": categories,
            "faceted": faceted,
            "bound_by_attribute": bound_by_attribute,
            "requested_tt": requested_tt,
            "known_attributes": set(Attribute.objects.values_list("slug", flat=True)),
        }

    # ------------------------------------------------------------------ #
    # Анализ
    # ------------------------------------------------------------------ #

    def _analyse(self, scope, block_attrs, block_categories, options) -> dict:
        products = scope["products"]
        product_tt = scope["product_tt"]
        min_share = options["min_pattern_share"]
        max_fp_rate = options["max_false_positive_rate"]
        tail_threshold = options["tail_threshold"]
        dominance_threshold = options["heterogeneity_dominance"]
        n_examples = options["examples"]

        by_type: dict[str, list[int]] = {}
        untyped: list[int] = []
        for pid in products:
            slug = product_tt.get(pid)
            if slug:
                by_type.setdefault(slug, []).append(pid)
            else:
                untyped.append(pid)

        # Коммерческий вес учитываем только если продажи вообще различают типы.
        # Иначе множитель одинаков у всех и лишь делит рейтинг на два, изображая
        # учёт продаж — деградируем в нейтральный 1.0 и говорим об этом вслух.
        sold_in_scope = len(scope["sold"] & set(products))
        sold_scope_share = sold_in_scope / len(products) if products else 0.0
        sales_absent = sold_scope_share < options["sales_min_share"]
        ancestors = _ancestor_index(scope["categories"])
        descendant_scope = _descendant_scope(scope, ancestors)

        rows = []
        for slug, pids in by_type.items():
            rows.append(
                self._analyse_type(
                    slug,
                    pids,
                    scope=scope,
                    block_attrs=block_attrs,
                    block_categories=block_categories,
                    ancestors=ancestors,
                    descendant_scope=descendant_scope,
                    sales_absent=sales_absent,
                    min_share=min_share,
                    max_fp_rate=max_fp_rate,
                    min_facet_fill_rate=options["min_facet_fill_rate"],
                    tail_threshold=tail_threshold,
                    dominance_threshold=dominance_threshold,
                    n_examples=n_examples,
                )
            )
        # Рейтинг — по actionable: он отвечает на вопрос «что можно безопасно
        # сделать следующим». potential идёт рядом, вторым ключом сортировки:
        # разница между ними и есть объём работы, запертой за архитектурой.
        rows.sort(
            key=lambda r: (
                -r["actionable_score"],
                -r["potential_score"],
                -r["products"],
                r["tool_type"],
            )
        )
        binding_gaps = [gap for row in rows for gap in row.pop("binding_gaps")]

        totals = _totals(scope, by_type, untyped, block_attrs)
        totals.update(_axis_totals(rows))
        return {
            "scope": _scope_meta(options, scope, totals),
            "totals": totals,
            "sales": {
                "window_days": (sales_window()[1] - sales_window()[0]).days + 1,
                "products_with_sales_in_scope": sold_in_scope,
                "scope_share": round(sold_scope_share, 6),
                "min_share": options["sales_min_share"],
                "sales_stat_rows_total": scope["sales_total"],
                "data_absent": sales_absent,
                "degradation": (
                    f"продажи есть у {sold_in_scope} товаров скоупа "
                    f"({sold_scope_share * 100:.3f}% < порога "
                    f"{options['sales_min_share'] * 100:.1f}%): sales_weight=1.0 у всех "
                    "типов, коммерческий вес в приоритизации НЕ участвует"
                    if sales_absent
                    else "sales_weight = 0.5 + 1.5 × доля товаров типа с продажами за окно"
                ),
            },
            "candidates": rows,
            "binding_targets": _binding_target_report(rows),
            "axis_ranking": _axis_ranking(rows),
            "facet_binding_queue": _facet_binding_queue(
                binding_gaps,
                scope,
                ancestors,
                descendant_scope,
                options["min_facet_fill_rate"],
            ),
            "cumulative_by_volume": _cumulative_by_volume(
                by_type, block_attrs, scope["with_attrs"]
            ),
        }

    def _analyse_type(
        self,
        slug,
        pids,
        *,
        scope,
        block_attrs,
        block_categories,
        ancestors,
        descendant_scope,
        sales_absent,
        min_share,
        max_fp_rate,
        min_facet_fill_rate,
        tail_threshold,
        dominance_threshold,
        n_examples,
    ) -> dict:
        products = scope["products"]
        names = [products[pid]["original_name"] or products[pid]["name"] or "" for pid in pids]
        total = len(pids)

        hits = scan_items(zip(pids, names, strict=True), examples=n_examples)
        covered = block_attrs.get(slug)
        has_block = covered is not None
        covered = covered or set()

        set_head_share = _set_head_share(names)
        is_set = _is_set_type(slug, set_head_share)

        # Куда уйдёт привязка новой оси. Считать видимость по категории ТОВАРА
        # нельзя: привязку создаёт load_attributes по полю `category` блока, и у
        # 28 блоков из 48 это имя разрешается в корень раздела.
        target = _binding_target(slug, block_categories, has_block, scope)

        # Разнородность нужна ДО разбора осей: «свалка» блокирует каждую ось
        # типа, а не только итог, — иначе ось выглядела бы готовой к работе.
        hetero = corpus_heterogeneity(names)
        heterogeneous = (
            total >= DEFAULT_HETEROGENEITY_MIN_PRODUCTS
            and hetero.dominance < dominance_threshold
            and hetero.distinct_heads >= DEFAULT_HETEROGENEITY_MIN_HEADS
        )

        patterns_out = []
        axes = []
        binding_gaps = []
        proposed_shares = []
        proposed_slugs = []
        for pattern in PATTERNS:
            hit = hits[pattern.key]
            share = hit.share(total)
            # У наборов «N шт» — это состав набора (piece_count), а не фасовка.
            attr_slug = (
                pattern.set_attribute_slug
                if (is_set and pattern.set_attribute_slug)
                else pattern.attribute_slug
            )
            # Шумный шаблон не предлагаем: правило, ошибающееся чаще порога,
            # оператору вредно. Но и не прячем — он остаётся в отчёте с
            # rejected_reason, чтобы решение было видимым.
            too_noisy = hit.false_positive_rate > max_fp_rate
            passes_share = share >= min_share
            proposed = passes_share and attr_slug not in covered and not too_noisy
            rejected_reason = ""
            if passes_share and attr_slug not in covered and too_noisy:
                rejected_reason = (
                    f"шум: {hit.false_positives} ложных на {hit.naive_hits} попаданий "
                    f"наивной регулярки ({hit.false_positive_rate * 100:.0f}% > "
                    f"{max_fp_rate * 100:.0f}%)"
                )
            row = {
                "pattern": pattern.key,
                "title": pattern.title,
                "attribute_slug": attr_slug,
                "attribute_name": pattern.attribute_name,
                "kind": pattern.kind,
                "unit": pattern.unit,
                "regex": pattern.guarded.pattern,
                "naive_regex": pattern.naive.pattern,
                "hits": hit.guarded_hits,
                "share": round(share, 4),
                "naive_hits": hit.naive_hits,
                "false_positives": hit.false_positives,
                "false_positive_rate": round(hit.false_positive_rate, 4),
                "already_in_block": attr_slug in covered,
                "proposed": proposed,
                "rejected_reason": rejected_reason,
                "attribute_exists": attr_slug in scope["known_attributes"],
                "examples": list(hit.examples),
                "false_positive_examples": list(hit.false_positive_examples),
                "top_values": [v for v, _ in hit.values.most_common(4)],
                "note": pattern.note,
            }
            patterns_out.append(row)
            if proposed:
                proposed_shares.append(share)
                proposed_slugs.append(attr_slug)

            # --- ось: три числа и собственный статус --------------------- #
            #
            # Ось попадает в разбор, если шаблон прошёл порог доли и его
            # характеристика ещё не описана блоком. Шумную ось не выбрасываем:
            # её потенциал реален, блокирует его чистота пула, и это отдельный
            # статус, а не молчание.
            if not passes_share or attr_slug in covered:
                continue
            visibility = _axis_visibility(
                hit.matched_keys,
                attr_slug,
                scope=scope,
                ancestors=ancestors,
                products=products,
                target=target,
            )
            axis_status = _axis_status(
                is_set=is_set,
                heterogeneous=heterogeneous,
                too_noisy=too_noisy,
                attribute_exists=row["attribute_exists"],
                live_values=visibility["live"],
                visible_values=visibility["visible"],
            )
            potential_values = hit.guarded_hits
            actionable_values = visibility["visible"] if axis_status == AXIS_READY else 0
            axes.append(
                {
                    "attribute_slug": attr_slug,
                    "attribute_name": pattern.attribute_name,
                    "pattern": pattern.key,
                    "kind": pattern.kind,
                    "potential_values": potential_values,
                    "actionable_values": actionable_values,
                    "blocked_values": potential_values - actionable_values,
                    "visibility": round(
                        visibility["visible"] / potential_values if potential_values else 0.0, 4
                    ),
                    "live_values": visibility["live"],
                    # Уже привязано против «привяжет load_attributes»: первое —
                    # факт, второе — предсказание, и они не одно и то же.
                    "already_visible_values": visibility["already_bound"],
                    "unlocked_by_binding_target": visibility["visible"]
                    - visibility["already_bound"],
                    "status": axis_status,
                    "next_action": NEXT_ACTION[axis_status],
                    "share": round(share, 4),
                    "false_positive_rate": round(hit.false_positive_rate, 4),
                }
            )
            row["axis_status"] = axis_status
            row["axis_next_action"] = NEXT_ACTION[axis_status]
            row["potential_values"] = potential_values
            row["actionable_values"] = actionable_values
            # Очередь привязок собирается только с осей, которым мешает именно
            # привязка: у мёртвой категории и отсутствующего атрибута лечение
            # другое, и смешивать их в один список значит подсунуть владельцу
            # работу, которая ничего не разблокирует.
            if axis_status == AXIS_FACET:
                for cid, count in visibility["unbound_live_categories"].items():
                    binding_gaps.append(
                        {
                            "attribute_slug": attr_slug,
                            "attribute_name": pattern.attribute_name,
                            "category_id": cid,
                            "tool_type": slug,
                            "values": count,
                        }
                    )

        # --- множители RIS --------------------------------------------- #
        attributes = len(proposed_slugs)
        extraction_confidence = (
            sum(proposed_shares) / len(proposed_shares) if proposed_shares else 0.0
        )
        sold_share = sum(1 for pid in pids if pid in scope["sold"]) / total if total else 0.0
        sales_weight = 1.0 if sales_absent else round(0.5 + 1.5 * sold_share, 4)

        live_share, faceted_categories, category_ids = _category_stats(
            pids, scope, ancestors, products
        )
        facet_visibility = live_share * (1.0 if faceted_categories else 0.75)

        score = total * attributes * sales_weight * extraction_confidence * facet_visibility

        # Итог типа агрегируется СНИЗУ ВВЕРХ — из осей, а не считается отдельно:
        # один коэффициент на весь тип усредняет несопоставимые оси и маскирует
        # различие (у ключей `wrench_type` виден покупателю целиком, `material` —
        # не виден вовсе), из-за чего приоритизация врёт.
        potential_total = sum(axis["potential_values"] for axis in axes)
        actionable_total = sum(axis["actionable_values"] for axis in axes)
        potential_score = potential_total * sales_weight
        actionable_score = actionable_total * sales_weight

        # Цена привязки: сколько товаров окажется под фасетом и какая доля из них
        # получит значение. Корень раздела накрывает тысячи товаров — фасет с
        # заполненностью в единицы процентов засоряет фильтры всего раздела.
        own_categories = {
            products[pid]["category_id"] for pid in pids if products[pid]["category_id"] is not None
        }
        # Товар накрыт, только если его категория ещё и жива: под скрытым узлом
        # фасета не будет независимо от того, куда легла привязка.
        target_products = sum(
            1
            for pid in pids
            if _is_live(products[pid]["category_id"], scope["categories"])
            and _covered_by_target(products[pid]["category_id"], target, ancestors)
        )
        blast_radius = (
            descendant_scope.get(target["covers"], 0)
            if target["covers"] is not None
            else sum(
                1 for row in scope["products"].values() if row["category_id"] in own_categories
            )
        )
        target_fill_rate = (actionable_total / blast_radius) if blast_radius else 0.0
        target.update(
            {
                "products_at_target": sum(
                    1 for pid in pids if products[pid]["category_id"] == target["covers"]
                ),
                "products_covered": target_products,
                "products_outside": total - target_products,
                "blast_radius": blast_radius,
                "fill_rate": round(target_fill_rate, 4),
                "low_fill_rate": bool(
                    target["covers"] is not None
                    and potential_total
                    and target_fill_rate < min_facet_fill_rate
                ),
            }
        )

        missing_attributes = sorted(set(proposed_slugs) - scope["known_attributes"])

        status, reason = _status(
            total=total,
            tail_threshold=tail_threshold,
            is_set=is_set,
            heterogeneous=heterogeneous,
            hetero=hetero,
            live_share=live_share,
            missing_attributes=missing_attributes,
            attributes=attributes,
        )

        with_attrs = sum(1 for pid in pids if pid in scope["with_attrs"])
        in_stock = sum(1 for pid in pids if (products[pid]["available_quantity"] or 0) > 0)
        return {
            "tool_type": slug,
            "products": total,
            "with_attributes": with_attrs,
            "without_attributes": total - with_attrs,
            "in_stock": in_stock,
            "block": (
                ("full" if has_block and not attributes else "partial") if has_block else "absent"
            ),
            "block_attributes": sorted(covered),
            "status": status,
            "reason": reason,
            "potential_values": potential_total,
            "actionable_values": actionable_total,
            "blocked_values": potential_total - actionable_total,
            "actionable_ratio": round(
                actionable_total / potential_total if potential_total else 0.0, 4
            ),
            "potential_score": round(potential_score, 2),
            "actionable_score": round(actionable_score, 2),
            "binding_target": target,
            "axes": axes,
            "binding_gaps": binding_gaps,
            "score": round(score, 2),
            "score_factors": {
                "products": total,
                "attributes": attributes,
                "sales_weight": sales_weight,
                "extraction_confidence": round(extraction_confidence, 4),
                "facet_visibility": round(facet_visibility, 4),
                "sold_share": round(sold_share, 4),
                "live_category_share": round(live_share, 4),
                "categories_with_filter_binding": faceted_categories,
            },
            "proposed_attributes": sorted(set(proposed_slugs)),
            "missing_attributes": missing_attributes,
            "is_set_type": is_set,
            "set_head_share": round(set_head_share, 4),
            "heterogeneity": {
                "distinct_heads": hetero.distinct_heads,
                "top_head": hetero.top_head,
                "dominance": round(hetero.dominance, 4),
                "head_ratio": round(hetero.head_ratio, 4),
                "flagged": heterogeneous,
            },
            "categories": sorted(category_ids),
            "patterns": patterns_out,
        }

    # ------------------------------------------------------------------ #
    # Вывод
    # ------------------------------------------------------------------ #

    def _render(self, report, options) -> None:
        out = self.stdout
        totals = report["totals"]
        meta = report["scope"]

        out.write("\n=== Скоуп ===")
        out.write(
            f"фильтры: in_stock_only={meta['in_stock_only']}, "
            f"active_only={meta['active_only']}, tool_type={meta['tool_type'] or '—'}"
        )
        out.write(
            f"пороги: min_pattern_share={meta['min_pattern_share']}, "
            f"tail_threshold={meta['tail_threshold']}, "
            f"heterogeneity_dominance={meta['heterogeneity_dominance']}"
        )

        out.write("\n=== Итоги пула ===")
        out.write(f"товаров в скоупе:            {totals['products']}")
        out.write(
            f"есть характеристики:         {totals['with_attributes']} "
            f"({totals['with_attributes_pct']}%)"
        )
        out.write(f"нет характеристик:           {totals['without_attributes']}")
        out.write(f"  из них тип без блока:      {totals['without_attributes_no_block']}")
        out.write(f"  блок есть, но пусто:       {totals['without_attributes_block_empty']}")
        out.write(f"без tool_type:               {totals['untyped']}")
        out.write(f"типов в пуле:                {totals['tool_types']}")
        out.write(f"блоков в attribute_rules:    {totals['rule_blocks']}")
        out.write(
            f"типов без блока:             {totals['tool_types_without_block']} "
            f"на {totals['products_in_types_without_block']} товаров"
        )
        out.write(
            f"длинный хвост (< {meta['tail_threshold']} тов.):    "
            f"{totals['tail_types']} типов на {totals['tail_products']} товаров "
            f"— отдельные блоки правил не нужны"
        )

        sales = report["sales"]
        if sales["data_absent"]:
            out.write(self.style.WARNING(f"\nПРОДАЖИ: {sales['degradation']}."))
        else:
            out.write(
                f"\nПродажи: окно {sales['window_days']} дн., товаров с продажами в скоупе "
                f"{sales['products_with_sales_in_scope']}; {sales['degradation']}."
            )

        rows = report["candidates"]
        limit = options["limit"]
        shown = rows[:limit] if limit else rows
        gap_total = sum(r["without_attributes"] for r in rows) or 1

        out.write("\n=== Значения: потенциал / исполнимое / запертое ===")
        out.write(f"potential_values:  {totals['potential_values']}")
        out.write(f"actionable_values: {totals['actionable_values']}")
        out.write(f"blocked_values:    {totals['blocked_values']}")
        out.write(f"actionable_ratio:  {totals['actionable_ratio'] * 100:.1f}%")

        out.write("\n=== Кандидаты (по убыванию actionable_score) ===")
        header = (
            f"{'#':>3} {'tool_type':32} {'тов':>5} {'без хар':>7} {'блок':>7} "
            f"{'нов':>3} {'pot':>7} {'act':>7} {'act%':>5} {'a-score':>9} "
            f"{'p-score':>9} {'кум%':>5}  статус"
        )
        out.write(header)
        out.write("-" * len(header))
        cumulative = 0
        for index, row in enumerate(rows, start=1):
            cumulative += row["without_attributes"]
            if limit and index > limit:
                break
            factors = row["score_factors"]
            out.write(
                f"{index:>3} {row['tool_type'][:32]:32} {row['products']:>5} "
                f"{row['without_attributes']:>7} {row['block']:>7} "
                f"{factors['attributes']:>3} {row['potential_values']:>7} "
                f"{row['actionable_values']:>7} {row['actionable_ratio'] * 100:>4.0f}% "
                f"{row['actionable_score']:>9.1f} {row['potential_score']:>9.1f} "
                f"{cumulative * 100 // gap_total:>4}%  {row['status']}"
            )
        if limit and len(rows) > limit:
            out.write(f"... и ещё {len(rows) - limit} типов (см. --json-report)")

        self._render_axis_ranking(report)
        self._render_binding_targets(report)
        self._render_binding_queue(report)

        out.write("\n=== Что предлагается писать (топ показанных) ===")
        for row in shown:
            # Предложения печатаем при любом статусе: блокер объясняет, что
            # мешает, но не отменяет уже посчитанную картину — оператору нужно
            # видеть, ради чего блокер стоит снимать.
            out.write(
                f"\n{row['tool_type']} ({row['products']} тов., "
                f"score {row['score']}) — {row['status']}: {row['reason']}"
            )
            target = row["binding_target"]
            out.write(
                "  привязка уйдёт в: "
                + (
                    f"«{target['category_name']}» → id {target['category_id']} "
                    f"({target['reason']}), накроет {target['products_covered']} из "
                    f"{row['products']}, под фасетом {target['blast_radius']}, "
                    f"заполненность {target['fill_rate'] * 100:.1f}%"
                    if target["source"] == "block"
                    else "блока нет — цель выберет оператор (число предположительное)"
                )
            )
            out.write("")
            for axis in row["axes"]:
                out.write(f"  {axis['attribute_slug']}")
                out.write(
                    f"    potential: {axis['potential_values']:<5} "
                    f"actionable: {axis['actionable_values']:<5} "
                    f"visibility: {axis['visibility'] * 100:.0f}%   "
                    f"status: {axis['status']}"
                )
                if axis["status"] != AXIS_READY:
                    out.write(f"    next_action: {axis['next_action']}")
            out.write(f"\n  potential_total:  {row['potential_values']}")
            out.write(f"  actionable_total: {row['actionable_values']}")
            out.write(f"  actionable_ratio: {row['actionable_ratio'] * 100:.1f}%\n")
            for pattern in row["patterns"]:
                if not pattern["proposed"] and not pattern["rejected_reason"]:
                    continue
                mark = "  " if pattern["proposed"] else "  ~"
                out.write(
                    f"{mark}{pattern['attribute_slug']:20} {pattern['kind']:7} "
                    f"{pattern['title']:16} попаданий {pattern['hits']} "
                    f"({pattern['share'] * 100:.0f}%), ложных {pattern['false_positives']}"
                    + ("" if pattern["attribute_exists"] else "  [АТРИБУТА НЕТ В БД]")
                )
                if pattern["rejected_reason"]:
                    out.write(f"    ОТКЛОНЁН: {pattern['rejected_reason']}")
                out.write(f"    regex: {pattern['regex']}")
                for example in pattern["examples"]:
                    out.write(f"    пример: {example[:110]}")
                for example in pattern["false_positive_examples"]:
                    out.write(f"    ЛОЖНОЕ:  {example[:110]}")

        self._render_control(report)

    def _render_axis_ranking(self, report) -> None:
        """Рейтинг осей сквозной по каталогу — работу выбирают по осям, не по типам."""
        out = self.stdout
        ranking = report["axis_ranking"]
        for key, title in (
            ("by_actionable", "Топ осей по actionable_values (что писать)"),
            ("by_blocked", "Топ осей по blocked_values (очередь архитектурной работы)"),
        ):
            out.write(f"\n=== {title} ===")
            entries = ranking[key][:10]
            if not entries:
                out.write("— пусто")
                continue
            for entry in entries:
                statuses = ", ".join(
                    f"{status}×{count}" for status, count in sorted(entry["statuses"].items())
                )
                out.write(
                    f"  {entry['attribute_slug']:20} potential {entry['potential_values']:>6} "
                    f"actionable {entry['actionable_values']:>6} "
                    f"blocked {entry['blocked_values']:>6}  "
                    f"типов {entry['tool_types']:>3}  {statuses}"
                )

    def _render_binding_targets(self, report) -> None:
        """Куда уйдут привязки блоков и во что это обойдётся витрине."""
        out = self.stdout
        block = report["binding_targets"]
        out.write("\n=== Куда уйдёт привязка (поле category блока) ===")
        out.write(
            f"привязок в корень раздела: {block['root_bindings']}; "
            f"с низкой заполненностью: {block['low_fill_rate']}; "
            f"неразрешимых (нет узла / неоднозначно / мёртвый): {block['unresolved']}"
        )
        if not block["items"]:
            out.write("— пусто: у типов с предложенными осями блоков нет")
            return
        header = (
            f"  {'tool_type':28} {'категория блока':28} {'кат.':>6} {'гл':>3} "
            f"{'накрыто':>8} {'вне':>5} {'под фасетом':>11} {'заполн':>7}  флаги"
        )
        out.write(header)
        out.write("  " + "-" * (len(header) - 2))
        for item in block["items"][:20]:
            flags = ",".join(
                name
                for name, value in (
                    ("КОРЕНЬ", item["root_binding"]),
                    ("МАЛО", item["low_fill_rate"]),
                    ("НЕ РАЗРЕШЕНО", item["unresolved"]),
                )
                if value
            )
            out.write(
                f"  {item['tool_type'][:28]:28} {item['category_name'][:28]:28} "
                f"{str(item['category_id'] or '—'):>6} {str(item['category_depth'] or '—'):>3} "
                f"{item['products_covered']:>8} {item['products_outside']:>5} "
                f"{item['blast_radius']:>11} {item['fill_rate'] * 100:>6.1f}%  {flags}"
            )
        if len(block["items"]) > 20:
            out.write(f"  ... и ещё {len(block['items']) - 20} типов (см. --json-report)")

    def _render_binding_queue(self, report) -> None:
        """Очередь facet-binding с blast radius и заполненностью."""
        out = self.stdout
        queue = report["facet_binding_queue"]
        out.write("\n=== Очередь facet-binding (что привязать, чтобы разблокировать) ===")
        out.write(
            f"всего заперто привязками: {queue['unlocked_values_total']} значений; "
            f"порог полезной заполненности {queue['min_fill_rate'] * 100:.0f}%"
        )
        if not queue["items"]:
            out.write("— пусто: осей, запертых только привязкой, нет")
            return
        header = (
            f"  {'атрибут':20} {'кат.':>6} {'уровень':>9} {'разблок':>8} {'под фасетом':>11} "
            f"{'заполн':>7}  типы"
        )
        out.write(header)
        out.write("  " + "-" * (len(header) - 2))
        for item in queue["items"][:20]:
            mark = " ⚠" if item["low_fill_rate"] else ""
            out.write(
                f"  {item['attribute_slug']:20} {item['category_id']:>6} "
                f"{item['binding_level']:>9} {item['unlocked_values']:>8} "
                f"{item['blast_radius']:>11} {item['fill_rate'] * 100:>6.1f}%{mark}  "
                f"{', '.join(item['tool_types'][:3])}"
            )
        if len(queue["items"]) > 20:
            out.write(f"  ... и ещё {len(queue['items']) - 20} предложений (см. --json-report)")

    def _render_control(self, report) -> None:
        out = self.stdout
        control = report["cumulative_by_volume"]
        out.write("\n=== Контрольный кумулятив (типы без блока, по убыванию объёма) ===")
        for key, title in (
            ("all", "все товары типа"),
            ("gap", "только товары без характеристик"),
        ):
            block = control[key]
            out.write(f"\n{key} — {title}: {block['types']} типов на {block['products']} товаров")
            for n, value in block["checkpoints"].items():
                out.write(f"  {n:>4} типов → {value} товаров")


# ---------------------------------------------------------------------- #
# Markdown-отчёт
# ---------------------------------------------------------------------- #
#
# Тот же отчёт, что печатается в консоль, но в виде, который можно вставить в
# задачу без переверстки. Функция чистая: на вход словарь ``_analyse``, на выход
# строка — её можно проверить тестом, не гоняя команду.

_BACKTICKS_RE = re.compile(r"`+")


def _md_cell(value) -> str:
    """Значение для ячейки таблицы: труба и перевод строки ломают разметку."""
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _md_code(value) -> str:
    """Инлайн-код с фенсом, который не рвётся о содержимое.

    Регулярки шаблонов содержат ``|``, ``*`` и ``_``: вне кода Markdown прочитал
    бы их как разметку, а внутри кода с одиночным бэктиком — сломался бы о
    бэктик в самом значении. Поэтому длина фенса считается по содержимому.
    """
    text = str(value).replace("\n", " ")
    longest = max((len(match) for match in _BACKTICKS_RE.findall(text)), default=0)
    fence = "`" * (longest + 1)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{fence}{pad}{text}{pad}{fence}"


def _md_table(header: list[str], align: list[str], rows: list[list[str]]) -> list[str]:
    """Строки Markdown-таблицы с явным выравниванием колонок."""
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(align) + "|"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def _md_flag(value: bool) -> str:
    return "да" if value else "нет"


def render_markdown(report: dict, *, limit: int = 0) -> str:
    """Собрать Markdown-версию отчёта. ``limit`` — как у таблицы в консоли."""
    meta = report["scope"]
    totals = report["totals"]
    sales = report["sales"]
    rows = report["candidates"]
    shown = rows[:limit] if limit else rows

    out: list[str] = ["# Кандидаты на блоки правил характеристик", ""]
    out.append(
        "Отчёт команды `discover_missing_rules`. Команда **строго read-only**: "
        "ни одной записи в БД — ни `ProductAttributeValue`, ни `attrs_cache`."
    )
    out.append("")

    out.append("## Скоуп")
    out.append("")
    out.extend(
        _md_table(
            ["Параметр", "Значение"],
            ["---", "---"],
            [
                ["`--in-stock-only`", _md_flag(meta["in_stock_only"])],
                ["`--active-only`", _md_flag(meta["active_only"])],
                ["`--tool-type`", _md_cell(", ".join(meta["tool_type"]) or "—")],
                ["`--min-pattern-share`", _md_cell(meta["min_pattern_share"])],
                ["`--max-false-positive-rate`", _md_cell(meta["max_false_positive_rate"])],
                ["`--tail-threshold`", _md_cell(meta["tail_threshold"])],
                ["`--heterogeneity-dominance`", _md_cell(meta["heterogeneity_dominance"])],
                ["`--sales-min-share`", _md_cell(meta["sales_min_share"])],
                ["`--min-facet-fill-rate`", _md_cell(meta["min_facet_fill_rate"])],
            ],
        )
    )
    out.append("")

    out.append("## Итоги пула")
    out.append("")
    out.extend(
        _md_table(
            ["Показатель", "Значение"],
            ["---", "---:"],
            [
                ["товаров в скоупе", _md_cell(totals["products"])],
                [
                    "есть характеристики",
                    f"{totals['with_attributes']} ({totals['with_attributes_pct']}%)",
                ],
                ["нет характеристик", _md_cell(totals["without_attributes"])],
                ["— из них тип без блока", _md_cell(totals["without_attributes_no_block"])],
                ["— блок есть, но пусто", _md_cell(totals["without_attributes_block_empty"])],
                ["без `tool_type`", _md_cell(totals["untyped"])],
                ["типов в пуле", _md_cell(totals["tool_types"])],
                ["блоков в `attribute_rules.json`", _md_cell(totals["rule_blocks"])],
                [
                    "типов без блока",
                    f"{totals['tool_types_without_block']} на "
                    f"{totals['products_in_types_without_block']} товаров",
                ],
                [
                    f"длинный хвост (< {meta['tail_threshold']} тов.)",
                    f"{totals['tail_types']} типов на {totals['tail_products']} товаров",
                ],
                ["`potential_values`", _md_cell(totals["potential_values"])],
                ["`actionable_values`", _md_cell(totals["actionable_values"])],
                ["`blocked_values`", _md_cell(totals["blocked_values"])],
                ["`actionable_ratio`", f"{totals['actionable_ratio'] * 100:.1f}%"],
            ],
        )
    )
    out.append("")

    if sales["data_absent"]:
        out.append(f"> **ПРОДАЖИ:** {_md_cell(sales['degradation'])}.")
    else:
        out.append(
            f"**Продажи:** окно {sales['window_days']} дн., товаров с продажами в скоупе "
            f"{sales['products_with_sales_in_scope']}; {_md_cell(sales['degradation'])}."
        )
    out.append("")

    out.append("## Кандидаты (по убыванию `actionable_score`)")
    out.append("")
    out.append(
        "`potential` — сколько значений технически извлекается; `actionable` — сколько "
        "из них можно безопасно записать и показать покупателю сейчас. Разница — "
        "объём работы, запертой за привязками, атрибутами и разбором пулов."
    )
    out.append("")
    if not rows:
        out.append("Кандидатов нет — в скоупе не нашлось ни одного типа.")
        out.append("")
    else:
        table_rows = []
        cumulative = 0
        gap_total = sum(row["without_attributes"] for row in rows) or 1
        for index, row in enumerate(rows, start=1):
            cumulative += row["without_attributes"]
            if limit and index > limit:
                continue
            factors = row["score_factors"]
            table_rows.append(
                [
                    str(index),
                    _md_code(row["tool_type"]),
                    str(row["products"]),
                    str(row["without_attributes"]),
                    _md_cell(row["block"]),
                    str(factors["attributes"]),
                    str(row["potential_values"]),
                    str(row["actionable_values"]),
                    str(row["blocked_values"]),
                    f"{row['actionable_ratio'] * 100:.0f}%",
                    f"{row['actionable_score']:.1f}",
                    f"{row['potential_score']:.1f}",
                    f"{row['score']:.1f}",
                    f"{cumulative * 100 // gap_total}%",
                    _md_cell(row["status"]),
                ]
            )
        out.extend(
            _md_table(
                [
                    "#",
                    "Тип",
                    "Товаров",
                    "Без характеристик",
                    "Блок",
                    "Новых",
                    "potential",
                    "actionable",
                    "blocked",
                    "act. %",
                    "actionable_score",
                    "potential_score",
                    "Score (RIS)",
                    "Кум. %",
                    "Статус",
                ],
                ["---:", "---", "---:", "---:", "---", "---:", "---:", "---:", "---:", "---:"]
                + ["---:", "---:", "---:", "---:", "---"],
                table_rows,
            )
        )
        out.append("")
        if limit and len(rows) > limit:
            out.append(f"… и ещё {len(rows) - limit} типов (полный список — в `--json-report`).")
            out.append("")

    out.extend(_markdown_axis_ranking(report["axis_ranking"]))
    out.extend(_markdown_binding_targets(report["binding_targets"]))
    out.extend(_markdown_binding_queue(report["facet_binding_queue"]))

    out.append("## Что предлагается писать")
    out.append("")
    if not shown:
        out.append("Предлагать нечего — кандидатов в скоупе нет.")
        out.append("")
    for index, row in enumerate(shown, start=1):
        out.extend(_markdown_candidate(index, row))

    control = report["cumulative_by_volume"]
    out.append("## Контрольный кумулятив (типы без блока, по убыванию объёма)")
    out.append("")
    out.append(
        "Ряды **нельзя путать**: `all` — все товары типов без блока, `gap` — только "
        "товары без характеристик, то есть те, что реально получат значения."
    )
    out.append("")
    marks = sorted(
        {int(mark) for block in control.values() for mark in block["checkpoints"]},
    )
    control_rows = [
        [
            str(mark),
            _md_cell(control["all"]["checkpoints"].get(str(mark), "—")),
            _md_cell(control["gap"]["checkpoints"].get(str(mark), "—")),
        ]
        for mark in marks
    ]
    control_rows.append(
        [
            "итого",
            f"{control['all']['types']} типов / {control['all']['products']} товаров",
            f"{control['gap']['types']} типов / {control['gap']['products']} товаров",
        ]
    )
    out.extend(
        _md_table(
            ["N типов", "`all` — все товары типа", "`gap` — только без характеристик"],
            ["---:", "---:", "---:"],
            control_rows,
        )
    )
    out.append("")
    return "\n".join(out)


def _markdown_axis_ranking(ranking: dict) -> list[str]:
    """Сквозной рейтинг осей: что писать и что разблокировать."""
    out = ["## Рейтинг осей (сквозной по каталогу)", ""]
    out.append(
        "Работу выбирают **не по `tool_type`, а по оси**: одна ось набирает объём "
        "сразу в нескольких типах, и по типам этот объём не виден. Порядок "
        "`by_blocked` — очередь архитектурной работы: что создать и что привязать."
    )
    out.append("")
    for key, title in (
        ("by_actionable", "Топ осей по `actionable_values` — что писать"),
        ("by_blocked", "Топ осей по `blocked_values` — очередь архитектурной работы"),
    ):
        out.append(f"### {title}")
        out.append("")
        entries = ranking[key][:10]
        if not entries:
            out.append("Пусто — предложенных осей в скоупе нет.")
            out.append("")
            continue
        out.extend(
            _md_table(
                ["Ось", "Характеристика", "potential", "actionable", "blocked", "Типов", "Статусы"],
                ["---", "---", "---:", "---:", "---:", "---:", "---"],
                [
                    [
                        _md_code(entry["attribute_slug"]),
                        _md_cell(entry["attribute_name"]),
                        str(entry["potential_values"]),
                        str(entry["actionable_values"]),
                        str(entry["blocked_values"]),
                        str(entry["tool_types"]),
                        _md_cell(
                            ", ".join(
                                f"{status}×{count}"
                                for status, count in sorted(entry["statuses"].items())
                            )
                        ),
                    ]
                    for entry in entries
                ],
            )
        )
        out.append("")
    return out


def _markdown_binding_targets(block: dict) -> list[str]:
    """Куда уйдёт привязка блока: корень раздела, заполненность, неразрешимые имена."""
    out = ["## Куда уйдёт привязка (поле `category` блока)", ""]
    out.append(
        "Видимость новой оси считается по категории, **куда фактически уйдёт "
        "привязка**: её создаёт `load_attributes` по полю `category` блока, разрешая "
        "имя лестницей, которая среди одноимённых узлов предпочитает `depth == 1`. "
        "Считать по категории товара значит учитывать привязку, которой не будет."
    )
    out.append("")
    out.append(
        f"Привязок в корень раздела: **{block['root_bindings']}**; с низкой "
        f"заполненностью: **{block['low_fill_rate']}**; неразрешимых "
        f"(нет узла / неоднозначно / мёртвый узел): **{block['unresolved']}**."
    )
    out.append("")
    if not block["items"]:
        out.append("Пусто: у типов с предложенными осями блоков правил нет.")
        out.append("")
        return out
    out.extend(
        _md_table(
            [
                "Тип",
                "Категория блока",
                "id",
                "Глубина",
                "Накрыто",
                "Вне цели",
                "Blast radius",
                "Заполненность",
                "Флаги",
            ],
            ["---", "---", "---:", "---:", "---:", "---:", "---:", "---:", "---"],
            [
                [
                    _md_code(item["tool_type"]),
                    _md_cell(item["category_name"] or "—"),
                    str(item["category_id"] or "—"),
                    str(item["category_depth"] or "—"),
                    str(item["products_covered"]),
                    str(item["products_outside"]),
                    str(item["blast_radius"]),
                    f"{item['fill_rate'] * 100:.1f}%",
                    _md_cell(
                        ", ".join(
                            name
                            for name, value in (
                                ("корень раздела", item["root_binding"]),
                                ("низкая заполненность", item["low_fill_rate"]),
                                ("не разрешено", item["unresolved"]),
                            )
                            if value
                        )
                        or "—"
                    ),
                ]
                for item in block["items"][:20]
            ],
        )
    )
    out.append("")
    if len(block["items"]) > 20:
        out.append(f"… и ещё {len(block['items']) - 20} типов (полный список — в `--json-report`).")
        out.append("")
    return out


def _markdown_binding_queue(queue: dict) -> list[str]:
    """Очередь facet-binding: что привязать, что это разблокирует и какой ценой."""
    out = ["## Очередь facet-binding", ""]
    out.append(
        f"Заперто привязками: **{queue['unlocked_values_total']}** значений. "
        "`blast radius` — сколько товаров скоупа окажется под фасетом, если привязать "
        "к этому узлу (привязка наследуется всем потомкам), `заполненность` — какая "
        "доля из них получит значение. Фасет с заполненностью ниже "
        f"{queue['min_fill_rate'] * 100:.0f}% помечен как малополезный: он не помогает "
        "выбрать, а засоряет сайдбар."
    )
    out.append("")
    if not queue["items"]:
        out.append("Пусто: осей, запертых **только** привязкой, в скоупе нет.")
        out.append("")
        return out
    out.extend(
        _md_table(
            [
                "Ось",
                "Категория",
                "Уровень",
                "Разблокирует значений",
                "Blast radius",
                "Заполненность",
                "Типы",
            ],
            ["---", "---:", "---", "---:", "---:", "---:", "---"],
            [
                [
                    _md_code(item["attribute_slug"]),
                    str(item["category_id"]),
                    _md_cell(item["binding_level"]),
                    str(item["unlocked_values"]),
                    str(item["blast_radius"]),
                    f"{item['fill_rate'] * 100:.1f}%"
                    + (" **мало**" if item["low_fill_rate"] else ""),
                    _md_cell(", ".join(item["tool_types"][:3])),
                ]
                for item in queue["items"][:20]
            ],
        )
    )
    out.append("")
    if len(queue["items"]) > 20:
        out.append(
            f"… и ещё {len(queue['items']) - 20} предложений (полный список — в `--json-report`)."
        )
        out.append("")
    return out


def _markdown_candidate(index: int, row: dict) -> list[str]:
    """Раздел одного кандидата: предлагаемые оси с числами и примерами."""
    out = [
        f"### {index}. {_md_code(row['tool_type'])} — {row['products']} тов., "
        f"actionable_score {row['actionable_score']} / potential_score "
        f"{row['potential_score']} (RIS {row['score']})",
        "",
        f"**{row['status']}:** {_md_cell(row['reason'])}",
        "",
    ]
    target = row["binding_target"]
    if target["source"] == "block":
        out.append(
            f"Привязка уйдёт в **{_md_cell(target['category_name'])}** "
            f"(id {target['category_id']}, `{target['reason']}`): накроет "
            f"{target['products_covered']} из {row['products']} товаров типа, под фасетом "
            f"окажется {target['blast_radius']}, заполненность "
            f"{target['fill_rate'] * 100:.1f}%."
        )
    else:
        out.append(
            "Блока правил нет — категорию привязки выберет оператор; `actionable` "
            "посчитан по презумпции «привяжем туда, где лежат товары»."
        )
    out.append("")
    if row["axes"]:
        out.extend(
            _md_table(
                ["Ось", "potential", "actionable", "visibility", "Статус", "next_action"],
                ["---", "---:", "---:", "---:", "---", "---"],
                [
                    [
                        _md_code(axis["attribute_slug"]),
                        str(axis["potential_values"]),
                        str(axis["actionable_values"]),
                        f"{axis['visibility'] * 100:.0f}%",
                        _md_cell(axis["status"]),
                        _md_cell(axis["next_action"]),
                    ]
                    for axis in row["axes"]
                ]
                + [
                    [
                        "**итого**",
                        f"**{row['potential_values']}**",
                        f"**{row['actionable_values']}**",
                        f"**{row['actionable_ratio'] * 100:.1f}%**",
                        "",
                        "",
                    ]
                ],
            )
        )
        out.append("")
    # Печатаем при любом статусе: блокер объясняет, что мешает, но не отменяет
    # уже посчитанную картину — видно, ради чего блокер стоит снимать.
    interesting = [p for p in row["patterns"] if p["proposed"] or p["rejected_reason"]]
    if not interesting:
        out.append("Предложений нет: ни один шаблон не прошёл порог или всё описано блоком.")
        out.append("")
        return out

    out.extend(
        _md_table(
            ["Ось", "Характеристика", "Вид", "Шаблон", "Попаданий", "Доля", "Ложных", "Итог"],
            ["---", "---", "---", "---", "---:", "---:", "---:", "---"],
            [
                [
                    _md_code(pattern["attribute_slug"]),
                    _md_cell(pattern["attribute_name"]),
                    _md_cell(pattern["kind"]),
                    _md_cell(pattern["title"]),
                    str(pattern["hits"]),
                    f"{pattern['share'] * 100:.0f}%",
                    str(pattern["false_positives"]),
                    (
                        "предлагается"
                        if pattern["proposed"]
                        else ("отклонён по шуму" if pattern["rejected_reason"] else "—")
                    )
                    + ("" if pattern["attribute_exists"] else ", **атрибута нет в БД**"),
                ]
                for pattern in interesting
            ],
        )
    )
    out.append("")

    for pattern in interesting:
        out.append(f"**{_md_code(pattern['attribute_slug'])}** — {_md_cell(pattern['title'])}")
        out.append("")
        if pattern["rejected_reason"]:
            out.append(f"- ОТКЛОНЁН: {_md_cell(pattern['rejected_reason'])}")
        out.append(f"- regex: {_md_code(pattern['regex'])}")
        for example in pattern["examples"]:
            out.append(f"- пример: {_md_code(example)}")
        for example in pattern["false_positive_examples"]:
            out.append(f"- ложное: {_md_code(example)}")
        out.append("")
    return out


# ---------------------------------------------------------------------- #
# Вспомогательные чистые функции
# ---------------------------------------------------------------------- #


def _ancestor_index(categories: dict[int, dict]) -> dict[int, list[int]]:
    """Для каждой категории — список её предков (id), по MP-путям treebeard."""
    steplen = Category.steplen
    by_path = {row["path"]: pk for pk, row in categories.items()}
    index: dict[int, list[int]] = {}
    for pk, row in categories.items():
        path = row["path"]
        chain = []
        for depth in range(1, len(path) // steplen):
            parent = by_path.get(path[: depth * steplen])
            if parent is not None:
                chain.append(parent)
        index[pk] = chain
    return index


def _category_stats(pids, scope, ancestors, products) -> tuple[float, int, set[int]]:
    """Доля товаров в живой категории, число фасетных категорий и их id.

    Живая = ``is_active AND on_site``. Фасетная = у неё самой или у предка есть
    привязка ``CategoryAttribute(is_filter=True)``: только такая категория умеет
    показать новую характеристику на витрине.
    """
    categories = scope["categories"]
    faceted = scope["faceted"]
    category_ids = set()
    live = 0
    faceted_count = 0
    seen_faceted = set()
    for pid in pids:
        cid = products[pid]["category_id"]
        if cid is None or cid not in categories:
            continue
        category_ids.add(cid)
        row = categories[cid]
        if row["is_active"] and row["on_site"]:
            live += 1
        if cid not in seen_faceted:
            seen_faceted.add(cid)
            if cid in faceted or any(a in faceted for a in ancestors.get(cid, ())):
                faceted_count += 1
    return (live / len(pids) if pids else 0.0), faceted_count, category_ids


def resolve_binding_category(name: str, categories: dict[int, dict]) -> tuple[int | None, str]:
    """Куда ``load_attributes`` фактически поставит привязку для имени категории.

    Повторяет лестницу ``load_attributes._resolve_category`` по уже прочитанному
    словарю категорий (лишних запросов не делаем — команда read-only и не должна
    дёргать БД ради справки): живые кандидаты важнее мёртвых, внутри отобранных
    приоритет у ``depth == 1``; если после этого кандидат не один — ``ambiguous``.

    Повторение нужно ровно потому, что предсказать эффект правила без него нельзя:
    у 28 блоков из 48 имя категории разрешается в **корень раздела**, а не в
    профильный узел, где лежат товары (``sverla`` → «Оснастка», ``klyuchi-gaechnye``
    → «Ручной инструмент»). Оценивать видимость новой оси по категории товара
    значит считать привязку, которой не будет.
    """
    if not name:
        return None, "no_category"
    objects = [row for row in categories.values() if row["name"] == name]
    if not objects:
        return None, "not_found"
    live = [row for row in objects if row["is_active"] and row["on_site"]]
    pool = live or objects
    tops = [row for row in pool if row["depth"] == 1]
    scope_rows = tops or pool
    level = "top" if tops else "tree"
    if len(scope_rows) != 1:
        return None, f"ambiguous:{level}"
    node = scope_rows[0]
    if not (node["is_active"] and node["on_site"]):
        return node["pk"], f"bound:{level}:dead"
    return node["pk"], f"bound:{level}"


def _binding_target(slug, block_categories, has_block, scope) -> dict:
    """Узел, куда уйдёт привязка новой оси этого типа, и его цена.

    У типа с блоком цель берётся из поля ``category`` блока и разрешается той же
    лестницей, что и в ``load_attributes``. У типа **без** блока цели ещё не
    существует: её выберет оператор, когда напишет блок, — тогда считаем по
    категориям самих товаров и честно помечаем результат ``presumed``, чтобы
    предположение нельзя было принять за замер.
    """
    categories = scope["categories"]
    if not has_block:
        return {
            "category_name": "",
            "category_id": None,
            "category_depth": None,
            "reason": "no_block",
            "source": "presumed",
            "is_live": True,
            "covers": None,  # None = «категории самих товаров»
        }
    name = block_categories.get(slug, "")
    category_id, reason = resolve_binding_category(name, categories)
    row = categories.get(category_id) if category_id is not None else None
    return {
        "category_name": name,
        "category_id": category_id,
        "category_depth": row["depth"] if row else None,
        "reason": reason,
        "source": "block",
        "is_live": bool(row and row["is_active"] and row["on_site"]),
        "covers": category_id,
    }


def _is_live(cid, categories) -> bool:
    """Категория видна витрине: существует, активна и выведена на сайт."""
    row = categories.get(cid) if cid is not None else None
    return bool(row and row["is_active"] and row["on_site"])


def _covered_by_target(cid, target, ancestors) -> bool:
    """Накроет ли привязка к цели товар из категории ``cid``.

    Привязка наследуется вниз, поэтому цель накрывает товар, если она и есть его
    категория либо её предок. Мёртвая цель не накрывает ничего: узел скрыт, а
    живым потомкам характеристика от скрытого узла не наследуется — ровно так
    блок ``metchiki-plashki`` уезжал в мёртвую категорию и фасет не появлялся.
    """
    if not target["is_live"]:
        return False
    node = target["covers"]
    if node is None:  # блока нет — цель выберет оператор, презумпция «где товары»
        return True
    return cid == node or node in ancestors.get(cid, ())


def _axis_visibility(matched_pids, attr_slug, *, scope, ancestors, products, target) -> dict:
    """Видимость ОДНОЙ оси: сколько её значений дойдёт до покупателя.

    Значение видно, если категория товара жива (``is_active AND on_site``) и
    фасетом объявлен **именно этот** атрибут — у самой категории или у любого её
    предка (фасеты наследуются вниз). Считается по каждому товару, а не долей на
    тип: у ключей ``wrench_type`` виден целиком, ``material`` — не виден вовсе,
    при одном и том же наборе категорий.

    Учитываются два источника видимости:

    ``already`` — привязка уже существует, значение будет видно сразу;
    ``target`` — привязку создаст ``load_attributes`` из поля ``category`` блока.
    Второй источник обязателен: у 28 блоков из 48 имя разрешается в корень
    раздела, а не в категорию товаров, и оценивать по категории товара значит
    считать привязку, которой не будет.
    """
    categories = scope["categories"]
    bound = scope["bound_by_attribute"].get(attr_slug, frozenset())
    live = 0
    already = 0
    visible = 0
    unbound: dict[int, int] = {}
    for pid in matched_pids:
        cid = products[pid]["category_id"]
        if not _is_live(cid, categories):
            continue
        live += 1
        is_bound = cid in bound or any(parent in bound for parent in ancestors.get(cid, ()))
        already += is_bound
        if is_bound or _covered_by_target(cid, target, ancestors):
            visible += 1
        else:
            unbound[cid] = unbound.get(cid, 0) + 1
    return {
        "live": live,
        "already_bound": already,
        "visible": visible,
        "unbound_live_categories": unbound,
    }


def _axis_status(
    *,
    is_set,
    heterogeneous,
    too_noisy,
    attribute_exists,
    live_values,
    visible_values,
) -> str:
    """Статус оси. Порядок проверок = порядок приоритета причин.

    Причины не смешиваются намеренно: ``BLOCKED_BY_ATTRIBUTE`` (атрибута нет в
    БД, лечится ``load_attributes`` после появления правила) и
    ``BLOCKED_BY_FACET`` (атрибут есть, привязки нет, лечится решением владельца
    о привязке) — разная работа и разная цена.
    """
    if is_set:
        return AXIS_SET
    if heterogeneous:
        return AXIS_CLASSIFICATION
    if too_noisy:
        return AXIS_PURITY
    if not attribute_exists:
        return AXIS_ATTRIBUTE
    if live_values == 0:
        return AXIS_CATEGORY
    if visible_values == 0:
        return AXIS_FACET
    return AXIS_READY


def _axis_totals(rows) -> dict:
    """Три числа по каталогу: потенциал, безопасно исполнимое и запертое."""
    potential = sum(row["potential_values"] for row in rows)
    actionable = sum(row["actionable_values"] for row in rows)
    return {
        "potential_values": potential,
        "actionable_values": actionable,
        "blocked_values": potential - actionable,
        "actionable_ratio": round(actionable / potential if potential else 0.0, 4),
    }


def _binding_target_report(rows) -> dict:
    """Куда фактически уйдут привязки и во что это обойдётся.

    Отдельный раздел, потому что дефект здесь системный, а не разовый: поле
    ``category`` блока разрешается лестницей ``load_attributes``, которая среди
    одноимённых узлов предпочитает ``depth == 1``, и у большинства блоков имя
    попадает в **корень раздела**, а не в профильную категорию с товарами.
    Привязка при этом «работает» (корень — предок, фасет наследуется вниз), но
    накрывает весь раздел: у `sverla` это «Оснастка» с тысячами товаров.

    Три исхода, которые нужно видеть отдельно:

    ``root_binding``
        цель — корень раздела (``depth == 1``), а товары лежат глубже;
    ``low_fill_rate``
        под фасетом окажется много товаров, а значения получат единицы;
    ``unresolved``
        имя не разрешается (``not_found``/``ambiguous``) или узел мёртв —
        привязки не будет вовсе, и ось не станет видимой ни при каком правиле.
    """
    items = []
    for row in rows:
        target = row["binding_target"]
        if target["source"] != "block" or not row["potential_values"]:
            continue
        resolved = target["reason"].startswith("bound:") and target["is_live"]
        items.append(
            {
                "tool_type": row["tool_type"],
                "category_name": target["category_name"],
                "category_id": target["category_id"],
                "category_depth": target.get("category_depth"),
                "reason": target["reason"],
                "products": row["products"],
                "products_covered": target["products_covered"],
                "products_outside": target["products_outside"],
                "products_at_target": target["products_at_target"],
                "blast_radius": target["blast_radius"],
                "fill_rate": target["fill_rate"],
                # Привязка уходит в корень раздела, а товары лежат глубже:
                # фасет накрывает весь раздел ради одного типа.
                "root_binding": bool(
                    resolved
                    and target.get("category_depth") == 1
                    and target["products_at_target"] < row["products"]
                ),
                "low_fill_rate": target["low_fill_rate"],
                "unresolved": not resolved,
            }
        )
    items.sort(key=lambda item: (-item["blast_radius"], item["tool_type"]))
    return {
        "items": items,
        "root_bindings": sum(1 for item in items if item["root_binding"]),
        "low_fill_rate": sum(1 for item in items if item["low_fill_rate"]),
        "unresolved": sum(1 for item in items if item["unresolved"]),
    }


def _axis_ranking(rows) -> dict:
    """Сквозной по каталогу рейтинг ОСЕЙ, а не типов.

    Работу выбирают не по ``tool_type``, а по конкретной оси: одна и та же ось
    набирает объём сразу в нескольких типах, и по типам этот объём не виден.
    Два порядка: по ``actionable`` — что писать, по ``blocked`` — очередь
    архитектурной работы (что создать, что привязать).
    """
    merged: dict[str, dict] = {}
    for row in rows:
        for axis in row["axes"]:
            entry = merged.setdefault(
                axis["attribute_slug"],
                {
                    "attribute_slug": axis["attribute_slug"],
                    "attribute_name": axis["attribute_name"],
                    "potential_values": 0,
                    "actionable_values": 0,
                    "blocked_values": 0,
                    "tool_types": 0,
                    "statuses": {},
                    "top_tool_types": [],
                },
            )
            entry["potential_values"] += axis["potential_values"]
            entry["actionable_values"] += axis["actionable_values"]
            entry["blocked_values"] += axis["blocked_values"]
            entry["tool_types"] += 1
            entry["statuses"][axis["status"]] = entry["statuses"].get(axis["status"], 0) + 1
            entry["top_tool_types"].append(
                {
                    "tool_type": row["tool_type"],
                    "potential_values": axis["potential_values"],
                    "actionable_values": axis["actionable_values"],
                    "status": axis["status"],
                }
            )
    for entry in merged.values():
        entry["top_tool_types"].sort(
            key=lambda item: (-item["potential_values"], item["tool_type"])
        )
        del entry["top_tool_types"][5:]
    entries = list(merged.values())
    return {
        "by_actionable": sorted(
            entries,
            key=lambda e: (-e["actionable_values"], -e["potential_values"], e["attribute_slug"]),
        ),
        "by_blocked": sorted(
            entries,
            key=lambda e: (-e["blocked_values"], -e["potential_values"], e["attribute_slug"]),
        ),
    }


def _descendant_scope(scope, ancestors) -> dict[int, int]:
    """Сколько товаров скоупа стоит в категории и во всех её потомках.

    Это знаменатель заполненности фасета: привязка к узлу накрывает всё поддерево,
    поэтому «сколько товаров окажется под фасетом» считается по потомкам, а не по
    той единственной категории, из-за которой привязку предложили.
    """
    counts: dict[int, int] = {}
    for row in scope["products"].values():
        cid = row["category_id"]
        if cid is None:
            continue
        counts[cid] = counts.get(cid, 0) + 1
        for parent in ancestors.get(cid, ()):
            counts[parent] = counts.get(parent, 0) + 1
    return counts


def _facet_binding_queue(binding_gaps, scope, ancestors, descendant_scope, min_fill_rate) -> dict:
    """Очередь привязок: «привязать X к Y — разблокирует N значений на M товарах».

    До сих пор такой список собирался вручную по одному типу. Здесь он строится
    сам и сразу с **blast radius**: привязка к узлу выше накрывает всех потомков,
    поэтому у каждого предложения посчитано, сколько товаров окажется под фасетом
    и какова будет его заполненность. Фасет с заполненностью в единицы процентов
    бесполезен и засоряет фильтры — такие предложения помечены флагом
    ``low_fill_rate``, а не тихо выданы наравне с остальными.

    Узел-предок предлагается, только если он объединяет **две и более** прямые
    категории: иначе это тот же самый фасет, но с большим радиусом и худшей
    заполненностью.
    """
    categories = scope["categories"]
    # attr → node → сведения; узел = прямая категория товара либо её предок.
    nodes: dict[tuple[str, int], dict] = {}
    for gap in binding_gaps:
        attr = gap["attribute_slug"]
        direct = gap["category_id"]
        for node in (direct, *ancestors.get(direct, ())):
            entry = nodes.setdefault(
                (attr, node),
                {
                    "attribute_slug": attr,
                    "attribute_name": gap["attribute_name"],
                    "category_id": node,
                    "binding_level": "direct" if node == direct else "ancestor",
                    "unlocked_values": 0,
                    "direct_categories": set(),
                    "tool_types": set(),
                },
            )
            if node == direct:
                entry["binding_level"] = "direct"
            entry["unlocked_values"] += gap["values"]
            entry["direct_categories"].add(direct)
            entry["tool_types"].add(gap["tool_type"])

    items = []
    for entry in nodes.values():
        direct_categories = entry.pop("direct_categories")
        if entry["binding_level"] == "ancestor" and len(direct_categories) < 2:
            continue
        node = entry["category_id"]
        blast_radius = descendant_scope.get(node, 0)
        fill_rate = entry["unlocked_values"] / blast_radius if blast_radius else 0.0
        category = categories.get(node, {})
        items.append(
            {
                **entry,
                "category_depth": category.get("depth"),
                "category_is_live": bool(category.get("is_active") and category.get("on_site")),
                "covers_categories": len(direct_categories),
                "blast_radius": blast_radius,
                "fill_rate": round(fill_rate, 4),
                "low_fill_rate": fill_rate < min_fill_rate,
                "tool_types": sorted(entry["tool_types"]),
            }
        )
    items.sort(
        key=lambda item: (
            -item["unlocked_values"],
            item["binding_level"] != "direct",
            item["category_id"],
        )
    )
    return {
        "min_fill_rate": min_fill_rate,
        "unlocked_values_total": sum(gap["values"] for gap in binding_gaps),
        "items": items,
    }


def _status(
    *,
    total,
    tail_threshold,
    is_set,
    heterogeneous,
    hetero,
    live_share,
    missing_attributes,
    attributes,
) -> tuple[str, str]:
    """Рекомендация по типу. Порядок проверок = порядок приоритета блокеров."""
    if total < tail_threshold:
        return (
            STATUS_TAIL,
            f"длинный хвост: {total} товаров — отдельный блок правил не окупается",
        )
    if is_set:
        return (
            STATUS_SET,
            "тип-набор: характеристики пишутся у самого набора; «N шт» — это "
            "piece_count (число предметов), а не package_quantity (фасовка)",
        )
    if heterogeneous:
        return (
            STATUS_CLASSIFICATION,
            f"разнородный корпус: {hetero.distinct_heads} разных ведущих слов, "
            f"самое частое «{hetero.top_head}» лишь у {hetero.dominance * 100:.0f}% "
            "названий — сначала разбор на подтипы, правило писать не на чем",
        )
    if live_share == 0:
        return (
            STATUS_CATEGORY,
            "все товары типа стоят в мёртвых категориях (is_active/on_site) — "
            "фасет на витрине не появится",
        )
    if missing_attributes:
        return (
            STATUS_ATTRIBUTE,
            f"нет Attribute в БД: {', '.join(missing_attributes)} — сначала load_attributes",
        )
    if attributes == 0:
        return (
            STATUS_TAIL,
            "ни один шаблон не проходит порог или всё уже описано блоком",
        )
    return STATUS_CREATE, "можно писать блок правил"


def _totals(scope, by_type, untyped, block_attrs) -> dict:
    products = scope["products"]
    with_attrs = scope["with_attrs"]
    total = len(products)
    have = sum(1 for pid in products if pid in with_attrs)
    no_block_gap = 0
    block_empty_gap = 0
    for slug, pids in by_type.items():
        has_block = slug in block_attrs
        gap = sum(1 for pid in pids if pid not in with_attrs)
        if has_block:
            block_empty_gap += gap
        else:
            no_block_gap += gap
    # Товар без tool_type тоже «тип без блока»: правил для него не существует.
    no_block_gap += sum(1 for pid in untyped if pid not in with_attrs)

    types_without_block = [s for s in by_type if s not in block_attrs]
    tail_types = [s for s, pids in by_type.items() if len(pids) < DEFAULT_TAIL_THRESHOLD]
    return {
        "products": total,
        "with_attributes": have,
        "with_attributes_pct": round(have * 100 / total, 1) if total else 0.0,
        "without_attributes": total - have,
        "without_attributes_no_block": no_block_gap,
        "without_attributes_block_empty": block_empty_gap,
        "untyped": len(untyped),
        "tool_types": len(by_type),
        "rule_blocks": len(block_attrs),
        "tool_types_without_block": len(types_without_block),
        "products_in_types_without_block": sum(len(by_type[s]) for s in types_without_block),
        "tail_types": len(tail_types),
        "tail_products": sum(len(by_type[s]) for s in tail_types),
    }


CUMULATIVE_MARKS = (10, 20, 50, 100, 150, 200)


def _checkpoints(sizes) -> dict[str, int]:
    checkpoints: dict[int, int] = {}
    running = 0
    for index, size in enumerate(sizes, start=1):
        running += size
        if index in CUMULATIVE_MARKS:
            checkpoints[index] = running
    for mark in CUMULATIVE_MARKS:
        if mark > len(sizes):
            checkpoints.setdefault(mark, running)
    return {str(k): v for k, v in sorted(checkpoints.items())}


def _cumulative_by_volume(by_type, block_attrs, with_attrs) -> dict:
    """Кумулятив по объёму: сколько товаров закрывают N крупнейших типов без блока.

    Отдельно от таблицы (та отсортирована по score) — это контрольный ряд для
    сверки с ручными замерами каталога.

    Рядов два, и их **нельзя путать** — именно на этом расходятся ручные замеры:

    ``all``
        все товары типов без блока. Отвечает на вопрос «какой объём каталога
        вообще относится к неописанным типам».
    ``gap``
        только товары **без характеристик**. Отвечает на вопрос «сколько
        товаров реально получат значения», и тип, полностью охарактеризованный
        вручную, в этот ряд не попадает вовсе — поэтому типов в нём меньше.
    """
    without_block = {slug: pids for slug, pids in by_type.items() if slug not in block_attrs}
    all_sizes = sorted((len(pids) for pids in without_block.values()), reverse=True)
    gap_sizes = sorted(
        (
            gap
            for pids in without_block.values()
            if (gap := sum(1 for pid in pids if pid not in with_attrs))
        ),
        reverse=True,
    )
    return {
        "all": {
            "types": len(all_sizes),
            "products": sum(all_sizes),
            "checkpoints": _checkpoints(all_sizes),
        },
        "gap": {
            "types": len(gap_sizes),
            "products": sum(gap_sizes),
            "checkpoints": _checkpoints(gap_sizes),
        },
    }


def _scope_meta(options, scope, totals) -> dict:
    return {
        "in_stock_only": options["in_stock_only"],
        "active_only": options["active_only"],
        "tool_type": scope["requested_tt"],
        "limit": options["limit"],
        "min_pattern_share": options["min_pattern_share"],
        "tail_threshold": options["tail_threshold"],
        "heterogeneity_dominance": options["heterogeneity_dominance"],
        "max_false_positive_rate": options["max_false_positive_rate"],
        "sales_min_share": options["sales_min_share"],
        "min_facet_fill_rate": options["min_facet_fill_rate"],
        "heterogeneity_min_heads": DEFAULT_HETEROGENEITY_MIN_HEADS,
        "heterogeneity_min_products": DEFAULT_HETEROGENEITY_MIN_PRODUCTS,
        "products": totals["products"],
        "read_only": True,
    }
