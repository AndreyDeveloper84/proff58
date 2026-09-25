"""Reverse-map манифеста taxonomy: переход ``manifest_version N → N-1`` (Wave 7.1 / H5).

Форвардный путь эволюции словаря — манифест плюс fail-closed seed
(``load_tool_types``: создаёт недостающее, ничего не удаляет). Обратного пути
не существовало: если опция исчезает из манифеста, товары с этой опцией
остаются висеть на записи, которой в словаре больше нет.

Модуль строит **план понижения версии** — read-only документ, отвечающий на
три вопроса по каждому slug:

- ``keep``        — опция есть в обоих манифестах с тем же value, ничего не делаем;
- ``reappearing`` — опция есть только в целевом (N-1): вернётся штатным seed'ом;
- ``drop``        — опция исчезает и товаров на ней нет: удаляется;
- ``remap``       — опция исчезает, товары есть, владелец задал явную цель переноса;
- ``blocked``     — однозначного отката нет.

**Fail-closed.** План неисполним (``feasible=False``), если хотя бы одна
исчезающая опция несёт товары без явного remap, если live-словарь не приведён к
манифесту N, или если понижение требует смены ``value`` существующей опции —
такого инструмента в контуре нет (seed на конфликте value падает, а не чинит).

Почему remap только явный: без ``option_uid``
(``future_evolution.immutable_option_identity``) переименование slug неотличимо
от «удалили одну опцию, добавили другую». Автоматически угадывать цель переноса
означало бы молча переклеить товары — ровно то, чего волна не допускает.

Перенос товаров исполняет ``tool_type_rollback`` (пара снимков + conflict-guard),
поэтому у понижения версии та же семантика идемпотентности и конфликта, что у
отката применённых предложений. Порядок операций жёсткий:

1. ``build_downgrade_plan`` (read-only) → план;
2. ``snapshot_pair_for_remap`` + ``apply_rollback`` → перенос товаров;
3. ``drop_disappearing_options`` → удаление освободившихся опций;
4. ``load_tool_types --manifest <N-1>`` → возврат ``reappearing`` опций.

Модуль не создаёт опции ``tool_type`` (инвариант manifest-only) и не трогает
semantics матчера.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from django.db import transaction
from django.db.models import Count

from apps.catalog.models import AttributeOption, ProductAttributeValue
from apps.catalog.rules_release import canonical_bytes, canonical_hash_of
from apps.catalog.taxonomy_manifest import TaxonomyManifest, load_manifest
from apps.catalog.tool_type_rollback import (
    TOOL_TYPE_SLUG,
    build_snapshot,
    live_taxonomy_identity,
)

REVERSE_SCHEMA_VERSION = 1

KEEP = "keep"
DROP = "drop"
REMAP = "remap"
REAPPEARING = "reappearing"
BLOCKED = "blocked"


class ReverseMigrationError(ValueError):
    """Структурно невозможное понижение версии или отказ применять план."""


def _as_manifest(value: TaxonomyManifest | Path | str) -> TaxonomyManifest:
    return value if isinstance(value, TaxonomyManifest) else load_manifest(Path(value))


def diff_manifests(from_manifest, to_manifest) -> dict:
    """Классификация slug'ов при переходе ``from`` (N) → ``to`` (N-1)."""
    src = {o.slug: o.value for o in _as_manifest(from_manifest).options}
    dst = {o.slug: o.value for o in _as_manifest(to_manifest).options}
    common = set(src) & set(dst)
    return {
        "unchanged": sorted(s for s in common if src[s] == dst[s]),
        "value_changed": sorted(s for s in common if src[s] != dst[s]),
        "disappearing": sorted(set(src) - set(dst)),
        "reappearing": sorted(set(dst) - set(src)),
    }


@dataclass(frozen=True)
class DowngradePlan:
    """Read-only решение по каждому slug + канонический документ плана."""

    entries: tuple[dict, ...]
    blocking: tuple[dict, ...]
    summary: dict
    document: dict
    from_manifest: TaxonomyManifest
    to_manifest: TaxonomyManifest

    @property
    def feasible(self) -> bool:
        return not self.blocking

    def entries_by_disposition(self, disposition: str) -> list[dict]:
        return [e for e in self.entries if e["disposition"] == disposition]


def _pav_counts(slugs: list[str]) -> dict[str, int]:
    if not slugs:
        return {}
    rows = (
        ProductAttributeValue.objects.filter(
            attribute__slug=TOOL_TYPE_SLUG, value_option__slug__in=slugs
        )
        .values("value_option__slug")
        .annotate(n=Count("id"))
    )
    return {row["value_option__slug"]: row["n"] for row in rows}


