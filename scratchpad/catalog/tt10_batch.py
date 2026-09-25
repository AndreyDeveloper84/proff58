"""TT-10 · перенос 9 товаров в правильные tool_type.

Запуск:
    python manage.py shell -c "exec(open('scratchpad/catalog/tt10_batch.py', encoding='utf-8').read())"

Выход: артефакты в scratchpad/catalog/artifacts-tt10/, протокол — tt-10-report.md.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections import Counter
from pathlib import Path

from django.db import transaction
from django.db.models import Count
from django.core.management import call_command

from apps.catalog.models import Attribute, AttributeOption, Product, ProductAttributeValue
from apps.catalog.read_models import build_attrs_cache
from apps.catalog.tool_type_rollback import (
    build_snapshot,
    plan_rollback,
    apply_rollback,
    snapshot_bytes,
)

# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------
MOVES = [
    {"pid": 1109, "from": "akkumulyatory", "to": "adaptery"},
    {"pid": 24866, "from": "svar-provoloka", "to": "raskhodniki-pajki"},
    {"pid": 28886, "from": "krep-gvozdi", "to": "bp-pnevmosteplery"},
    {"pid": 28887, "from": "krep-gvozdi", "to": "bp-pnevmosteplery"},
    {"pid": 34643, "from": "lebedki-tali", "to": "sterzhni-kleevye"},
    {"pid": 34644, "from": "lebedki-tali", "to": "sterzhni-kleevye"},
    {"pid": 35057, "from": "lebedki-tali", "to": "passatizhi"},
    {"pid": 35058, "from": "lebedki-tali", "to": "passatizhi"},
    {"pid": 36379, "from": "svar-maski", "to": "siz-ochki"},
]

ARTIFACTS = Path("scratchpad/catalog/artifacts-tt10")
BEFORE_SNAPSHOT = ARTIFACTS / "before.json"
AFTER_SNAPSHOT = ARTIFACTS / "after.json"
ROLLBACK_MAP = ARTIFACTS / "rollback-map.json"
DUMP_FILE = ARTIFACTS / "db-tt10-before.sql.gz"

TOOL_TYPE_SLUG = "tool_type"
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

product_ids = sorted({m["pid"] for m in MOVES})


def log(msg: str) -> None:
    print(f"[TT-10] {msg}")


def ensure_artifacts_dir() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)


def type_counts(slugs: list[str]) -> dict[str, int]:
    """Текущие счётчики PAV по списку tool_type-slug."""
    qs = (
        ProductAttributeValue.objects.filter(
            attribute__slug=TOOL_TYPE_SLUG, value_option__slug__in=slugs
        )
        .values("value_option__slug")
        .annotate(cnt=Count("product_id"))
    )
    return {row["value_option__slug"]: row["cnt"] for row in qs}


def untouchable_hash(pids: list[int]) -> str:
    """SHA-256 от неприкасаемых полей по заданным товарам (стабильный порядок)."""
    rows = (
        Product.objects.filter(id__in=pids)
        .order_by("id")
        .values(*UNTOUCHABLE_FIELDS)
    )
    payload = json.dumps(list(rows), ensure_ascii=True, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def take_snapshot(path: Path, pids: list[int]) -> None:
    doc = build_snapshot(product_ids=pids)
    path.write_bytes(snapshot_bytes(doc))
    log(f"snapshot rows={doc['canonical']['rows_count']} -> {path}")


def run_pg_dump() -> None:
    """Свежий pg_dump перед write (политика docs/catalog/operations/pgdump-policy.md).

    Если pg_dump недоступен в PATH (например, локальная Windows-машина без
    установленного клиента PostgreSQL), записываем предупреждение и продолжаем:
    снапшот + rollback-map остаются основными точками отката.
    """
    db_url = os.environ.get("DATABASE_URL", "postgres://proff:proff@localhost:5432/proff58")
    # Поддерживаем postgres:// и postgresql://
    db_url = db_url.replace("postgresql://", "postgres://")
    rest = db_url.replace("postgres://", "")
    creds_host, dbname = rest.split("/", 1)
    creds, host_port = creds_host.split("@")
    user, password = creds.split(":")
    host, port = (host_port.split(":") + ["5432"])[:2]

    env = os.environ.copy()
    env["PGPASSWORD"] = password
    cmd = [
        "pg_dump",
        "-h", host,
        "-p", str(port),
        "-U", user,
        "-d", dbname,
    ]
    log(f"pg_dump -> {DUMP_FILE}")
    try:
        with DUMP_FILE.open("wb") as fh:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            import gzip  # noqa: E402
            with gzip.GzipFile(fileobj=fh, mode="wb") as gz:
                for chunk in iter(proc.stdout.readline, b""):
                    if not chunk:
                        break
                    gz.write(chunk)
            stderr = proc.communicate()[1]
            if proc.returncode != 0:
                raise RuntimeError(f"pg_dump failed: {stderr.decode('utf-8', errors='replace')}")
        log(f"pg_dump OK size={DUMP_FILE.stat().st_size}")
    except FileNotFoundError:
        log("WARNING: pg_dump не найден в PATH; дамп не создан (локальное ограничение)")
        DUMP_FILE.write_text(
            "# pg_dump не выполнен: утилита не найдена в PATH\n", encoding="utf-8"
        )


def preflight() -> dict:
    """Проверка готовности + предсказание."""
    ensure_artifacts_dir()
    log("=== PREFLIGHT ===")

    # 1. Продукты существуют и имеют ожидаемый исходный тип
    current = {
        row["product_id"]: row
        for row in ProductAttributeValue.objects.filter(
            attribute__slug=TOOL_TYPE_SLUG, product_id__in=product_ids
        )
        .select_related("value_option")
        .values("product_id", "value_option__slug", "source")
    }
    missing = [pid for pid in product_ids if pid not in current]
    if missing:
        raise ValueError(f"товары не найдены: {missing}")

    errors = []
    for m in MOVES:
        row = current[m["pid"]]
        if row["value_option__slug"] != m["from"]:
            errors.append(
                f"pid={m['pid']} ожидался {m['from']!r}, live {row['value_option__slug']!r}"
            )
        if row["source"] != "manual":
            errors.append(f"pid={m['pid']} source={row['source']!r} (ожидался manual)")
    if errors:
        raise ValueError("preflight failed:\n" + "\n".join(errors))

    # 2. Целевые опции существуют
    attribute = Attribute.objects.get(slug=TOOL_TYPE_SLUG)
    target_slugs = {m["to"] for m in MOVES}
    live_options = {
        o.slug: o for o in AttributeOption.objects.filter(attribute=attribute, slug__in=target_slugs)
    }
    unknown = target_slugs - set(live_options)
    if unknown:
        raise ValueError(f"целевые option slug отсутствуют: {sorted(unknown)}")

    # 3. Счётчики ДО
    all_slugs = sorted({m["from"] for m in MOVES} | target_slugs)
    before_counts = type_counts(all_slugs)
    log(f"counts before: {before_counts}")

    # 4. Предсказание ПОСЛЕ
    delta = Counter()
    for m in MOVES:
        delta[m["from"]] -= 1
        delta[m["to"]] += 1
    predicted = {slug: before_counts.get(slug, 0) + delta[slug] for slug in all_slugs}
    log(f"counts predicted after: {predicted}")

    # 5. Отпечаток неприкасаемых полей
    before_hash = untouchable_hash(product_ids)
    log(f"untouchable_hash before={before_hash}")

    return {
        "attribute": attribute,
        "live_options": live_options,
        "before_counts": before_counts,
        "predicted_counts": predicted,
        "before_hash": before_hash,
        "current_pavs": current,
    }


def save_rollback_map(option_by_slug: dict[str, AttributeOption]) -> None:
    """product_id -> {old_option_id, old_slug, new_option_id, new_slug}."""
    before_doc = json.loads(BEFORE_SNAPSHOT.read_text(encoding="utf-8"))
    before_rows = {r["product_id"]: r for r in before_doc["canonical"]["rows"]}
    mapping = {}
    for m in MOVES:
        pid = m["pid"]
        old_slug = before_rows[pid]["option_slug"]
        mapping[str(pid)] = {
            "old_option_id": option_by_slug[old_slug].id,
            "old_slug": old_slug,
            "new_option_id": option_by_slug[m["to"]].id,
            "new_slug": m["to"],
        }
    ROLLBACK_MAP.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"rollback-map -> {ROLLBACK_MAP}")


def apply_batch(attribute: Attribute, live_options: dict[str, AttributeOption]) -> None:
    """Один transaction.atomic: bulk_update PAV + точечная пересборка attrs_cache."""
    option_by_slug = {o.slug: o for o in attribute.options.all()}
    expected = {m["pid"]: m["from"] for m in MOVES}
    target = {m["pid"]: option_by_slug[m["to"]] for m in MOVES}

    with transaction.atomic():
        # Блокируем продукты и PAV
        list(Product.objects.select_for_update().filter(id__in=product_ids).order_by("id"))
        # Блокируем PAV без select_related: nullable FK + FOR UPDATE + outer join
        # не поддерживается PostgreSQL. Опции подгрузим отдельно.
        pavs = {
            pav.product_id: pav
            for pav in ProductAttributeValue.objects.select_for_update()
            .filter(attribute=attribute, product_id__in=product_ids)
            .order_by("product_id")
        }
        # Подгружаем value_option для FP-guard (9 строк — N+1 не критичен)
        for pav in pavs.values():
            pav.value_option  # кэширует объект

        # FP-guard: текущий option == ожидаемый из rollback-map
        drifted = []
        for pid in product_ids:
            pav = pavs.get(pid)
            live_slug = pav.value_option.slug if pav and pav.value_option_id else None
            if live_slug != expected[pid]:
                drifted.append(f"{pid}: expected {expected[pid]!r}, live {live_slug!r}")
        if drifted:
            raise ValueError("FP-guard FAILED:\n" + "\n".join(drifted))

        # Обновляем value_option
        touched_pavs = []
        for pid in product_ids:
            pav = pavs[pid]
            pav.value_option = target[pid]
            touched_pavs.append(pav)
        ProductAttributeValue.objects.bulk_update(touched_pavs, ["value_option"])
        log(f"bulk_update PAV: {len(touched_pavs)}")

        # Пересобираем attrs_cache по тому же множеству
        products = list(
            Product.objects.select_for_update()
            .filter(id__in=product_ids)
            .prefetch_related("attribute_values__attribute", "attribute_values__value_option")
            .order_by("id")
        )
        for product in products:
            product.attrs_cache = build_attrs_cache(product)
        Product.objects.bulk_update(products, ["attrs_cache"])
        log(f"bulk_update attrs_cache: {len(products)}")


def post_audit(predicted_counts: dict[str, int], before_hash: str) -> dict:
    """Проверка после записи."""
    log("=== POST-AUDIT ===")
    after_counts = type_counts(sorted(predicted_counts))
    log(f"counts after: {after_counts}")

    mismatches = []
    for slug, predicted in predicted_counts.items():
        actual = after_counts.get(slug, 0)
        if actual != predicted:
            mismatches.append(f"{slug}: predicted {predicted}, actual {actual}")
    if mismatches:
        raise ValueError("POST-AUDIT counts FAILED:\n" + "\n".join(mismatches))

    after_hash = untouchable_hash(product_ids)
    log(f"untouchable_hash after={after_hash}")
    if after_hash != before_hash:
        raise ValueError("POST-AUDIT untouchable_hash changed!")

    # attrs_cache ≡ EAV по девяти
    pavs = {
        row["product_id"]: row
        for row in ProductAttributeValue.objects.filter(
            attribute__slug=TOOL_TYPE_SLUG, product_id__in=product_ids
        )
        .select_related("value_option")
        .values("product_id", "value_option__value")
    }
    cache_diffs = []
    for product in Product.objects.filter(id__in=product_ids).only("id", "attrs_cache"):
        cache_val = (product.attrs_cache or {}).get(TOOL_TYPE_SLUG)
        eav_val = pavs.get(product.id, {}).get("value_option__value")
        if cache_val != eav_val:
            cache_diffs.append(
                f"pid={product.id}: attrs_cache={cache_val!r}, EAV={eav_val!r}"
            )
    if cache_diffs:
        raise ValueError("POST-AUDIT attrs_cache != EAV:\n" + "\n".join(cache_diffs))

    # Дублей PAV нет (unique_together product+attribute, но проверим явно)
    dupes = (
        ProductAttributeValue.objects.filter(attribute__slug=TOOL_TYPE_SLUG, product_id__in=product_ids)
        .values("product_id")
        .annotate(cnt=Count("id"))
        .filter(cnt__gt=1)
    )
    if list(dupes):
        raise ValueError(f"POST-AUDIT duplicate PAV found: {list(dupes)}")

    log("POST-AUDIT PASS")
    return {"after_counts": after_counts, "after_hash": after_hash}


def test_rollback() -> None:
    """Испытать откат и повторный forward по паре снимков."""
    log("=== ROLLBACK TEST ===")
    after_doc = json.loads(AFTER_SNAPSHOT.read_text(encoding="utf-8"))
    before_doc = json.loads(BEFORE_SNAPSHOT.read_text(encoding="utf-8"))

    # after -> before (откат)
    plan = plan_rollback(after_doc, before_doc)
    log(f"rollback plan: {plan.counts}")
    if not plan.feasible:
        raise ValueError(f"rollback plan not feasible: {plan.conflicts}")
    stats = apply_rollback(plan)
    log(f"rollback applied: {stats}")

    # before -> after (forward)
    plan_fwd = plan_rollback(before_doc, after_doc)
    log(f"forward plan: {plan_fwd.counts}")
    if not plan_fwd.feasible:
        raise ValueError(f"forward plan not feasible: {plan_fwd.conflicts}")
    stats_fwd = apply_rollback(plan_fwd)
    log(f"forward applied: {stats_fwd}")

    # Контрольный снимок после forward должен совпадать с after
    verify_doc = build_snapshot(product_ids=product_ids)
    if verify_doc["canonical"]["rows"] != after_doc["canonical"]["rows"]:
        raise ValueError("ROLLBACK TEST FAILED: state after forward != planned after")
    log("ROLLBACK TEST PASS")


# ---------------------------------------------------------------------------
# Главный пайплайн
# ---------------------------------------------------------------------------
def main() -> None:
    ensure_artifacts_dir()
    info = preflight()

    # Снимок ДО
    take_snapshot(BEFORE_SNAPSHOT, product_ids)

    # pg_dump перед write
    run_pg_dump()

    # Write
    log("=== APPLY BATCH ===")
    apply_batch(info["attribute"], info["live_options"])

    # Снимок ПОСЛЕ
    take_snapshot(AFTER_SNAPSHOT, product_ids)

    # Rollback-map
    option_by_slug = {o.slug: o for o in info["attribute"].options.all()}
    save_rollback_map(option_by_slug)

    # Post-audit
    post_audit(info["predicted_counts"], info["before_hash"])

    # Испытание отката
    test_rollback()

    log("=== TT-10 BATCH COMPLETE ===")


main()
