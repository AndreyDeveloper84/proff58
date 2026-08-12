"""Загрузка словаря характеристик из ``attribute_rules.json`` (Фаза B, #96).

Создаёт схему EAV по канону движка #99 (`data/attribute_rules.json`):
``Attribute`` (тип/единица/is_ai_feature), ``AttributeOption`` для select-характеристик
и привязку ``CategoryAttribute`` (is_filter/is_seo_facet) к категории из поля
``category`` блока tool_type.

Идемпотентна: существующий ``Attribute`` НЕ пересоздаётся — обновляются только
безопасные поля (``unit``/``is_filterable``/``is_ai_feature``); ручные правки имени/типа
не затираются. Сам движок извлечения (`attribute_extract.py`) тут не используется —
это загрузчик схемы, а не экстрактор.

Окно ХАР-PRE (2026-08-08) закрыло три дефекта загрузчика.

**1. Plan mode.** ``--dry-run``/``--plan`` не пишет в БД ничего: тот же код принимает
решения (create/update/keep/skip), расходится только финальный шаг — вместо записи
план уходит в machine-readable JSON (``--json-report <файл>``, иначе stdout;
человекочитаемая сводка тогда идёт в stderr). Окно применения может сверить план
с фактом, а не верить на слово.

**2. Пустое значение в правилах не перезаписывает непустое в БД.** Один и тот же
slug объявляется в нескольких блоках tool_type, и блок без ``unit`` молча стирал
единицу измерения, выставленную соседним блоком. Исторический случай — ``size``:
«Размер под ключ» (number, ``unit`` = «мм», блоки ``klyuchi-gaechnye``/``golovki``)
и «Размер» перчаток (select, ``unit`` не объявлен); в самом словаре он разведён
окном ХАР-SIZE на ``size``/``glove_size``, но механизм защиты общий и остаётся.
Защита узкая и намеренно ограничена строковым ``unit``
(:data:`EMPTY_PRESERVING_FIELDS`): у ``is_filterable``/``is_ai_feature`` значение
``False`` — это объявленное значение, а не «пусто», и подавлять его нельзя.

**3. Привязка категорий формализована.** Имя категории в дереве не уникально
(живой витринный узел и мёртвый легаси-дубль делят одно имя на ``depth=1``), а
``.first()`` брал меньший pk — то есть легаси. Теперь работает явная лестница
:meth:`Command._resolve_category`: живые кандидаты (``is_active`` AND ``on_site``)
имеют приоритет над мёртвыми; внутри отобранного множества приоритет у ``depth=1``
(обратная совместимость); если после этого кандидат не один — это ``ambiguous``,
и по умолчанию команда **падает**, а не гадает (``--allow-ambiguous`` — продолжить,
пропустив такие привязки). Отсутствие категории (``not_found``) по умолчанию
остаётся предупреждением с кодом причины: испортить оно ничего не может (привязки
просто не будет), а неполное дерево — штатное состояние bootstrap-а и тестов;
``--strict-bindings`` делает фатальным и его.

Окно ХАР-BIND (2026-08-09) закрыло четвёртый.

**4. Живость выбранного узла проверяется.** Лестница разрешала имя, но не смотрела,
жив ли найденный узел: единственный кандидат с ``is_active=False``/``on_site=False``
принимался молча (ветка «живых нет вовсе — работаем по всему множеству»). Привязка
создавалась и выглядела успешной, а на витрине не давала ничего: сам узел скрыт, а
живым потомкам характеристика не наследуется — фасет просто не появлялся. Ровно так
блок ``metchiki-plashki`` уезжал в мёртвую категорию «Метчики и плашки», пока товары
лежат в живых «Метчики»/«Плашки». Теперь у такого исхода свой код причины
``bound:*:dead`` и свой статус ``dead_category``: по умолчанию — WARNING с указанием
выбранного узла (fail-closed сломал бы bootstrap и наборы правил, где мёртвый узел
единственный), ``--strict-live-categories`` делает его фатальным.

Окно ХАР-BINDDIFF (2026-08-11) закрыло пятый.

**5. Флаги существующей привязки не перезаписываются молча.** ``update_or_create``
с ``defaults`` уместен только при создании: для уже существующей ``CategoryAttribute``
он побочным эффектом загрузки схемы затирал ``is_filter``/``is_seo_facet`` значениями
из файла правил. Настройка фасетов — это решение владельца каталога (её меняют
руками и командой ``catalog_seed_tool_type_filters``), а не следствие того, что
кто-то догрузил атрибуты. Теперь расхождение ``current`` ↔ ``planned`` — **отдельный
semantic update**: он всегда виден в плане (``changes`` строки привязки и счётчик
``summary.bindings.flag_diff``), но по умолчанию **не применяется** — строка остаётся
``keep``, а расхождение уходит в ``suppressed`` с причиной
``binding_flag_update_not_authorized``. Применить его можно только явным
разрешением ``--allow-binding-flag-updates`` (стиль ``--allow-ambiguous``: разрешение
на самостоятельное действие, а не ужесточение проверки). Создание привязки прежнее:
у новой строки флаги берутся из правил.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalog.ingest import data_dir
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    CategoryAttribute,
)

# kind словаря → тип атрибута модели. number храним как DECIMAL (value_decimal).
KIND_TO_TYPE = {
    "select": AttributeType.SELECT,
    "number": AttributeType.DECIMAL,
    "boolean": AttributeType.BOOLEAN,
}

# Безопасные для перезаписи поля Attribute (имя/тип/slug не трогаем у существующих).
SAFE_FIELDS = ("unit", "is_filterable", "is_ai_feature")

# Поля, где пустое значение из правил НЕ перезаписывает непустое в БД (см. модульный
# докстринг, дефект 2). Только строковые: у булевых «пусто» не существует.
EMPTY_PRESERVING_FIELDS = ("unit",)

# Признаки кандидата, попадающие в план: по ним владелец видит, почему выбран узел.
CANDIDATE_FIELDS = ("id", "slug", "depth", "is_active", "on_site", "is_site_v2")

# Суффикс кода причины для «узел найден, но мёртвый» (см. докстринг, дефект 4).
DEAD_SUFFIX = ":dead"

# Флаги привязки категория↔атрибут. У существующей строки они принадлежат владельцу
# каталога и меняются только с явным разрешением (см. докстринг, дефект 5).
BINDING_FLAGS = ("is_filter", "is_seo_facet")

# Причина, по которой расхождение флагов существующей привязки не применено.
BINDING_FLAG_SUPPRESS_REASON = "binding_flag_update_not_authorized"


class Command(BaseCommand):
    help = "Создать Attribute/AttributeOption/CategoryAttribute из data/attribute_rules.json."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=None, help="Каталог с attribute_rules.json")
        parser.add_argument(
            "--dry-run",
            "--plan",
            dest="dry_run",
            action="store_true",
            help=(
                "Ничего не писать в БД: построить machine-readable план "
                "create/update/keep/skip по атрибутам, вариантам и привязкам."
            ),
        )
        parser.add_argument(
            "--json-report",
            dest="json_report",
            default=None,
            help="Файл для machine-readable JSON-плана dry-run (иначе — stdout).",
        )
        parser.add_argument(
            "--allow-ambiguous",
            action="store_true",
            help=(
                "Продолжить, пропустив неоднозначные привязки (несколько живых "
                "категорий с одним именем). По умолчанию — fail-closed."
            ),
        )
        parser.add_argument(
            "--strict-bindings",
            action="store_true",
            help="Считать фатальным и отсутствие категории (not_found), не только ambiguous.",
        )
        parser.add_argument(
            "--strict-live-categories",
            action="store_true",
            help=(
                "Считать фатальной привязку к мёртвой категории (dead_category: узел "
                "найден, но is_active=False или on_site=False). По умолчанию — WARNING."
            ),
        )
        parser.add_argument(
            "--allow-binding-flag-updates",
            action="store_true",
            help=(
                "Разрешить менять is_filter/is_seo_facet у УЖЕ существующих привязок "
                "категория↔атрибут. По умолчанию текущие флаги сохраняются, а "
                "расхождение с правилами только показывается в плане."
            ),
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        base = options["path"] or data_dir()
        rules_path = Path(f"{base}/attribute_rules.json")
        data = json.loads(rules_path.read_text(encoding="utf-8"))

        plan = self._build_plan(
            data,
            str(rules_path),
            dry_run,
            allow_binding_flag_updates=options["allow_binding_flag_updates"],
        )
        self._enforce_binding_policy(
            plan,
            allow_ambiguous=options["allow_ambiguous"],
            strict_bindings=options["strict_bindings"],
            strict_live_categories=options["strict_live_categories"],
        )

        if dry_run:
            self._emit_plan(plan, options["json_report"])
            return ""

        self._apply(plan)
        summary = plan["summary"]
        self.stdout.write(
            self.style.SUCCESS(
                "Характеристики готовы. Атрибутов: {occurrences}, вариантов: {options}, "
                "привязок к категориям: {bound}.".format(
                    occurrences=plan["occurrences"],
                    options=summary["options"]["create"]
                    + summary["options"]["update"]
                    + summary["options"]["keep"],
                    bound=summary["bindings"]["create"]
                    + summary["bindings"]["update"]
                    + summary["bindings"]["keep"],
                )
            )
        )
        return str(plan["occurrences"])

    # ------------------------------------------------------------------ #
    # План (read-only): решения принимаются здесь и только здесь
    # ------------------------------------------------------------------ #

    def _build_plan(
        self,
        data: dict,
        rules_path: str,
        dry_run: bool,
        *,
        allow_binding_flag_updates: bool = False,
    ) -> dict:
        existing_attrs = {a.slug: a for a in Attribute.objects.all()}
        existing_options = {
            (o.attribute.slug, o.value): o
            for o in AttributeOption.objects.select_related("attribute")
        }
        existing_bindings = {
            (ca.category_id, ca.attribute.slug): ca
            for ca in CategoryAttribute.objects.select_related("attribute")
        }

        attr_rows: dict[str, dict] = {}
        option_rows: dict[tuple[str, str], dict] = {}
        binding_rows: dict[tuple[str, str], dict] = {}
        category_cache: dict[str, tuple] = {}
        occurrences = 0

        for tt in data.get("tool_types", []):
            tt_slug = tt.get("tool_type", "")
            category_name = tt.get("category")
            for a in tt.get("attributes", []):
                occurrences += 1
                self._plan_attribute(a, tt_slug, attr_rows, existing_attrs)
                if a.get("kind") == "select":
                    self._plan_options(a, option_rows, existing_options)
                if category_name:
                    self._plan_binding(
                        a,
                        tt_slug,
                        category_name,
                        binding_rows,
                        existing_bindings,
                        category_cache,
                        allow_binding_flag_updates,
                    )

        attributes = [attr_rows[s] for s in sorted(attr_rows)]
        options = [option_rows[k] for k in sorted(option_rows)]
        bindings = [binding_rows[k] for k in sorted(binding_rows)]
        for row in attributes:
            self._finalize_attribute(row)

        return {
            "command": "load_attributes",
            "dry_run": dry_run,
            "generated_at": timezone.now().isoformat(),
            "rules_path": rules_path,
            "occurrences": occurrences,
            "summary": {
                "attributes": _count_actions(attributes, ("create", "update", "keep")),
                "options": _count_actions(options, ("create", "update", "keep")),
                "bindings": _count_actions(bindings, ("create", "update", "keep", "skip"))
                | _count_statuses(bindings)
                | _count_flag_diff(bindings),
            },
            "attributes": attributes,
            "options": options,
            "bindings": bindings,
        }

    def _plan_attribute(
        self,
        a: dict,
        tt_slug: str,
        attr_rows: dict[str, dict],
        existing_attrs: dict[str, Attribute],
    ) -> None:
        slug = a["slug"]
        desired = {
            "unit": a.get("unit", ""),
            "is_filterable": a.get("is_filter", True),
            "is_ai_feature": a.get("is_ai_feature", False),
        }
        attribute_type = KIND_TO_TYPE.get(a.get("kind"), AttributeType.TEXT)

        row = attr_rows.get(slug)
        if row is None:
            obj = existing_attrs.get(slug)
            if obj is None:
                # Создаётся первым блоком; последующие блоки правят те же
                # безопасные поля поверх — ровно как делал get_or_create + update.
                current = None
                target = {
                    "name": a["name"],
                    "attribute_type": attribute_type,
                    **desired,
                }
            else:
                current = {
                    "name": obj.name,
                    "attribute_type": obj.attribute_type,
                    **{f: getattr(obj, f) for f in SAFE_FIELDS},
                }
                target = dict(current)
            row = {
                "slug": slug,
                "action": "create" if obj is None else "keep",
                "current": current,
                "target": target,
                "changes": [],
                "suppressed": [],
                "conflicts": [],
                "declared_in": [],
            }
            attr_rows[slug] = row

        if tt_slug not in row["declared_in"]:
            row["declared_in"].append(tt_slug)
        if row["target"]["attribute_type"] != attribute_type:
            conflict = {
                "field": "attribute_type",
                "kept": row["target"]["attribute_type"],
                "declared": attribute_type,
                "tool_type": tt_slug,
            }
            if conflict not in row["conflicts"]:
                row["conflicts"].append(conflict)

        for field in SAFE_FIELDS:
            new = desired[field]
            old = row["target"][field]
            if new == old:
                continue
            if field in EMPTY_PRESERVING_FIELDS and not new and old:
                entry = {"field": field, "from": old, "to": new, "reason": "empty_rule_value"}
                if entry not in row["suppressed"]:
                    row["suppressed"].append(entry)
                continue
            row["target"][field] = new

    @staticmethod
    def _finalize_attribute(row: dict) -> None:
        if row["action"] == "create":
            return
        changes = [
            {"field": f, "from": row["current"][f], "to": row["target"][f]}
            for f in SAFE_FIELDS
            if row["current"][f] != row["target"][f]
        ]
        row["changes"] = changes
        row["action"] = "update" if changes else "keep"

    def _plan_options(
        self,
        a: dict,
        option_rows: dict[tuple[str, str], dict],
        existing_options: dict[tuple[str, str], AttributeOption],
    ) -> None:
        for sort, opt in enumerate(a.get("options", [])):
            key = (a["slug"], opt["value"])
            target = {"slug": opt.get("slug", ""), "sort_order": sort}
            row = option_rows.get(key)
            if row is None:
                obj = existing_options.get(key)
                current = None if obj is None else {"slug": obj.slug, "sort_order": obj.sort_order}
                row = {
                    "attribute": a["slug"],
                    "value": opt["value"],
                    "action": "create" if obj is None else "keep",
                    "current": current,
                    "target": target,
                    "changes": [],
                }
                option_rows[key] = row
            else:
                row["target"] = target
            if row["current"] is not None:
                row["changes"] = [
                    {"field": f, "from": row["current"][f], "to": row["target"][f]}
                    for f in ("slug", "sort_order")
                    if row["current"][f] != row["target"][f]
                ]
                row["action"] = "update" if row["changes"] else "keep"

    def _plan_binding(
        self,
        a: dict,
        tt_slug: str,
        category_name: str,
        binding_rows: dict[tuple[str, str], dict],
        existing_bindings: dict[tuple[int, str], CategoryAttribute],
        category_cache: dict[str, tuple],
        allow_binding_flag_updates: bool = False,
    ) -> None:
        if category_name not in category_cache:
            category_cache[category_name] = self._resolve_category(category_name)
        category, reason, candidates = category_cache[category_name]

        key = (category_name, a["slug"])
        target = {
            "is_filter": a.get("is_filter", True),
            "is_seo_facet": a.get("is_seo_facet", False),
        }
        status = _binding_status(reason)

        if category is None:
            binding_rows[key] = {
                "category": category_name,
                "category_id": None,
                "attribute": a["slug"],
                "tool_type": tt_slug,
                "action": "skip",
                "status": status,
                "current": None,
                "target": target,
                "changes": [],
                "suppressed": [],
                "candidates": candidates,
                "reason": reason,
            }
            return

        existing = existing_bindings.get((category.pk, a["slug"]))
        current = None if existing is None else {f: getattr(existing, f) for f in BINDING_FLAGS}
        # Диф считаем всегда — владелец должен видеть расхождение независимо от того,
        # разрешено ли его применять (дефект 5).
        changes = (
            []
            if current is None
            else [
                {"field": f, "from": current[f], "to": target[f]}
                for f in BINDING_FLAGS
                if current[f] != target[f]
            ]
        )
        suppressed: list[dict] = []
        if current is None:
            action = "create"
        elif not changes:
            action = "keep"
        elif allow_binding_flag_updates:
            action = "update"
        else:
            # Без явного разрешения существующая привязка сохраняет свои флаги:
            # план показывает расхождение, но apply его не исполняет.
            action = "keep"
            suppressed = [dict(c, reason=BINDING_FLAG_SUPPRESS_REASON) for c in changes]

        binding_rows[key] = {
            "category": category_name,
            "category_id": category.pk,
            "attribute": a["slug"],
            "tool_type": tt_slug,
            "action": action,
            "status": status,
            "current": current,
            "target": target,
            "changes": changes,
            "suppressed": suppressed,
            "candidates": candidates,
            "reason": reason,
        }

    def _resolve_category(self, name: str) -> tuple[Category | None, str, list[dict]]:
        """Лестница разрешения имени категории: живые → топ → единственный.

        Возвращает ``(категория|None, код причины, кандидаты)``. Код причины:
        ``bound:top``/``bound:tree`` (+``:live``, если мёртвые кандидаты отброшены,
        +``:dead``, если живых кандидатов не было вовсе и выбран мёртвый узел),
        ``ambiguous:top``/``ambiguous:tree``, ``not_found``.
        """
        objects = list(Category.objects.filter(name=name).order_by("pk"))
        candidates = [{f: getattr(c, f) for f in CANDIDATE_FIELDS} for c in objects]
        if not objects:
            return None, "not_found", candidates

        # Живой узел витрины важнее мёртвого легаси-дубля с меньшим pk. Если живых
        # нет вовсе — работаем по всему множеству (обратная совместимость).
        live = [c for c in objects if c.is_active and c.on_site]
        pool = live or objects
        live_filter = bool(live) and len(live) < len(objects)

        # Топ-уровень имеет приоритет — обратная совместимость; если топа с таким
        # именем нет, а имя однозначно в дереве — биндим к точной под-категории
        # (напр. «Алмазные круги»), чтобы фасет не засорял всю топ-категорию.
        tops = [c for c in pool if c.depth == 1]
        scope = tops or pool
        level = "top" if tops else "tree"

        if len(scope) != 1:
            return None, f"ambiguous:{level}", candidates

        # Guard живости (ХАР-BIND): выбранный узел может быть мёртвым — тогда привязка
        # технически создастся, но фасета на витрине не даст. Это отдельный исход.
        node = scope[0]
        if not (node.is_active and node.on_site):
            suffix = DEAD_SUFFIX
        else:
            suffix = ":live" if live_filter else ""
        return node, f"bound:{level}{suffix}", candidates

    # ------------------------------------------------------------------ #
    # Политика привязок и вывод
    # ------------------------------------------------------------------ #

    def _enforce_binding_policy(
        self,
        plan: dict,
        *,
        allow_ambiguous: bool,
        strict_bindings: bool,
        strict_live_categories: bool = False,
    ) -> None:
        ambiguous = [r for r in plan["bindings"] if r["status"] == "ambiguous"]
        not_found = [r for r in plan["bindings"] if r["status"] == "not_found"]
        dead = [r for r in plan["bindings"] if r["status"] == "dead_category"]

        for row in ambiguous:
            names = ", ".join(_describe_candidate(c) for c in row["candidates"])
            self.stderr.write(
                self.style.WARNING(
                    f"  [{row['reason']}] «{row['category']}» → {row['attribute']}: "
                    f"кандидаты — {names}"
                )
            )
        for row in not_found:
            self.stderr.write(
                self.style.WARNING(
                    f"  [{row['reason']}] «{row['category']}» → {row['attribute']}: "
                    f"категории нет в дереве — сначала выполните build_categories."
                )
            )
        for row in dead:
            self.stderr.write(
                self.style.WARNING(
                    f"  [{row['reason']}] «{row['category']}» → {row['attribute']}: выбран "
                    f"{_chosen_candidate(row)} — узел мёртв, фасета на витрине не будет."
                )
            )

        if ambiguous and not allow_ambiguous:
            names = sorted({r["category"] for r in ambiguous})
            raise CommandError(
                "Неоднозначная привязка категорий: "
                + ", ".join(f"«{n}»" for n in names)
                + ". Переименуйте/деактивируйте дубль или запустите "
                "с --allow-ambiguous (привязки будут пропущены)."
            )
        if not_found and strict_bindings:
            names = sorted({r["category"] for r in not_found})
            raise CommandError(
                "Категории не найдены (--strict-bindings): " + ", ".join(f"«{n}»" for n in names)
            )
        if dead and strict_live_categories:
            names = sorted({r["category"] for r in dead})
            raise CommandError(
                "Привязка к мёртвой категории (--strict-live-categories): "
                + ", ".join(f"«{n}»" for n in names)
                + ". Укажите в правилах живой узел или оживите этот."
            )

    def _emit_plan(self, plan: dict, json_report: str | None) -> None:
        payload = json.dumps(plan, ensure_ascii=False, indent=2, default=str)
        summary = plan["summary"]
        human = (
            "ПЛАН load_attributes (dry-run, в БД не записано ничего)\n"
            f"  атрибуты:  создать {summary['attributes']['create']}, "
            f"изменить {summary['attributes']['update']}, "
            f"без изменений {summary['attributes']['keep']}\n"
            f"  варианты:  создать {summary['options']['create']}, "
            f"изменить {summary['options']['update']}, "
            f"без изменений {summary['options']['keep']}\n"
            f"  привязки:  создать {summary['bindings']['create']}, "
            f"изменить {summary['bindings']['update']}, "
            f"без изменений {summary['bindings']['keep']}, "
            f"пропущено {summary['bindings']['skip']} "
            f"(ambiguous {summary['bindings']['ambiguous']}, "
            f"not_found {summary['bindings']['not_found']})\n"
            f"  из них в мёртвые узлы: dead_category {summary['bindings']['dead_category']}\n"
            f"  существующих привязок с расхождением флагов: "
            f"{summary['bindings']['flag_diff']}"
        )
        for row in plan["bindings"]:
            if not row.get("changes") or row.get("current") is None:
                continue
            diff = ", ".join(f"{c['field']}: {c['from']!r} → {c['to']!r}" for c in row["changes"])
            mark = "=" if row["suppressed"] else "~"
            tail = " (сохранено, нет --allow-binding-flag-updates)" if row["suppressed"] else ""
            human += f"\n  {mark} привязка «{row['category']}» → {row['attribute']}: {diff}{tail}"
        for row in plan["bindings"]:
            if row["status"] != "dead_category":
                continue
            human += (
                f"\n  ! «{row['category']}» → {row['attribute']} ({row['tool_type']}): "
                f"выбран {_chosen_candidate(row)}, причина {row['reason']}"
            )
        for row in plan["attributes"]:
            if row["action"] == "update":
                changes = ", ".join(
                    f"{c['field']}: {c['from']!r} → {c['to']!r}" for c in row["changes"]
                )
                human += f"\n  ~ {row['slug']}: {changes}"
            if row["suppressed"]:
                for s in row["suppressed"]:
                    human += (
                        f"\n  = {row['slug']}: {s['field']} {s['from']!r} сохранено "
                        f"(в правилах пусто, {s['reason']})"
                    )

        if json_report:
            Path(json_report).write_text(payload, encoding="utf-8")
            self.stdout.write(human)
            self.stdout.write(self.style.SUCCESS(f"JSON-план: {json_report}"))
        else:
            self.stderr.write(human)
            self.stdout.write(payload)

    # ------------------------------------------------------------------ #
    # Применение: исполняет решения плана, своих решений не принимает
    # ------------------------------------------------------------------ #

    def _apply(self, plan: dict) -> None:
        with transaction.atomic():
            attrs: dict[str, Attribute] = {}
            for row in plan["attributes"]:
                target = row["target"]
                if row["action"] == "create":
                    attrs[row["slug"]] = Attribute.objects.create(
                        slug=row["slug"],
                        name=target["name"],
                        attribute_type=target["attribute_type"],
                        **{f: target[f] for f in SAFE_FIELDS},
                    )
                    continue
                attribute = Attribute.objects.get(slug=row["slug"])
                if row["action"] == "update":
                    fields = [c["field"] for c in row["changes"]]
                    for field in fields:
                        setattr(attribute, field, target[field])
                    attribute.save(update_fields=fields)
                attrs[row["slug"]] = attribute

            for row in plan["options"]:
                AttributeOption.objects.update_or_create(
                    attribute=attrs[row["attribute"]],
                    value=row["value"],
                    defaults=dict(
                        slug=row["target"]["slug"], sort_order=row["target"]["sort_order"]
                    ),
                )

            for row in plan["bindings"]:
                # keep/skip не пишем вообще: у существующей привязки флаги остаются
                # такими, как есть (дефект 5), а skip — это нерешённая категория.
                if row["action"] not in ("create", "update"):
                    continue
                defaults = {f: row["target"][f] for f in BINDING_FLAGS}
                if row["action"] == "create":
                    # get_or_create, а не update_or_create: если привязка появилась
                    # между планом и записью — это уже существующая строка, и её
                    # флаги молча не перезаписываются.
                    CategoryAttribute.objects.get_or_create(
                        category_id=row["category_id"],
                        attribute=attrs[row["attribute"]],
                        defaults=defaults,
                    )
                    continue
                CategoryAttribute.objects.update_or_create(
                    category_id=row["category_id"],
                    attribute=attrs[row["attribute"]],
                    defaults=defaults,
                )


def _count_actions(rows: list[dict], actions: tuple[str, ...]) -> dict[str, int]:
    counts = {a: 0 for a in actions}
    for row in rows:
        counts[row["action"]] = counts.get(row["action"], 0) + 1
    return counts


def _count_statuses(rows: list[dict]) -> dict[str, int]:
    counts = {"bound": 0, "dead_category": 0, "ambiguous": 0, "not_found": 0}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return counts


def _count_flag_diff(rows: list[dict]) -> dict[str, int]:
    """Сколько СУЩЕСТВУЮЩИХ привязок расходятся с правилами по флагам.

    Считается независимо от ``--allow-binding-flag-updates``: это масштаб проблемы —
    ровно столько строк прежняя логика (``update_or_create`` с ``defaults``)
    перезаписывала бы молча.
    """
    return {
        "flag_diff": sum(1 for row in rows if row.get("current") is not None and row["changes"])
    }


def _binding_status(reason: str) -> str:
    """Код причины → статус строки плана. ``bound:*:dead`` — свой статус, не ``bound``."""
    if reason.endswith(DEAD_SUFFIX):
        return "dead_category"
    return reason.split(":")[0]


def _describe_candidate(candidate: dict) -> str:
    return (
        f"#{candidate['id']} {candidate['slug']} (depth={candidate['depth']}, "
        f"active={candidate['is_active']}, on_site={candidate['on_site']})"
    )


def _chosen_candidate(row: dict) -> str:
    """Описание узла, который лестница выбрала для строки плана."""
    chosen = next((c for c in row["candidates"] if c["id"] == row["category_id"]), None)
    return _describe_candidate(chosen) if chosen else f"#{row['category_id']}"
