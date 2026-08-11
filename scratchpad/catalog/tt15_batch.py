"""TT-15 · перенос товаров в новые типы на staging (3 кластера, гейт-цикл).

Запуск на стенде (внутри контейнера web), через env:

    TT15_STEP=baseline   TT15_MODE=dryrun  — глобальный отпечаток ДО (инварианты)
    TT15_STEP=cluster1   TT15_MODE=dryrun  — preflight/dry-run кластера 1
    TT15_STEP=cluster1   TT15_MODE=apply   — write кластера 1 + post-audit + откат
    ... cluster2, cluster3 аналогично (перед каждым apply — backup.sh на хосте)
    TT15_STEP=invariants TT15_MODE=dryrun  — сверка инвариантов ПОСЛЕ с ДО

    python manage.py shell -c "exec(open('/app/var/tt15_batch.py', encoding='utf-8').read())"

Артефакты: /app/var/tt15/ (var — bind volume хоста).
Дамп БД снимается штатным scripts/backup.sh на хосте перед каждым apply —
внутри контейнера pg_dump нет (как в TT-12).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

from django.db import transaction
from django.db.models import Count, Q

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    CatalogChange,
    Product,
    ProductAttributeValue,
)
from apps.catalog.read_models import build_attrs_cache
from apps.catalog.tool_type_rollback import (
    apply_rollback,
    build_snapshot,
    live_taxonomy_identity,
    plan_rollback,
    snapshot_bytes,
)

# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------
STEP = os.environ.get("TT15_STEP", "baseline")
MODE = os.environ.get("TT15_MODE", "dryrun")

ART = Path("/app/var/tt15")
GLOBAL_FP = ART / "global-fp.json"

TOOL_TYPE = "tool_type"
UNTOUCHABLE_FIELDS = [
    "code_1c",
    "article",
    "name",
    "category_id",
    "price",
    "stock_quantity",
    "status",
    "is_active",
]

CLUSTER2_IDS = [35608] + list(range(39279, 39293))  # 15 настоящих воронок
CLUSTER3_IDS = list(range(23743, 23750))  # 7 нагрузочных вилок

CLUSTERS = {
    "cluster1": {
        "target": "bp-golovki-trimmernye",
        "ids_file": ART / "cluster1-ids.json",  # 108 id из recon (критерий ± решения)
        "expected_from": {"prochaya-osnastka": 94, "krep-gaiki": 6, "krep-bolty": 4, None: 4},
        "must_include": [26232],
        "must_exclude": {38680: None, 1899: "bp-trimmery"},
        "watch": {38680: None, 1899: "bp-trimmery"},
    },
    "cluster2": {
        "target": "hoz-voronki",
        "ids": CLUSTER2_IDS,
        "expected_from": {None: 14, "obor-smazka": 1},
        "must_include": [39290, 35608],
        "must_exclude": {},
        "watch": {11: None, 40109: None, 40354: None, 38368: None,
                  11056: "svar-sopla", 6170: None},
    },
    "cluster3": {
        "target": "izm-multimetry",
        "ids": CLUSTER3_IDS,
        "expected_from": {"avtomaty-predohraniteli": 7},
        "must_include": [],
        "must_exclude": {18: "izm-multimetry"},
        "watch": {18: "izm-multimetry"},
    },
}

ALL_AFFECTED_SLUGS = sorted({
    "bp-golovki-trimmernye", "hoz-voronki", "izm-multimetry",
    "prochaya-osnastka", "krep-gaiki", "krep-bolty",
    "obor-smazka", "avtomaty-predohraniteli", "bp-trimmery", "svar-sopla",
})


def log(msg: str) -> None:
    print(f"[TT-15] {msg}")


def cluster_ids(cfg: dict) -> list[int]:
    if "ids" in cfg:
        return sorted(cfg["ids"])
    return sorted(json.loads(cfg["ids_file"].read_text(encoding="utf-8")))


def all_scope_and_watch() -> list[int]:
    ids: set[int] = set()
    for cfg in CLUSTERS.values():
        ids.update(cluster_ids(cfg))
        ids.update(cfg["watch"])
    return sorted(ids)


def type_map(pids: list[int]) -> dict[int, tuple[str | None, str | None]]:
    """pid -> (option_slug | None, source | None); (None, None) = нет PAV-строки."""
    rows = ProductAttributeValue.objects.filter(
        attribute__slug=TOOL_TYPE, product_id__in=pids
    ).values("product_id", "value_option__slug", "source")
    m = {r["product_id"]: (r["value_option__slug"], r["source"]) for r in rows}
    return {pid: m.get(pid, (None, None)) for pid in pids}


def type_counts(slugs: list[str]) -> dict[str, int]:
    qs = (
        ProductAttributeValue.objects.filter(
            attribute__slug=TOOL_TYPE, value_option__slug__in=slugs
        )
        .values("value_option__slug")
        .annotate(cnt=Count("product_id"))
    )
    return {row["value_option__slug"]: row["cnt"] for row in qs}


def untouchable_hash(pids: list[int]) -> str:
    rows = Product.objects.filter(id__in=pids).order_by("id").values(*UNTOUCHABLE_FIELDS)
    payload = json.dumps(list(rows), ensure_ascii=True, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def dup_recount() -> dict:
    """Пересчёт одноимённых видимых карточек (методика CAT-11/CAT-12)."""
    groups: dict[str, list[dict]] = defaultdict(list)
    qs = Product.objects.filter(is_active=True, status="published").values("id", "name", "article")
    for row in qs.iterator():
        groups[_norm(row["name"])].append(row)
    dups = {k: v for k, v in groups.items() if len(v) >= 2 and k}
    classes = Counter()
    n_cards = 0
    for rows in dups.values():
        n_cards += len(rows)
        arts = [(r["article"] or "").strip() for r in rows]
        nonempty = [a for a in arts if a]
        if not nonempty:
            cls = "empty_all"
        elif len(nonempty) < len(arts):
            cls = "empty_partial"
        elif len(set(nonempty)) == 1:
            cls = "same_article"
        else:
            cls = "different_articles"
        classes[cls] += 1
    return {"groups": len(dups), "cards": n_cards, "classes": dict(classes)}


def global_fp() -> dict:
    """Глобальный отпечаток: инварианты + счётчики + неприкасаемые поля scope."""
    yaya = Product.objects.filter(original_name__istartswith="яя").aggregate(
        total=Count("id"), active=Count("id", filter=Q(is_active=True))
    )
    suffix = (
        Product.objects.filter(is_active=True, status="published")
        .filter(Q(name__contains=" (арт. ") | Q(name__contains=" (код 1С "))
        .count()
    )
    findings = {
        str(r["item__run_id"]): r["n"]
        for r in CatalogChange.objects.values("item__run_id").annotate(n=Count("id"))
    }
    findings_status = {
        r["status"]: r["n"] for r in CatalogChange.objects.values("status").annotate(n=Count("id"))
    }
    return {
        "pav_total": ProductAttributeValue.objects.filter(attribute__slug=TOOL_TYPE).count(),
        "taxonomy_identity": live_taxonomy_identity(),
        "affected_counts": type_counts(ALL_AFFECTED_SLUGS),
        "yaya": {"total": yaya["total"], "active": yaya["active"]},
        "suffix266": suffix,
        "dup": dup_recount(),
        "findings_by_run": findings,
        "findings_by_status": findings_status,
        "untouchable_all": untouchable_hash(all_scope_and_watch()),
    }


def fp_diff(before: dict, after: dict) -> list[str]:
    diffs = []
    for key in before:
        if before[key] != after.get(key):
            diffs.append(f"{key}: {before[key]!r} -> {after.get(key)!r}")
    return diffs


# ---------------------------------------------------------------------------
# Preflight / dry-run
# ---------------------------------------------------------------------------
def preflight(cfg: dict) -> dict:
    ids = cluster_ids(cfg)
    log(f"=== PREFLIGHT {STEP} (mode={MODE}) ===")

    for pid in cfg["must_include"]:
        if pid not in ids:
            raise ValueError(f"pid={pid} обязан быть в периметре, но его нет")
    for pid in cfg["must_exclude"]:
        if pid in ids:
            raise ValueError(f"pid={pid} обязан быть ИСКЛЮЧЁН, но он в периметре")

    products = set(Product.objects.filter(id__in=ids).values_list("id", flat=True))
    missing = [pid for pid in ids if pid not in products]
    if missing:
        raise ValueError(f"товары не найдены: {missing}")

    tm = type_map(ids + sorted(cfg["watch"]))
    live_from = Counter(tm[pid][0] for pid in ids)
    expected_from = Counter(cfg["expected_from"])
    if live_from != expected_from:
        raise ValueError(f"исходные типы не сошлись: live={dict(live_from)} expected={dict(expected_from)}")

    bad_source = [
        f"{pid}: src={tm[pid][1]!r}"
        for pid in ids
        if tm[pid][1] is not None and tm[pid][1] != "manual"
    ]
    if bad_source:
        raise ValueError("source != manual: " + "; ".join(bad_source))

    # watch-товары: тип должен совпасть с ожидаемым и не меняться
    for pid, want in cfg["watch"].items():
        got = tm[pid][0]
        if got != want:
            raise ValueError(f"watch pid={pid}: ожидался тип {want!r}, live {got!r}")

    attribute = Attribute.objects.get(slug=TOOL_TYPE)
    target_opt = AttributeOption.objects.filter(attribute=attribute, slug=cfg["target"]).first()
    if target_opt is None:
        raise ValueError(f"целевая опция {cfg['target']!r} отсутствует")

    before_counts = type_counts(ALL_AFFECTED_SLUGS)
    delta = Counter()
    for pid in ids:
        delta[tm[pid][0]] -= 1
        delta[cfg["target"]] += 1
    predicted = {
        s: before_counts.get(s, 0) + delta[s]
        for s in ALL_AFFECTED_SLUGS
        if before_counts.get(s, 0) + delta[s] != before_counts.get(s, 0)
    }
    creates = sum(1 for pid in ids if tm[pid][0] is None)
    log(f"scope={len(ids)}, creates(нет PAV)={creates}")
    log(f"counts before (затронутые): { {s: before_counts.get(s, 0) for s in predicted} }")
    log(f"counts predicted after:     {predicted}")

    scope_hash = untouchable_hash(ids + sorted(cfg["watch"]))
    log(f"untouchable_hash(scope+watch)={scope_hash}")

    return {
        "ids": ids,
        "attribute": attribute,
        "target_opt": target_opt,
        "before_counts": before_counts,
        "predicted": predicted,
        "scope_hash": scope_hash,
        "tm": tm,
        "creates": creates,
    }


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------
def apply_cluster(cfg: dict, info: dict) -> None:
    ids = info["ids"]
    attribute = info["attribute"]
    target = info["target_opt"]
    tm = info["tm"]

    with transaction.atomic():
        list(Product.objects.select_for_update().filter(id__in=ids).order_by("id"))
        pavs = {
            pav.product_id: pav
            for pav in ProductAttributeValue.objects.select_for_update()
            .filter(attribute=attribute, product_id__in=ids)
            .order_by("product_id")
        }
        for pav in pavs.values():
            pav.value_option  # кэш для FP-guard

        # FP-guard внутри транзакции: live == ожидаемому из preflight
        drifted = []
        for pid in ids:
            pav = pavs.get(pid)
            live_slug = pav.value_option.slug if pav and pav.value_option_id else None
            if live_slug != tm[pid][0]:
                drifted.append(f"{pid}: expected {tm[pid][0]!r}, live {live_slug!r}")
        if drifted:
            raise ValueError("FP-guard FAILED:\n" + "\n".join(drifted))

        touched = []
        for pid in ids:
            pav = pavs.get(pid)
            if pav is None:
                # source=manual — default модели
                pav = ProductAttributeValue(
                    product_id=pid, attribute=attribute, value_option=target
                )
                pav.save()
            else:
                pav.value_option = target
                pav.save(update_fields=["value_option"])
            touched.append(pav)
        log(f"PAV записано: {len(touched)} (creates={info['creates']})")

        products = list(
            Product.objects.select_for_update()
            .filter(id__in=ids)
            .prefetch_related("attribute_values__attribute", "attribute_values__value_option")
            .order_by("id")
        )
        for product in products:
            product.attrs_cache = build_attrs_cache(product)
        Product.objects.bulk_update(products, ["attrs_cache"])
        log(f"attrs_cache пересобран: {len(products)}")


# ---------------------------------------------------------------------------
# Post-audit
# ---------------------------------------------------------------------------
def post_audit(cfg: dict, info: dict) -> None:
    ids = info["ids"]
    log(f"=== POST-AUDIT {STEP} ===")
    after_counts = type_counts(ALL_AFFECTED_SLUGS)
    mismatches = []
    for slug, want in info["predicted"].items():
        got = after_counts.get(slug, 0)
        if got != want:
            mismatches.append(f"{slug}: predicted {want}, actual {got}")
    if mismatches:
        raise ValueError("POST-AUDIT counts FAILED:\n" + "\n".join(mismatches))
    log(f"counts after: { {s: after_counts.get(s, 0) for s in info['predicted']} } — сошлись")

    after_hash = untouchable_hash(ids + sorted(cfg["watch"]))
    if after_hash != info["scope_hash"]:
        raise ValueError("POST-AUDIT untouchable_hash changed!")
    log(f"untouchable_hash идентичен: {after_hash}")

    # watch не тронут
    tmw = type_map(sorted(cfg["watch"]))
    for pid, want in cfg["watch"].items():
        if tmw[pid][0] != want:
            raise ValueError(f"watch pid={pid} изменился: {tmw[pid][0]!r} != {want!r}")

    # attrs_cache ≡ EAV
    pavs = {
        r["product_id"]: r["value_option__value"]
        for r in ProductAttributeValue.objects.filter(
            attribute__slug=TOOL_TYPE, product_id__in=ids
        ).values("product_id", "value_option__value")
    }
    diffs = []
    for product in Product.objects.filter(id__in=ids).only("id", "attrs_cache"):
        cache_val = (product.attrs_cache or {}).get(TOOL_TYPE)
        eav_val = pavs.get(product.id)
        if cache_val != eav_val:
            diffs.append(f"pid={product.id}: cache={cache_val!r}, EAV={eav_val!r}")
    if diffs:
        raise ValueError("attrs_cache != EAV:\n" + "\n".join(diffs))

    dupes = list(
        ProductAttributeValue.objects.filter(attribute__slug=TOOL_TYPE, product_id__in=ids)
        .values("product_id").annotate(cnt=Count("id")).filter(cnt__gt=1)
    )
    if dupes:
        raise ValueError(f"duplicate PAV: {dupes}")
    log("POST-AUDIT PASS")


# ---------------------------------------------------------------------------
# Снимки, карта отката, испытание отката
# ---------------------------------------------------------------------------
def take_snapshot(path: Path, ids: list[int]) -> None:
    doc = build_snapshot(product_ids=ids)
    path.write_bytes(snapshot_bytes(doc))
    log(f"snapshot rows={doc['canonical']['rows_count']} -> {path}")


def save_rollback_map(cfg: dict, info: dict, before_path: Path) -> None:
    ids = info["ids"]
    before_doc = json.loads(before_path.read_text(encoding="utf-8"))
    before_rows = {r["product_id"]: r for r in before_doc["canonical"]["rows"]}
    option_by_slug = {o.slug: o for o in info["attribute"].options.all()}
    mapping = {}
    for pid in ids:
        old_slug = before_rows[pid]["option_slug"]
        mapping[str(pid)] = {
            "old_option_id": option_by_slug[old_slug].id if old_slug else None,
            "old_slug": old_slug,
            "new_option_id": option_by_slug[cfg["target"]].id,
            "new_slug": cfg["target"],
        }
    path = ART / f"{STEP}-rollback-map.json"
    path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"rollback-map -> {path}")


def test_rollback(ids: list[int], before_path: Path, after_path: Path) -> None:
    log("=== ROLLBACK TEST ===")
    after_doc = json.loads(after_path.read_text(encoding="utf-8"))
    before_doc = json.loads(before_path.read_text(encoding="utf-8"))

    plan = plan_rollback(after_doc, before_doc)
    log(f"rollback plan: {plan.counts}")
    if not plan.feasible:
        raise ValueError(f"rollback plan not feasible: {plan.conflicts[:5]}")
    stats = apply_rollback(plan)
    log(f"rollback applied: {stats}")

    plan_fwd = plan_rollback(before_doc, after_doc)
    log(f"forward plan: {plan_fwd.counts}")
    if not plan_fwd.feasible:
        raise ValueError(f"forward plan not feasible: {plan_fwd.conflicts[:5]}")
    stats_fwd = apply_rollback(plan_fwd)
    log(f"forward applied: {stats_fwd}")

    verify_doc = build_snapshot(product_ids=ids)
    if verify_doc["canonical"]["rows"] != after_doc["canonical"]["rows"]:
        raise ValueError("ROLLBACK TEST FAILED: state after forward != planned after")
    log("ROLLBACK TEST PASS")


# ---------------------------------------------------------------------------
# Шаги
# ---------------------------------------------------------------------------
def step_baseline() -> None:
    ART.mkdir(parents=True, exist_ok=True)
    fp = global_fp()
    GLOBAL_FP.write_text(json.dumps(fp, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (ART / "invariants-before.json").write_text(
        json.dumps(fp, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    log(f"baseline fp -> {GLOBAL_FP} (+ invariants-before.json)")
    log(json.dumps(fp, ensure_ascii=False, default=str))


def step_cluster(cfg: dict) -> None:
    ART.mkdir(parents=True, exist_ok=True)
    # Контроль параллельной записи: live fp обязан совпасть с сохранённым
    if GLOBAL_FP.exists():
        stored = json.loads(GLOBAL_FP.read_text(encoding="utf-8"))
        live = global_fp()
        diffs = fp_diff(stored, live)
        if diffs:
            raise ValueError(
                "ГЛОБАЛЬНЫЙ ОТПЕЧАТОК СДВИНУЛСЯ не от нашей записи — стоп:\n" + "\n".join(diffs)
            )
        log("global fp: совпал с сохранённым (чужой записи нет)")

    info = preflight(cfg)
    if MODE != "apply":
        log(f"DRY-RUN {STEP} OK (запись не выполнялась)")
        return

    before_path = ART / f"{STEP}-before.json"
    after_path = ART / f"{STEP}-after.json"
    take_snapshot(before_path, info["ids"])

    log("=== APPLY ===")
    apply_cluster(cfg, info)

    take_snapshot(after_path, info["ids"])
    save_rollback_map(cfg, info, before_path)
    post_audit(cfg, info)
    test_rollback(info["ids"], before_path, after_path)

    # После rollback-теста состояние == after; обновляем глобальный отпечаток
    fp = global_fp()
    GLOBAL_FP.write_text(json.dumps(fp, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    log(f"global fp обновлён -> {GLOBAL_FP}")
    log(f"=== {STEP} COMPLETE ===")


def step_invariants() -> None:
    baseline_path = ART / "invariants-before.json"
    live = global_fp()
    if not baseline_path.exists():
        baseline_path.write_text(
            json.dumps(live, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        log(f"invariants-before -> {baseline_path} (первый запуск)")
        return
    before = json.loads(baseline_path.read_text(encoding="utf-8"))
    log("=== INVARIANTS DIFF (before -> after) ===")
    for key in before:
        b, a = before[key], live.get(key)
        mark = "OK " if b == a else "CHG"
        log(f"{mark} {key}: {json.dumps(b, ensure_ascii=False, default=str)} -> {json.dumps(a, ensure_ascii=False, default=str)}")
    (ART / "invariants-after.json").write_text(
        json.dumps(live, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


def main() -> None:
    if STEP == "baseline":
        step_baseline()
    elif STEP == "invariants":
        step_invariants()
    elif STEP in CLUSTERS:
        step_cluster(CLUSTERS[STEP])
    else:
        raise ValueError(f"unknown TT15_STEP={STEP!r}")


main()
