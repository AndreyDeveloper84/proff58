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
4. Считает Rule Impact Score и выдаёт список типов по убыванию выгоды.

Rule Impact Score
-----------------
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

Статусы
-------
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
from apps.catalog.rule_discovery import PATTERNS, corpus_heterogeneity, head_token, scan_names
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

        scope = self._collect_scope(options)
        if not scope["products"]:
            self.stdout.write(self.style.WARNING("Скоуп пуст — ни одного товара."))
        report = self._analyse(scope, block_attrs, options)
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
            for row in Category.objects.values("pk", "path", "depth", "is_active", "on_site")
        }
        faceted = set(
            CategoryAttribute.objects.filter(is_filter=True)
            .values_list("category_id", flat=True)
            .distinct()
        )

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
            "requested_tt": requested_tt,
            "known_attributes": set(Attribute.objects.values_list("slug", flat=True)),
        }

    # ------------------------------------------------------------------ #
    # Анализ
    # ------------------------------------------------------------------ #

    def _analyse(self, scope, block_attrs, options) -> dict:
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

        rows = []
        for slug, pids in by_type.items():
            rows.append(
                self._analyse_type(
                    slug,
                    pids,
                    scope=scope,
                    block_attrs=block_attrs,
                    ancestors=ancestors,
                    sales_absent=sales_absent,
                    min_share=min_share,
                    max_fp_rate=max_fp_rate,
                    tail_threshold=tail_threshold,
                    dominance_threshold=dominance_threshold,
                    n_examples=n_examples,
                )
            )
        rows.sort(key=lambda r: (-r["score"], -r["products"], r["tool_type"]))

        totals = _totals(scope, by_type, untyped, block_attrs)
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
        ancestors,
        sales_absent,
        min_share,
        max_fp_rate,
        tail_threshold,
        dominance_threshold,
        n_examples,
    ) -> dict:
        products = scope["products"]
        names = [products[pid]["original_name"] or products[pid]["name"] or "" for pid in pids]
        total = len(pids)

        hits = scan_names(names, examples=n_examples)
        covered = block_attrs.get(slug)
        has_block = covered is not None
        covered = covered or set()

        set_head_share = _set_head_share(names)
        is_set = _is_set_type(slug, set_head_share)

        patterns_out = []
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

        hetero = corpus_heterogeneity(names)
        heterogeneous = (
            total >= DEFAULT_HETEROGENEITY_MIN_PRODUCTS
            and hetero.dominance < dominance_threshold
            and hetero.distinct_heads >= DEFAULT_HETEROGENEITY_MIN_HEADS
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

        out.write("\n=== Кандидаты (по убыванию Rule Impact Score) ===")
        header = (
            f"{'#':>3} {'tool_type':32} {'тов':>5} {'без хар':>7} {'блок':>7} "
            f"{'нов':>3} {'sales':>5} {'extr':>5} {'facet':>5} {'score':>9} "
            f"{'кум%':>5}  статус"
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
                f"{factors['attributes']:>3} {factors['sales_weight']:>5.2f} "
                f"{factors['extraction_confidence']:>5.2f} "
                f"{factors['facet_visibility']:>5.2f} {row['score']:>9.1f} "
                f"{cumulative * 100 // gap_total:>4}%  {row['status']}"
            )
        if limit and len(rows) > limit:
            out.write(f"... и ещё {len(rows) - limit} типов (см. --json-report)")

        out.write("\n=== Что предлагается писать (топ показанных) ===")
        for row in shown:
            # Предложения печатаем при любом статусе: блокер объясняет, что
            # мешает, но не отменяет уже посчитанную картину — оператору нужно
            # видеть, ради чего блокер стоит снимать.
            out.write(
                f"\n{row['tool_type']} ({row['products']} тов., "
                f"score {row['score']}) — {row['status']}: {row['reason']}"
            )
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

    out.append("## Кандидаты (по убыванию Rule Impact Score)")
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
                    f"{factors['sales_weight']:.2f}",
                    f"{factors['extraction_confidence']:.2f}",
                    f"{factors['facet_visibility']:.2f}",
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
                    "sales",
                    "extr",
                    "facet",
                    "Score",
                    "Кум. %",
                    "Статус",
                ],
                ["---:", "---", "---:", "---:", "---", "---:", "---:", "---:", "---:", "---:"]
                + ["---:", "---"],
                table_rows,
            )
        )
        out.append("")
        if limit and len(rows) > limit:
            out.append(f"… и ещё {len(rows) - limit} типов (полный список — в `--json-report`).")
            out.append("")

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


def _markdown_candidate(index: int, row: dict) -> list[str]:
    """Раздел одного кандидата: предлагаемые оси с числами и примерами."""
    out = [
        f"### {index}. {_md_code(row['tool_type'])} — {row['products']} тов., "
        f"score {row['score']}",
        "",
        f"**{row['status']}:** {_md_cell(row['reason'])}",
        "",
    ]
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
        "heterogeneity_min_heads": DEFAULT_HETEROGENEITY_MIN_HEADS,
        "heterogeneity_min_products": DEFAULT_HETEROGENEITY_MIN_PRODUCTS,
        "products": totals["products"],
        "read_only": True,
    }
