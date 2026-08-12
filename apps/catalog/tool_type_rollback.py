"""Откат применённого ``tool_type``: снимок → план → применение (Wave 7.1 / Stage H5).

Контур обратимости применённых предложений. Форвардный путь (``enrich_tool_type``,
apply-pipeline) здесь не меняется и не вызывается — модуль работает поверх уже
случившегося изменения.

Процедура по ``docs/catalog/operations/rollback.md``: снимок «до» → (запись) →
снимок «после» → откат → post-audit. Откат исполняется по **паре** снимков:

- ``from`` — состояние, которое ожидается в БД сейчас (что записал forward-прогон);
- ``to`` — состояние, к которому возвращаемся (снимок «до»).

Решение по каждому товару принимается только сравнением с обоими снимками:

- live == ``to``   → ``noop``     (уже откачено; отсюда идемпотентность);
- live == ``from`` → ``write``    (штатный откат);
- иначе            → ``conflict`` (baseline изменился — молчаливой перезаписи нет).

Fail-closed: план с любым конфликтом не применяется целиком; запись идёт одной
транзакцией, поэтому частичный сбой не оставляет полуприменённого состояния.
План строится **вне** транзакции записи, поэтому ``apply_rollback`` берёт строки
под ``select_for_update`` и повторяет сверку baseline тем же решающим правилом
(``_decide``) уже внутри транзакции (H6): чужая запись, успевшая пройти между
планом и применением, даёт conflict, а не молчаливую перезапись. Товар, который
кто-то уже привёл к цели, считается ``noop`` — идемпотентность сохраняется.
Опции ``tool_type`` модуль не создаёт (инвариант manifest-only): целевой slug
обязан существовать в live-словаре.

Каноническая сериализация снимка — та же рецептура, что у release manifest (H3):
``rules_release.canonical_bytes`` / ``canonical_hash_of``. Два прогона на
неизменной БД дают побайтово идентичный файл.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from django.db import transaction

from apps.catalog.attrs_cache import flush_attrs_cache_merged
from apps.catalog.models import Attribute, AttributeOption, Product, ProductAttributeValue
from apps.catalog.rules_release import canonical_bytes, canonical_hash_of
from apps.catalog.taxonomy_manifest import taxonomy_identity_hash

TOOL_TYPE_SLUG = "tool_type"
SNAPSHOT_SCHEMA_VERSION = 1
CACHE_KEY = "tool_type"

EXIT_OK = 0
EXIT_CONFLICT = 1
EXIT_INVALID = 2
EXIT_INTERNAL = 3

DECISION_NOOP = "noop"
DECISION_WRITE = "write"
DECISION_CONFLICT = "conflict"


class RollbackError(ValueError):
    """Невалидные артефакты отката или отказ применять неисполнимый план."""


# --- снимок ---


def live_taxonomy_identity() -> str:
    """Identity hash live-словаря ``tool_type`` (та же рецептура, что в H1)."""
    options = AttributeOption.objects.filter(attribute__slug=TOOL_TYPE_SLUG).values("slug", "value")
    return taxonomy_identity_hash(list(options))


def _selected_ids(
    product_ids: Iterable[int] | None,
    option_slugs: Iterable[str] | None,
    all_with_tool_type: bool,
) -> tuple[dict, list[int]]:
    selectors = [product_ids is not None, option_slugs is not None, bool(all_with_tool_type)]
    if sum(1 for s in selectors if s) != 1:
        raise RollbackError(
            "снимок требует ровно один селектор: product_ids | option_slugs | all_with_tool_type"
        )
    if product_ids is not None:
        ids = sorted({int(pid) for pid in product_ids})
        found = set(Product.objects.filter(id__in=ids).values_list("id", flat=True))
        missing = [pid for pid in ids if pid not in found]
        if missing:
            raise RollbackError(f"товары не найдены: {missing[:20]}")
        return {"kind": "explicit_ids", "value": ids}, ids
    if option_slugs is not None:
        slugs = sorted({str(s) for s in option_slugs})
        live = set(
            AttributeOption.objects.filter(
                attribute__slug=TOOL_TYPE_SLUG, slug__in=slugs
            ).values_list("slug", flat=True)
        )
        unknown = [s for s in slugs if s not in live]
        if unknown:
            raise RollbackError(f"option slug нет в live-словаре tool_type: {unknown}")
        ids = sorted(
            ProductAttributeValue.objects.filter(
                attribute__slug=TOOL_TYPE_SLUG, value_option__slug__in=slugs
            ).values_list("product_id", flat=True)
        )
        return {"kind": "option_slugs", "value": slugs}, ids
    ids = sorted(
        ProductAttributeValue.objects.filter(attribute__slug=TOOL_TYPE_SLUG).values_list(
            "product_id", flat=True
        )
    )
    return {"kind": "all_with_tool_type", "value": []}, ids


def _rows_for(product_ids: list[int]) -> list[dict]:
    """Строки снимка по явному списку id (отсутствующие товары пропускаются)."""
    caches = dict(Product.objects.filter(id__in=product_ids).values_list("id", "attrs_cache"))
    pavs = {
        pav.product_id: pav
        for pav in ProductAttributeValue.objects.filter(
            attribute__slug=TOOL_TYPE_SLUG, product_id__in=product_ids
        ).select_related("value_option")
    }
    rows = []
    for pid in sorted(product_ids):
        if pid not in caches:
            continue
        pav = pavs.get(pid)
        option = pav.value_option if pav is not None else None
        cache = caches.get(pid) or {}
        rows.append(
            {
                "product_id": pid,
                "option_slug": option.slug if option is not None else None,
                "option_value": option.value if option is not None else None,
                "attrs_cache_tool_type": cache.get(CACHE_KEY),
            }
        )
    return rows


def build_snapshot(
    *,
    product_ids: Iterable[int] | None = None,
    option_slugs: Iterable[str] | None = None,
    all_with_tool_type: bool = False,
) -> dict:
    """Read-only снимок состояния ``tool_type`` по явному множеству товаров."""
    selector, ids = _selected_ids(product_ids, option_slugs, all_with_tool_type)
    rows = _rows_for(ids)
    canonical = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "attribute_slug": TOOL_TYPE_SLUG,
        "selector": selector,
        "live_taxonomy_identity_hash": live_taxonomy_identity(),
        "rows_count": len(rows),
        "rows": rows,
    }
    return {"canonical": canonical, "canonical_hash": canonical_hash_of(canonical)}


def snapshot_bytes(doc: dict) -> bytes:
    """Канонические байты снимка (byte-stable между прогонами)."""
    return canonical_bytes(doc)


def validate_snapshot(doc, *, label: str = "snapshot") -> dict:
    """Fail-closed проверка структуры и самосогласованности снимка."""
    if not isinstance(doc, dict) or not isinstance(doc.get("canonical"), dict):
        raise RollbackError(f"{label}: нет секции canonical")
    canonical = doc["canonical"]
    actual = canonical_hash_of(canonical)
    if doc.get("canonical_hash") != actual:
        raise RollbackError(
            f"{label}: canonical_hash не соответствует содержимому "
            f"(записан {doc.get('canonical_hash')!r}, пересчитан {actual!r})"
        )
    if canonical.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise RollbackError(
            f"{label}: неподдерживаемый schema_version {canonical.get('schema_version')!r}"
        )
    if canonical.get("attribute_slug") != TOOL_TYPE_SLUG:
        raise RollbackError(f"{label}: снимок не по атрибуту {TOOL_TYPE_SLUG}")
    rows = canonical.get("rows")
    if not isinstance(rows, list):
        raise RollbackError(f"{label}: rows должен быть списком")
    ids = [r.get("product_id") for r in rows]
    if len(ids) != len(set(ids)):
        raise RollbackError(f"{label}: дубликаты product_id в rows")
    if canonical.get("rows_count") != len(rows):
        raise RollbackError(f"{label}: rows_count не совпадает с числом строк")
    return doc


def load_snapshot(path: Path | str, *, label: str = "snapshot") -> dict:
    """Прочитать снимок с диска с проверкой самосогласованности."""
    path = Path(path)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RollbackError(f"{label}: файл не найден: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RollbackError(f"{label}: не валидный JSON ({path}): {exc}") from exc
    return validate_snapshot(doc, label=label)


# --- план ---


@dataclass(frozen=True)
class RollbackPlan:
    """Решение по каждому товару + целевой снимок (для post-audit)."""

    entries: tuple[dict, ...]
    target_doc: dict
    source_doc: dict

    @property
    def counts(self) -> dict:
        return {
            DECISION_NOOP: sum(1 for e in self.entries if e["decision"] == DECISION_NOOP),
            DECISION_WRITE: sum(1 for e in self.entries if e["decision"] == DECISION_WRITE),
            DECISION_CONFLICT: sum(1 for e in self.entries if e["decision"] == DECISION_CONFLICT),
        }

    @property
    def conflicts(self) -> list[dict]:
        return [e for e in self.entries if e["decision"] == DECISION_CONFLICT]

    @property
    def writes(self) -> list[dict]:
        return [e for e in self.entries if e["decision"] == DECISION_WRITE]

    @property
    def feasible(self) -> bool:
        return not self.conflicts


def plan_rollback(from_doc: dict, to_doc: dict) -> RollbackPlan:
    """Сопоставить пару снимков с живой БД. Ничего не пишет."""
    validate_snapshot(from_doc, label="from")
    validate_snapshot(to_doc, label="to")
    from_rows = {r["product_id"]: r for r in from_doc["canonical"]["rows"]}
    to_rows = {r["product_id"]: r for r in to_doc["canonical"]["rows"]}
    if set(from_rows) != set(to_rows):
        only_from = sorted(set(from_rows) - set(to_rows))[:10]
        only_to = sorted(set(to_rows) - set(from_rows))[:10]
        raise RollbackError(
            "снимки покрывают разные множества товаров: "
            f"только в from={only_from}, только в to={only_to}"
        )

    live_slugs = set(
        AttributeOption.objects.filter(attribute__slug=TOOL_TYPE_SLUG).values_list(
            "slug", flat=True
        )
    )
    targets = {r["option_slug"] for r in to_rows.values() if r["option_slug"] is not None}
    unknown = sorted(targets - live_slugs)
    if unknown:
        raise RollbackError(
            "целевых option slug нет в live-словаре tool_type (опции создаются только "
            f"из манифеста): {unknown}"
        )

    live_identity = live_taxonomy_identity()
    for label, doc in (("from", from_doc), ("to", to_doc)):
        recorded = doc["canonical"].get("live_taxonomy_identity_hash")
        if recorded != live_identity:
            raise RollbackError(
                f"{label}: taxonomy_identity дрейфовал с момента снимка "
                f"(снимок {recorded!r}, live {live_identity!r}) — переплан обязателен"
            )

    live_rows = {r["product_id"]: r for r in _rows_for(sorted(from_rows))}
    entries: list[dict] = []
    for pid in sorted(from_rows):
        src, dst = from_rows[pid], to_rows[pid]
        live = live_rows.get(pid)
        entry = {
            "product_id": pid,
            "from_option_slug": src["option_slug"],
            "to_option_slug": dst["option_slug"],
            "to_attrs_cache_tool_type": dst["attrs_cache_tool_type"],
            "live_option_slug": live["option_slug"] if live is not None else None,
        }
        decision, reason = _decide(live, src["option_slug"], dst["option_slug"])
        entry.update(decision=decision, reason=reason)
        entries.append(entry)
    return RollbackPlan(entries=tuple(entries), target_doc=to_doc, source_doc=from_doc)


def _decide(live_row: dict | None, from_slug: str | None, to_slug: str | None) -> tuple[str, str]:
    """Решение по одному товару: сравнение live с парой снимков.

    Общая точка для плана и для повторной сверки внутри транзакции записи —
    так «что решил план» и «что проверяет apply» не могут разъехаться.
    """
    if live_row is None:
        return DECISION_CONFLICT, "product_missing"
    if live_row["option_slug"] == to_slug:
        return DECISION_NOOP, "already_at_target"
    if live_row["option_slug"] == from_slug:
        return DECISION_WRITE, "baseline_matches_from"
    return DECISION_CONFLICT, "baseline_changed"


# --- применение ---


def apply_rollback(plan: RollbackPlan) -> dict:
    """Применить план одной транзакцией. Конфликтный план не применяется вовсе."""
    counts = plan.counts
    if not plan.feasible:
        sample = [f"{e['product_id']}:{e['reason']}" for e in plan.conflicts[:10]]
        raise RollbackError(
            f"откат отклонён: conflict по {counts[DECISION_CONFLICT]} товарам "
            f"(baseline изменился) — {sample}"
        )
    writes = plan.writes
    if not writes:
        return {"written": 0, "noop": counts[DECISION_NOOP]}

    with transaction.atomic():
        attribute = Attribute.objects.filter(slug=TOOL_TYPE_SLUG).first()
        if attribute is None:
            raise RollbackError("атрибут tool_type не найден")
        option_by_slug = {o.slug: o for o in attribute.options.all()}

        # План строился вне этой транзакции. Берём строки под блокировку и
        # повторяем сверку baseline тем же решающим правилом: чужая запись,
        # успевшая пройти между планом и применением, обязана дать conflict,
        # а не молчаливую перезапись. Порядок по id — против взаимных дедлоков.
        write_ids = sorted(e["product_id"] for e in writes)
        list(Product.objects.select_for_update().filter(id__in=write_ids).order_by("id"))
        list(
            ProductAttributeValue.objects.select_for_update()
            .filter(attribute=attribute, product_id__in=write_ids)
            .order_by("product_id")
        )
        live_now = {r["product_id"]: r for r in _rows_for(write_ids)}
        drifted: list[str] = []
        settled = 0
        applicable: list[dict] = []
        for entry in writes:
            decision, reason = _decide(
                live_now.get(entry["product_id"]),
                entry["from_option_slug"],
                entry["to_option_slug"],
            )
            pid = entry["product_id"]
            if decision == DECISION_WRITE:
                applicable.append(entry)
            elif decision == DECISION_NOOP:
                settled += 1  # чужой процесс уже привёл товар к цели
            elif reason == "product_missing":
                raise RollbackError(f"товар {pid} исчез между планом и применением")
            else:
                drifted.append(f"{pid}:{reason}:live={live_now[pid]['option_slug']!r}")
        if drifted:
            raise RollbackError(
                f"откат отклонён: baseline изменился между планом и применением "
                f"по {len(drifted)} товарам — {drifted[:10]}"
            )

        products = Product.objects.in_bulk(write_ids)
        touched: list[Product] = []
        for entry in applicable:
            pid = entry["product_id"]
            product = products[pid]
            target_slug = entry["to_option_slug"]
            pav = ProductAttributeValue.objects.filter(product_id=pid, attribute=attribute).first()
            if target_slug is None:
                if pav is not None:
                    pav.delete()
            else:
                option = option_by_slug.get(target_slug)
                if option is None:
                    raise RollbackError(f"option {target_slug!r} исчез между планом и применением")
                if pav is None:
                    ProductAttributeValue.objects.create(
                        product=product, attribute=attribute, value_option=option
                    )
                else:
                    pav.value_option = option
                    pav.save(update_fields=["value_option"])
            cache = dict(product.attrs_cache or {})
            target_cache = entry["to_attrs_cache_tool_type"]
            if target_cache is None:
                cache.pop(CACHE_KEY, None)
            else:
                cache[CACHE_KEY] = target_cache
            product.attrs_cache = cache
            touched.append(product)
        flush_attrs_cache_merged(touched, lambda p: {CACHE_KEY})
    return {"written": len(applicable), "noop": counts[DECISION_NOOP] + settled}


# --- post-audit ---


def verify_post_state(target_doc: dict) -> dict:
    """Пересобрать снимок по тем же товарам и сверить с целевым (post-audit)."""
    validate_snapshot(target_doc, label="target")
    expected = {r["product_id"]: r for r in target_doc["canonical"]["rows"]}
    actual = {r["product_id"]: r for r in _rows_for(sorted(expected))}
    diffs: list[str] = []
    for pid in sorted(expected):
        want, got = expected[pid], actual.get(pid)
        if got is None:
            diffs.append(f"product {pid}: товар отсутствует в live")
            continue
        for field in ("option_slug", "option_value", "attrs_cache_tool_type"):
            if want[field] != got[field]:
                diffs.append(
                    f"product {pid}.{field}: ожидалось {want[field]!r}, live {got[field]!r}"
                )
    return {"passed": not diffs, "diffs": diffs, "rows_checked": len(expected)}