def build_downgrade_plan(
    *,
    from_manifest,
    to_manifest,
    remap: dict[str, str] | None = None,
) -> DowngradePlan:
    """Построить план понижения версии. В БД ничего не пишет."""
    src = _as_manifest(from_manifest)
    dst = _as_manifest(to_manifest)
    if src.attribute_slug != dst.attribute_slug:
        raise ReverseMigrationError(
            f"манифесты по разным атрибутам: {src.attribute_slug!r} vs {dst.attribute_slug!r}"
        )
    if dst.manifest_version != src.manifest_version - 1:
        raise ReverseMigrationError(
            "поддерживается только смежное понижение N → N-1: "
            f"from v{src.manifest_version}, to v{dst.manifest_version}"
        )

    diff = diff_manifests(src, dst)
    remap = dict(remap or {})
    stray = sorted(set(remap) - set(diff["disappearing"]))
    if stray:
        raise ReverseMigrationError(
            f"remap задан для slug, который не исчезает при понижении: {stray}"
        )

    src_values = {o.slug: o.value for o in src.options}
    dst_values = {o.slug: o.value for o in dst.options}
    live_slugs = set(
        AttributeOption.objects.filter(attribute__slug=TOOL_TYPE_SLUG).values_list(
            "slug", flat=True
        )
    )
    counts = _pav_counts(diff["disappearing"])

    entries: list[dict] = []
    blocking: list[dict] = []

    identity = live_taxonomy_identity()
    if identity != src.identity_hash:
        blocking.append(
            {
                "code": "live_not_at_from_manifest",
                "slug": "",
                "detail": (
                    f"live taxonomy_identity={identity} != манифест N {src.identity_hash}; "
                    "приведите живой словарь к N до понижения"
                ),
            }
        )

    for slug in diff["unchanged"]:
        entries.append(_entry(slug, KEEP, src_values[slug], dst_values[slug], reason="unchanged"))

    for slug in diff["value_changed"]:
        entries.append(
            _entry(
                slug,
                BLOCKED,
                src_values[slug],
                dst_values[slug],
                reason="value_change_requires_manual",
            )
        )
        blocking.append(
            {
                "code": "value_change_requires_manual",
                "slug": slug,
                "detail": (
                    f"понижение требует смены value {src_values[slug]!r} → {dst_values[slug]!r}; "
                    "seed такого не делает — решение владельца"
                ),
            }
        )

    for slug in diff["reappearing"]:
        entries.append(
            _entry(slug, REAPPEARING, None, dst_values[slug], reason="seed_will_recreate")
        )

    affected = 0
    for slug in diff["disappearing"]:
        pav_count = counts.get(slug, 0)
        target = remap.get(slug)
        if target is None:
            if pav_count == 0:
                entries.append(
                    _entry(slug, DROP, src_values[slug], None, pav_count=0, reason="unused")
                )
                continue
            entries.append(
                _entry(
                    slug,
                    BLOCKED,
                    src_values[slug],
                    None,
                    pav_count=pav_count,
                    reason="orphaned_products",
                )
            )
            blocking.append(
                {
                    "code": "orphaned_products",
                    "slug": slug,
                    "detail": (
                        f"{pav_count} товаров останутся с исчезнувшей опцией; "
                        "нужен явный remap или решение владельца"
                    ),
                }
            )
            continue

        code = _remap_violation(target, dst_values, live_slugs, diff["disappearing"])
        if code is not None:
            entries.append(
                _entry(
                    slug,
                    BLOCKED,
                    src_values[slug],
                    None,
                    pav_count=pav_count,
                    remap_to=target,
                    reason=code,
                )
            )
            blocking.append(
                {"code": code, "slug": slug, "detail": f"remap {slug} → {target}: {code}"}
            )
            continue
        affected += pav_count
        entries.append(
            _entry(
                slug,
                REMAP,
                src_values[slug],
                None,
                pav_count=pav_count,
                remap_to=target,
                reason="explicit_remap",
            )
        )

    entries.sort(key=lambda e: e["slug"])
    summary = {
        disposition: len([e for e in entries if e["disposition"] == disposition])
        for disposition in (KEEP, REAPPEARING, DROP, REMAP, BLOCKED)
    }
    summary["affected_products"] = affected
    canonical = {
        "schema_version": REVERSE_SCHEMA_VERSION,
        "attribute_slug": src.attribute_slug,
        "from": _manifest_ref(src),
        "to": _manifest_ref(dst),
        "entries": entries,
        "summary": summary,
        "feasible": not blocking,
        "blocking": blocking,
    }
    return DowngradePlan(
        entries=tuple(entries),
        blocking=tuple(blocking),
        summary=summary,
        document={"canonical": canonical, "canonical_hash": canonical_hash_of(canonical)},
        from_manifest=src,
        to_manifest=dst,
    )


