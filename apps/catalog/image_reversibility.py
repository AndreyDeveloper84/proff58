# apps/catalog/image_reversibility.py
"""Обратимость прогонов сбора изображений товаров (ИЗО-02).

`pg_dump` не покрывает файлы в media-томе: снимок БД без снимка файловой
системы обратимость НЕ даёт. Здесь — вторая половина снимка и весь контур:

снимок «до» → план прогона → откат конкретного прогона → post-audit.

Инварианты:

- **`manual` неприкосновенен.** Откат работает только по спарсенным источникам
  (`source != manual`); попытка откатить `manual` — отказ, а не «ну ладно».
- **Осиротевшие файлы не удаляются.** Команда обязана их найти и показать
  (на стенде их уже 37), но чистка media — отдельное решение владельца.
- Идемпотентность записи держится на БД-ограничениях
  (`uniq_product_image_checksum`, `uniq_product_image_source_url`), а не на
  аккуратности вызывающего кода: план здесь только объясняет, что произойдёт.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db import transaction

from .models import ImageSource, ProductImage

CHUNK = 1024 * 1024
DEFAULT_SUBDIR = "products"


class RollbackRefused(Exception):
    """Откат запрещён инвариантом (например, попытка снести `manual`)."""


# --- контрольные суммы -------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str | None:
    """sha256 файла; None — файла нет или он нечитаем."""
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            while chunk := fh.read(CHUNK):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def media_root() -> Path:
    return Path(settings.MEDIA_ROOT)


def scan_media_files(
    subdir: str = DEFAULT_SUBDIR, *, with_checksum: bool = True
) -> dict[str, dict]:
    """Файлы поддерева media (по умолчанию `products/`) → метаданные.

    Ключ — путь относительно MEDIA_ROOT в posix-форме, ровно как хранит
    `ProductImage.image.name`, иначе сверка Windows/Linux разъедется.
    """
    root = media_root()
    base = root / subdir
    out: dict[str, dict] = {}
    if not base.exists():
        return out
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        out[rel] = {
            "size": path.stat().st_size,
            "checksum": sha256_file(path) if with_checksum else None,
        }
    return out


# --- снимок -------------------------------------------------------------


def _record_row(image: ProductImage, files: dict[str, dict]) -> dict:
    name = image.image.name or ""
    file_meta = files.get(name)
    return {
        "id": image.pk,
        "product_id": image.product_id,
        "file": name,
        "file_exists": file_meta is not None,
        "file_checksum": (file_meta or {}).get("checksum"),
        "db_checksum": image.checksum,
        "source": image.source,
        "source_url": image.source_url,
        "fetched_at": image.fetched_at.isoformat() if image.fetched_at else None,
        "is_main": image.is_main,
        "sort_order": image.sort_order,
        "alt": image.alt,
    }


def build_snapshot(subdir: str = DEFAULT_SUBDIR) -> dict:
    """Снимок «до»: записи ProductImage + файлы media + их checksum.

    Пара (этот снимок, `pg_dump`) — и есть полная обратимость: БД отдельно,
    файлы отдельно, ни один из двух сам по себе не достаточен.
    """
    files = scan_media_files(subdir)
    records = [
        _record_row(image, files)
        for image in ProductImage.objects.order_by("pk").iterator(chunk_size=500)
    ]
    referenced = {r["file"] for r in records if r["file"]}
    orphans = sorted(set(files) - referenced)
    by_source: dict[str, int] = {}
    for row in records:
        by_source[row["source"]] = by_source.get(row["source"], 0) + 1
    return {
        "kind": "product_images_snapshot",
        "media_root": str(media_root()),
        "subdir": subdir,
        "records_total": len(records),
        "records_by_source": by_source,
        "files_total": len(files),
        "orphan_files_total": len(orphans),
        "records": records,
        "files": [{"file": k, **v} for k, v in sorted(files.items())],
        # НЕ удаляем: список осиротевших — предмет отдельного решения владельца
        "orphan_files": orphans,
    }


# --- план прогона -------------------------------------------------------


@dataclass
class PlanCounters:
    add: int = 0
    skip_same_url: int = 0
    skip_same_checksum: int = 0
    invalid: int = 0
    items: list[dict] = field(default_factory=list)


def build_plan(candidates: list[dict]) -> dict:
    """Что даст прогон: что добавится, что отлетит как дубль и почему.

    Кандидат: `{"product_id": int, "source_url": str, "checksum": str|None,
    "source": str}`. `checksum` до скачивания неизвестен — тогда решает только
    URL, и это честно отражено в причине пропуска.
    """
    counters = PlanCounters()
    # дубли внутри самой пачки кандидатов ловим тем же ключом, что и БД
    seen_urls: set[tuple[int, str]] = set()
    seen_sums: set[tuple[int, str]] = set()

    for raw in candidates:
        product_id = raw.get("product_id")
        url = (raw.get("source_url") or "").strip() or None
        checksum = (raw.get("checksum") or "").strip() or None
        source = raw.get("source") or ""
        item = {
            "product_id": product_id,
            "source_url": url,
            "checksum": checksum,
            "source": source,
        }
        if not product_id or not url or source not in ImageSource.values:
            item["action"] = "invalid"
            item["reason"] = "нет product_id/source_url либо неизвестный source"
            counters.invalid += 1
            counters.items.append(item)
            continue
        if source == ImageSource.MANUAL:
            item["action"] = "invalid"
            item["reason"] = "source=manual в плане прогона недопустим"
            counters.invalid += 1
            counters.items.append(item)
            continue

        url_key = (product_id, url)
        sum_key = (product_id, checksum) if checksum else None

        if (
            url_key in seen_urls
            or ProductImage.objects.filter(product_id=product_id, source_url=url).exists()
        ):
            item["action"] = "skip"
            item["reason"] = "тот же URL у того же товара (uniq_product_image_source_url)"
            counters.skip_same_url += 1
        elif sum_key and (
            sum_key in seen_sums
            or ProductImage.objects.filter(product_id=product_id, checksum=checksum).exists()
        ):
            item["action"] = "skip"
            item["reason"] = "те же байты у того же товара (uniq_product_image_checksum)"
            counters.skip_same_checksum += 1
        else:
            item["action"] = "add"
            item["reason"] = "новая картинка для товара"
            counters.add += 1
            seen_urls.add(url_key)
            if sum_key:
                seen_sums.add(sum_key)
        counters.items.append(item)

    return {
        "kind": "product_images_plan",
        "candidates_total": len(candidates),
        "add": counters.add,
        "skip_same_url": counters.skip_same_url,
        "skip_same_checksum": counters.skip_same_checksum,
        "invalid": counters.invalid,
        "items": counters.items,
    }


# --- откат --------------------------------------------------------------


def build_rollback_plan(
    *,
    source: str,
    since: datetime | None = None,
    until: datetime | None = None,
    subdir: str = DEFAULT_SUBDIR,
) -> dict:
    """Что снесёт откат прогона `source` в окне `fetched_at ∈ [since, until]`.

    `manual` откатить нельзя: это единственный источник, который контур сбора
    не создавал, и терять его нечем компенсировать.
    """
    if source == ImageSource.MANUAL:
        raise RollbackRefused(
            "откат source=manual запрещён: manual-записи загружены руками "
            "и контуром сбора не создавались"
        )
    if source not in ImageSource.values:
        raise RollbackRefused(f"неизвестный source={source!r}; допустимы {ImageSource.values}")

    qs = ProductImage.objects.filter(source=source)
    if since is not None:
        qs = qs.filter(fetched_at__gte=since)
    if until is not None:
        qs = qs.filter(fetched_at__lte=until)

    files = scan_media_files(subdir)
    targets = [_record_row(image, files) for image in qs.order_by("pk")]
    return {
        "kind": "product_images_rollback_plan",
        "source": source,
        "since": since.isoformat() if since else None,
        "until": until.isoformat() if until else None,
        "records_to_delete": len(targets),
        "files_to_delete": sum(1 for t in targets if t["file_exists"]),
        "files_missing": sum(1 for t in targets if t["file"] and not t["file_exists"]),
        "manual_untouched": ProductImage.objects.filter(source=ImageSource.MANUAL).count(),
        "targets": targets,
    }


@transaction.atomic
def apply_rollback(plan: dict) -> dict:
    """Исполнение плана отката: записи и их файлы, одной транзакцией.

    Повторная сверка внутри транзакции под `SELECT … FOR UPDATE`: план строится
    вне неё, и чужая запись, успевшая занять id между планом и применением,
    даёт конфликт, а не молчаливое удаление чужого (тот же принцип, что в
    откате `tool_type`, H6).
    """
    if plan.get("kind") != "product_images_rollback_plan":
        raise RollbackRefused("на вход подан не план отката изображений")

    ids = [t["id"] for t in plan["targets"]]
    expected = {t["id"]: (t["source"], t["file"]) for t in plan["targets"]}
    live = {
        image.pk: image for image in ProductImage.objects.select_for_update().filter(pk__in=ids)
    }

    conflicts = []
    for pk, (src, name) in expected.items():
        image = live.get(pk)
        if image is None:
            conflicts.append({"id": pk, "reason": "запись исчезла между планом и применением"})
        elif image.source != src or (image.image.name or "") != name:
            conflicts.append({"id": pk, "reason": "запись изменилась между планом и применением"})
        elif image.source == ImageSource.MANUAL:
            conflicts.append({"id": pk, "reason": "запись стала manual — трогать нельзя"})
    if conflicts:
        raise RollbackRefused(
            f"откат не применён целиком: конфликтов {len(conflicts)} " f"(первый: {conflicts[0]})"
        )

    root = media_root()
    files_deleted = 0
    files_absent = 0
    for image in live.values():
        name = image.image.name or ""
        if not name:
            continue
        path = root / name
        try:
            path.unlink()
            files_deleted += 1
        except FileNotFoundError:
            files_absent += 1
    deleted, _ = ProductImage.objects.filter(pk__in=list(live)).delete()
    return {
        "records_deleted": len(live),
        "rows_deleted": deleted,
        "files_deleted": files_deleted,
        "files_absent": files_absent,
    }


# --- post-audit ---------------------------------------------------------


def audit(subdir: str = DEFAULT_SUBDIR) -> dict:
    """Сверка БД ↔ файловая система после прогона или отката.

    Осиротевшие файлы показываются, но не удаляются — ни здесь, ни где-либо
    ещё в этом контуре.
    """
    files = scan_media_files(subdir)
    missing_file: list[dict] = []
    checksum_mismatch: list[dict] = []
    no_checksum: list[dict] = []
    referenced: set[str] = set()

    for image in ProductImage.objects.order_by("pk").iterator(chunk_size=500):
        name = image.image.name or ""
        referenced.add(name)
        meta = files.get(name)
        if meta is None:
            missing_file.append({"id": image.pk, "file": name, "source": image.source})
            continue
        if image.checksum is None:
            no_checksum.append({"id": image.pk, "file": name, "source": image.source})
        elif meta["checksum"] != image.checksum:
            checksum_mismatch.append(
                {
                    "id": image.pk,
                    "file": name,
                    "db_checksum": image.checksum,
                    "file_checksum": meta["checksum"],
                }
            )

    orphans = sorted(set(files) - referenced)
    return {
        "kind": "product_images_audit",
        "records_total": ProductImage.objects.count(),
        "files_total": len(files),
        "missing_file_total": len(missing_file),
        "checksum_mismatch_total": len(checksum_mismatch),
        "without_checksum_total": len(no_checksum),
        "orphan_files_total": len(orphans),
        "missing_file": missing_file,
        "checksum_mismatch": checksum_mismatch,
        "without_checksum": no_checksum,
        "orphan_files": orphans,
    }
