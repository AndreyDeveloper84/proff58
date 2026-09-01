"""Удаление ранее записанных характеристик по карантинным товарам (трек P2).

Карантин (``apps.catalog.attribute_quarantine``) запрещает движку писать НОВЫЕ
значения, но **никогда** не удаляет уже записанные — иначе одна строка в реестре
молча стирала бы данные (см. prune-цикл ``enrich_attributes``). Уборка вынесена
сюда и требует отдельной авторизации.

Контур команды повторяет общий playbook каталога:

* **dry-run по умолчанию** — без ``--apply`` не удаляется ничего;
* перед записью обязателен **снимок удаляемого** (``--snapshot``): product_id +
  slug атрибута + значение + источник. Ключ восстановления — пара
  ``product_id + attribute``, а НЕ ``pav_id``: после удаления id не возвращается;
* удаление и чистка ``attrs_cache`` — одной транзакцией;
* **post-audit** после записи: те же пары перечитываются из БД, остаток обязан
  быть нулевым.

Что именно удаляется: только значения, которыми владеет движок
(``source ∈ PRUNABLE_SOURCES`` — regex/keyword/inferred). Ручные, 1С- и
llm-значения не трогаются: карантин заводится против движка, а не против
оператора (тот же инвариант, что у prune в ``enrich_attributes``).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalog import attribute_quarantine as quarantine
from apps.catalog.attrs_cache import flush_attrs_cache_merged
from apps.catalog.ingest import data_dir

# Единственное определение множества «источники движка» живёт в enrich_attributes:
# уборка обязана резать ровно то, что пишет прогон, иначе контуры разъедутся.
from apps.catalog.management.commands.enrich_attributes import PRUNABLE_SOURCES
from apps.catalog.models import Product, ProductAttributeValue
from apps.catalog.read_models import attr_value_to_json

TOOL_TYPE_SLUG = "tool_type"


class Command(BaseCommand):
    help = (
        "Удалить ранее записанные движком характеристики по карантинным товарам "
        "(dry-run по умолчанию; запись — только с --apply и снимком)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--path", default=None, help="Каталог с attribute_rules.json")
        parser.add_argument(
            "--quarantine",
            dest="quarantine",
            default=None,
            metavar="FILE",
            help=f"Файл реестра карантина (по умолчанию <--path|data>/{quarantine.FILENAME}).",
        )
        parser.add_argument(
            "--snapshot",
            dest="snapshot",
            default=None,
            metavar="FILE",
            help="JSON-снимок удаляемого. Обязателен вместе с --apply.",
        )
        parser.add_argument(
            "--apply",
            dest="apply",
            action="store_true",
            help="Выполнить удаление. Без флага — только план (ничего не пишется).",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        snapshot_path = options["snapshot"]
        base = options["path"] or data_dir()
        rules_path = Path(f"{base}/attribute_rules.json")
        raw = json.loads(rules_path.read_text(encoding="utf-8"))
        managed_slugs = {a["slug"] for tt in raw.get("tool_types", []) for a in tt["attributes"]}
        managed_by_tt = {
            tt["tool_type"]: {a["slug"] for a in tt["attributes"]}
            for tt in raw.get("tool_types", [])
        }

        if apply and not snapshot_path:
            raise CommandError("--apply требует --snapshot: удаление без снимка запрещено.")

        registry_path = options["quarantine"] or quarantine.default_registry_path(base)
        try:
            registry = quarantine.load_registry(registry_path, managed_slugs=managed_slugs)
        except quarantine.QuarantineError as exc:
            raise CommandError(f"Реестр карантина отвергнут: {exc}") from exc

        declared_ids = registry.product_ids
        if declared_ids:
            known_ids = set(
                Product.objects.filter(pk__in=declared_ids).values_list("pk", flat=True)
            )
            unknown_ids = sorted(set(declared_ids) - known_ids)
            if unknown_ids:
                raise CommandError(
                    f"Реестр карантина {registry.path}: товары не найдены в каталоге: "
                    f"{unknown_ids}."
                )
        for entry in registry.expired:
            self.stderr.write(
                f"ВНИМАНИЕ: карантин товара {entry.product_id} истёк "
                f"{entry.expires_at.isoformat()} — уборка по нему не выполняется."
            )

        effective = registry.effective
        if not effective:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Карантин {registry.path}: действующих записей нет — убирать нечего."
                )
            )
            return ""

        # tool_type карантинных товаров: нужен, чтобы понять managed-множество блока.
        product_tt = {
            row["product_id"]: row["value_option__slug"]
            for row in ProductAttributeValue.objects.filter(
                product_id__in=list(effective),
                attribute__slug=TOOL_TYPE_SLUG,
                value_option__isnull=False,
            ).values("product_id", "value_option__slug")
        }

        # Пары (товар → слуги, которые защищает карантин и потому подлежат уборке).
        target: dict[int, set[str]] = {}
        for product_id, entry in effective.items():
            if entry.is_whole_product:
                tt_slug = product_tt.get(product_id)
                if tt_slug is None:
                    self.stderr.write(
                        f"ВНИМАНИЕ: товар {product_id} без tool_type — managed-множество "
                        "блока неизвестно, уборка по нему пропущена."
                    )
                    continue
                slugs = set(managed_by_tt.get(tt_slug, ()))
                if not slugs:
                    self.stderr.write(
                        f"ВНИМАНИЕ: для tool_type {tt_slug!r} (товар {product_id}) нет блока "
                        "правил — убирать нечего."
                    )
                    continue
            else:
                slugs = set(entry.attributes)
            target[product_id] = slugs

        pavs = (
            ProductAttributeValue.objects.filter(
                product_id__in=list(target), attribute__slug__in=managed_slugs
            )
            .select_related("attribute", "value_option")
            .order_by("product_id", "attribute__slug")
        )
        doomed = [
            pav
            for pav in pavs
            if pav.attribute.slug in target.get(pav.product_id, ())
            and pav.source in PRUNABLE_SOURCES
        ]

        items = [
            {
                "product_id": pav.product_id,
                "attribute": pav.attribute.slug,
                "value": attr_value_to_json(pav),
                "source": pav.source,
                "confidence": pav.confidence,
                "pav_id": pav.pk,
            }
            for pav in doomed
        ]
        by_attribute: dict[str, int] = {}
        for item in items:
            by_attribute[item["attribute"]] = by_attribute.get(item["attribute"], 0) + 1

        payload = {
            "command": "catalog_attribute_cleanup_quarantine",
            "mode": "apply" if apply else "dry-run",
            "generated_at": timezone.now().isoformat(),
            "quarantine_path": str(registry.path),
            "rules_path": str(rules_path),
            "quarantine": registry.meta(),
            "totals": {
                "products": len({item["product_id"] for item in items}),
                "values": len(items),
                "by_attribute": by_attribute,
            },
            "items": items,
        }

        if snapshot_path:
            # Снимок пишется ДО удаления — и в dry-run тоже (это план уборки).
            Path(snapshot_path).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default) + "\n",
                encoding="utf-8",
            )

        summary = (
            f"Карантин {registry.path}: действующих записей {len(effective)}, "
            f"к удалению {len(items)} значений на "
            f"{payload['totals']['products']} товарах"
            + (
                " (" + ", ".join(f"{k}: {v}" for k, v in sorted(by_attribute.items())) + ")"
                if by_attribute
                else ""
            )
            + "."
        )

        if not apply:
            self.stdout.write(self.style.SUCCESS(f"dry-run: {summary} Ничего не удалено."))
            if snapshot_path:
                self.stdout.write(self.style.SUCCESS(f"dry-run: план записан в {snapshot_path}"))
            return ""

        if not items:
            self.stdout.write(self.style.SUCCESS(f"{summary} Удалять нечего — no-op."))
            return ""

        doomed_ids = [item["pav_id"] for item in items]
        removed_by_product: dict[int, set[str]] = {}
        for item in items:
            removed_by_product.setdefault(item["product_id"], set()).add(item["attribute"])

        with transaction.atomic():
            deleted, _ = ProductAttributeValue.objects.filter(id__in=doomed_ids).delete()
            products = list(Product.objects.filter(id__in=list(removed_by_product)))
            for product in products:
                cache = dict(product.attrs_cache or {})
                for slug in removed_by_product[product.id]:
                    cache.pop(slug, None)
                product.attrs_cache = cache
            flush_attrs_cache_merged(products, lambda p: removed_by_product[p.id])

        # --- post-audit: пары обязаны исчезнуть -------------------------------
        left = [
            f"{pav.product_id}/{pav.attribute.slug}"
            for pav in ProductAttributeValue.objects.filter(
                product_id__in=list(removed_by_product), attribute__slug__in=managed_slugs
            ).select_related("attribute")
            if pav.attribute.slug in removed_by_product.get(pav.product_id, ())
            and pav.source in PRUNABLE_SOURCES
        ]
        cache_left = [
            f"{product.id}/{slug}"
            for product in Product.objects.filter(id__in=list(removed_by_product))
            for slug in removed_by_product[product.id]
            if slug in (product.attrs_cache or {})
        ]
        if left or cache_left:
            raise CommandError(
                "post-audit: после уборки остались значения "
                f"{sorted(left)} и ключи attrs_cache {sorted(cache_left)}."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"{summary} Удалено PAV: {deleted}. Снимок: {snapshot_path}. "
                "post-audit: остатков нет."
            )
        )
        return ""


def _json_default(value):
    if isinstance(value, date):
        return value.isoformat()
    return str(value)