def _entry(slug, disposition, from_value, to_value, *, pav_count=0, remap_to=None, reason=""):
    return {
        "slug": slug,
        "disposition": disposition,
        "from_value": from_value,
        "to_value": to_value,
        "pav_count": pav_count,
        "remap_to": remap_to,
        "reason": reason,
    }


def _remap_violation(target, dst_values, live_slugs, disappearing) -> str | None:
    # «цель сама исчезает» — частный случай «нет в N-1», но диагноз точнее, поэтому первым
    if target in disappearing:
        return "remap_target_disappearing"
    if target not in dst_values:
        return "remap_target_unknown"
    if target not in live_slugs:
        return "remap_target_not_live"
    return None


def _manifest_ref(manifest: TaxonomyManifest) -> dict:
    return {
        "manifest_version": manifest.manifest_version,
        "options": len(manifest.options),
        "taxonomy_identity_hash": manifest.identity_hash,
        "manifest_semantic_hash": manifest.semantic_hash,
    }


def plan_bytes(document: dict) -> bytes:
    """Канонические байты плана (byte-stable между прогонами)."""
    return canonical_bytes(document)


# --- перенос товаров: пара снимков для исполнителя отката ---


def snapshot_pair_for_remap(plan: DowngradePlan) -> tuple[dict, dict]:
    """Пара снимков ``(from, to)`` для ``tool_type_rollback`` по remap-записям.

    ``from`` — текущее состояние товаров на исчезающих опциях, ``to`` — то же
    множество товаров, переклеенное на целевые опции. Конфликт-гард и
    идемпотентность обеспечивает исполнитель отката.
    """
    if not plan.feasible:
        raise ReverseMigrationError(
            "план не feasible: " + "; ".join(f"{b['code']}:{b['slug']}" for b in plan.blocking[:5])
        )
    remaps = {e["slug"]: e["remap_to"] for e in plan.entries_by_disposition(REMAP)}
    if not remaps:
        raise ReverseMigrationError("в плане нет remap-записей — пара снимков не нужна")

    from_doc = build_snapshot(option_slugs=sorted(remaps))
    target_values = {
        o.slug: o.value
        for o in AttributeOption.objects.filter(
            attribute__slug=TOOL_TYPE_SLUG, slug__in=sorted(set(remaps.values()))
        )
    }
    missing = sorted(set(remaps.values()) - set(target_values))
    if missing:
        raise ReverseMigrationError(f"целевых опций нет в live-словаре: {missing}")

    rows = []
    for row in from_doc["canonical"]["rows"]:
        target_slug = remaps[row["option_slug"]]
        rows.append(
            {
                "product_id": row["product_id"],
                "option_slug": target_slug,
                "option_value": target_values[target_slug],
                "attrs_cache_tool_type": target_values[target_slug],
            }
        )
    canonical = {**from_doc["canonical"], "rows": rows, "rows_count": len(rows)}
    to_doc = {"canonical": canonical, "canonical_hash": canonical_hash_of(canonical)}
    return from_doc, to_doc


# --- удаление освободившихся опций ---


def drop_disappearing_options(plan: DowngradePlan, *, apply: bool = False) -> dict:
    """Удалить опции, исчезающие при понижении версии. Fail-closed по usage.

    Удаляются только опции, которых нет в манифесте N-1 и на которых **в момент
    выполнения** нет ни одного товара. Любая исчезающая опция с товарами
    (например, remap ещё не исполнен) отменяет операцию целиком.
    """
    if not plan.feasible:
        raise ReverseMigrationError(
            "план не feasible — удаление опций запрещено: "
            + "; ".join(f"{b['code']}:{b['slug']}" for b in plan.blocking[:5])
        )
    slugs = sorted(e["slug"] for e in plan.entries if e["disposition"] in (DROP, REMAP))
    with transaction.atomic():
        live = {
            o.slug: o
            for o in AttributeOption.objects.select_for_update().filter(
                attribute__slug=TOOL_TYPE_SLUG, slug__in=slugs
            )
        }
        already_absent = [s for s in slugs if s not in live]
        present = [s for s in slugs if s in live]
        counts = _pav_counts(present)
        still_used = {s: counts[s] for s in present if counts.get(s)}
        if still_used:
            raise ReverseMigrationError(
                "исчезающие опции всё ещё несут товары (сначала перенос, потом удаление): "
                + ", ".join(f"{s}={n}" for s, n in sorted(still_used.items()))
            )
        if not apply:
            return {"would_drop": present, "dropped": [], "already_absent": already_absent}
        for slug in present:
            live[slug].delete()
    return {"would_drop": present, "dropped": present, "already_absent": already_absent}
