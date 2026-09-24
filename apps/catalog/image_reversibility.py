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
- **Витринная копия (ADR-0014).** У записи может быть второй файл `display`,
  производный от `image`. Снимок и аудит считают его «своим» (не сиротой),
  аудит сверяет его с `display_checksum`, откат удаляет оба файла. Копия
  принадлежит ровно одной записи — делить файл копии между записями нельзя,
  иначе откат одной снесёт копию другой. Ключи отчётов для `image` не менялись:
  старые планы отката применимы, новые ключи только добавлены.
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
    display_name = image.display.name or ""
    display_meta = files.get(display_name) if display_name else None
    candidate_name = image.candidate.name or ""
    candidate_meta = files.get(candidate_name) if candidate_name else None
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
        "display_file": display_name,
        "display_file_exists": display_meta is not None,
        "display_file_checksum": (display_meta or {}).get("checksum"),
        "display_db_checksum": image.display_checksum or None,
        "processing_status": image.processing_status,
        # Доработка контролёра качества: кандидат — отдельный файл, отдельно от
        # принятой копии (может совпадать с display_file, если кандидат уже
        # промоутирован — тогда это ОДИН файл на диске, не дубль).
        "candidate_file": candidate_name,
        "candidate_file_exists": candidate_meta is not None,
        "candidate_file_checksum": (candidate_meta or {}).get("checksum"),
        "candidate_db_checksum": image.candidate_checksum or None,
        "purpose": image.purpose,
        "qc_decision": image.qc_decision or None,
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
    referenced |= {r["display_file"] for r in records if r["display_file"]}
    referenced |= {r["candidate_file"] for r in records if r["candidate_file"]}
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

    def _distinct_files(t: dict) -> set[str]:
        # Только СУЩЕСТВУЮЩИЕ файлы (как раньше, без display) — пропавший файл не
        # в счёт удаления. Кандидат может совпадать с display_file (промоутированный
        # кандидат — один файл на диске под двумя полями): считаем его один раз.
        names: set[str] = set()
        if t["file_exists"]:
            names.add(t["file"])
        if t["display_file_exists"]:
            names.add(t["display_file"])
        if t["candidate_file_exists"]:
            names.add(t["candidate_file"])
        return names

    return {
        "kind": "product_images_rollback_plan",
        "source": source,
        "since": since.isoformat() if since else None,
        "until": until.isoformat() if until else None,
        "records_to_delete": len(targets),
        # исходный + витринная копия + кандидат (без дублей на один файл, ADR-0014)
        "files_to_delete": sum(len(_distinct_files(t)) for t in targets),
        "display_files_to_delete": sum(1 for t in targets if t["display_file_exists"]),
        "candidate_files_to_delete": sum(
            1
            for t in targets
            if t["candidate_file_exists"] and t["candidate_file"] != t["display_file"]
        ),
        "files_missing": sum(1 for t in targets if t["file"] and not t["file_exists"]),
        "display_files_missing": sum(
            1 for t in targets if t["display_file"] and not t["display_file_exists"]
        ),
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
    expected = {t["id"]: t for t in plan["targets"]}
    live = {
        image.pk: image for image in ProductImage.objects.select_for_update().filter(pk__in=ids)
    }

    conflicts = []
    for pk, target in expected.items():
        image = live.get(pk)
        if image is None:
            conflicts.append({"id": pk, "reason": "запись исчезла между планом и применением"})
        elif image.source != target["source"] or (image.image.name or "") != target["file"]:
            conflicts.append({"id": pk, "reason": "запись изменилась между планом и применением"})
        elif image.source == ImageSource.MANUAL:
            conflicts.append({"id": pk, "reason": "запись стала manual — трогать нельзя"})
        elif "display_file" in target and (image.display.name or "") != target["display_file"]:
            # Планы до ADR-0014 ключа не знают — у них сверяем только оригинал.
            conflicts.append(
                {"id": pk, "reason": "витринная копия изменилась между планом и применением"}
            )
        elif (
            "candidate_file" in target and (image.candidate.name or "") != target["candidate_file"]
        ):
            # Планы до доработки контролёра ключа не знают — тот же принцип обратной
            # совместимости, что у display_file выше.
            conflicts.append({"id": pk, "reason": "кандидат изменился между планом и применением"})
    if conflicts:
        raise RollbackRefused(
            f"откат не применён целиком: конфликтов {len(conflicts)} " f"(первый: {conflicts[0]})"
        )

    root = media_root()
    files_deleted = 0
    files_absent = 0
    display_files_deleted = 0
    candidate_files_deleted = 0
    for image in live.values():
        # Витринная копия и кандидат производны от оригинала и без него смысла не
        # имеют. Кандидат может указывать на ТОТ ЖЕ файл, что и display (промоушен
        # переиспользует имя) — группируем по физическому имени, чтобы удалить его
        # только один раз, но засчитать в оба счётчика, если оба поля на него ссылались.
        names: dict[str, set[str]] = {}
        if image.image.name:
            names.setdefault(image.image.name, set())
        if image.display.name:
            names.setdefault(image.display.name, set()).add("display")
        if image.candidate.name:
            names.setdefault(image.candidate.name, set()).add("candidate")
        for name, kinds in names.items():
            try:
                (root / name).unlink()
                files_deleted += 1
                if "display" in kinds:
                    display_files_deleted += 1
                if "candidate" in kinds:
                    candidate_files_deleted += 1
            except FileNotFoundError:
                files_absent += 1
    deleted, _ = ProductImage.objects.filter(pk__in=list(live)).delete()
    return {
        "records_deleted": len(live),
        "rows_deleted": deleted,
        "files_deleted": files_deleted,
        "files_absent": files_absent,
        "candidate_files_deleted": candidate_files_deleted,
        "display_files_deleted": display_files_deleted,
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
    missing_display: list[dict] = []
    display_mismatch: list[dict] = []
    missing_candidate: list[dict] = []
    candidate_mismatch: list[dict] = []
    referenced: set[str] = set()

    for image in ProductImage.objects.order_by("pk").iterator(chunk_size=500):
        name = image.image.name or ""
        referenced.add(name)
        display_name = image.display.name or ""
        if display_name:
            referenced.add(display_name)
            display_meta = files.get(display_name)
            if display_meta is None:
                missing_display.append({"id": image.pk, "file": display_name})
            elif display_meta["checksum"] is None or display_meta["checksum"] != (
                image.display_checksum or None
            ):
                # None у файла — копия нечитаема: при пустом display_checksum это
                # совпало бы «None == None» и молча прошло бы аудит.
                display_mismatch.append(
                    {
                        "id": image.pk,
                        "file": display_name,
                        "db_checksum": image.display_checksum or None,
                        "file_checksum": display_meta["checksum"],
                    }
                )
        candidate_name = image.candidate.name or ""
        if candidate_name:
            referenced.add(candidate_name)
            candidate_meta = files.get(candidate_name)
            if candidate_meta is None:
                missing_candidate.append({"id": image.pk, "file": candidate_name})
            elif candidate_meta["checksum"] is None or candidate_meta["checksum"] != (
                image.candidate_checksum or None
            ):
                candidate_mismatch.append(
                    {
                        "id": image.pk,
                        "file": candidate_name,
                        "db_checksum": image.candidate_checksum or None,
                        "file_checksum": candidate_meta["checksum"],
                    }
                )
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
        "missing_display_file_total": len(missing_display),
        "display_checksum_mismatch_total": len(display_mismatch),
        "missing_candidate_file_total": len(missing_candidate),
        "candidate_checksum_mismatch_total": len(candidate_mismatch),
        "missing_file": missing_file,
        "checksum_mismatch": checksum_mismatch,
        "without_checksum": no_checksum,
        "missing_display_file": missing_display,
        "display_checksum_mismatch": display_mismatch,
        "missing_candidate_file": missing_candidate,
        "candidate_checksum_mismatch": candidate_mismatch,
        "orphan_files": orphans,
    }


def audit_archive() -> dict:
    """Сверка архива отклонённых фото (§7.1) с закрытым хранилищем.

    Отдельная функция и отдельное хранилище (`PRIVATE_MEDIA_ROOT`, не
    `MEDIA_ROOT`): архив не входит в обычный `audit()`/`scan_media_files`, его
    файлы не должны попасть в список сирот публичного media.
    """
    from .models import RejectedImageCandidate, private_media_storage

    root = Path(private_media_storage.location)
    files: dict[str, dict] = {}
    if root.exists():
        for path in sorted(root.rglob("*")):
            if path.is_file():
                rel = path.relative_to(root).as_posix()
                files[rel] = {"size": path.stat().st_size, "checksum": sha256_file(path)}

    missing: list[dict] = []
    mismatch: list[dict] = []
    referenced: set[str] = set()
    for row in (
        RejectedImageCandidate.objects.order_by("pk")
        .values("pk", "file", "checksum", "readable")
        .iterator(chunk_size=500)
    ):
        name = row["file"] or ""
        if not name:
            continue
        referenced.add(name)
        meta = files.get(name)
        if meta is None:
            if row["readable"]:  # уже помеченные нечитаемыми не дублируем в отчёт
                missing.append({"id": row["pk"], "file": name})
        elif meta["checksum"] != row["checksum"]:
            mismatch.append(
                {
                    "id": row["pk"],
                    "file": name,
                    "db_checksum": row["checksum"],
                    "file_checksum": meta["checksum"],
                }
            )
    orphans = sorted(set(files) - referenced)
    return {
        "kind": "product_images_archive_audit",
        "records_total": RejectedImageCandidate.objects.count(),
        "files_total": len(files),
        "missing_file_total": len(missing),
        "checksum_mismatch_total": len(mismatch),
        "orphan_files_total": len(orphans),
        "missing_file": missing,
        "checksum_mismatch": mismatch,
        "orphan_files": orphans,
    }


# --- откат ПРОГОНА ОБРАБОТКИ (не сбора!): восстановить решение, не удаляя фото --

#: Поля, которые снимает и восстанавливает откат прогона обработки. НЕ включает
#: `image`/`checksum`/`source*`/`fetched_at`/`is_main`/`sort_order` — прогон
#: обработки их не трогает, а восстанавливать нечего.
PROCESSING_ROLLBACK_FIELDS = (
    "processing_status",
    "processing_mode",
    "processing_version",
    "review_reason",
    "duplicate_of_id",
    "fingerprint",
    "display",
    "display_checksum",
    "display_render_key",
    "candidate",
    "candidate_checksum",
    "candidate_render_key",
    "candidate_mode",
    "qc_decision",
    "qc_source",
    "qc_rules_version",
    "qc_reasons",
    "main_fit_auto",
)


def _processing_row(image: ProductImage) -> dict:
    row = {f: getattr(image, f) for f in PROCESSING_ROLLBACK_FIELDS}
    row["display"] = image.display.name or ""
    row["candidate"] = image.candidate.name or ""
    row["qc_reasons"] = list(image.qc_reasons or [])
    row["id"] = image.pk
    # Не поле отката, а условие применимости: прогон обработки не должен был
    # тронуть исходник — если он сменился, восстанавливать уже нечего (H6-стиль).
    row["source_image_name"] = image.image.name or ""
    return row


def build_processing_run_snapshot(image_ids: list[int]) -> dict:
    """Снимок «до» — вызывать ПЕРЕД прогоном `process_product_images --manifest`."""
    rows = {
        str(image.pk): _processing_row(image)
        for image in ProductImage.objects.filter(pk__in=image_ids)
    }
    return {"kind": "product_images_processing_run", "ids": list(image_ids), "before": rows}


def finalize_processing_run_snapshot(snapshot: dict) -> dict:
    """Снимок «после» — вызывать СРАЗУ ПОСЛЕ прогона, в тот же снимок."""
    ids = snapshot["ids"]
    snapshot["after"] = {
        str(image.pk): _processing_row(image) for image in ProductImage.objects.filter(pk__in=ids)
    }
    return snapshot


def build_processing_rollback_plan(snapshot: dict) -> dict:
    """Отдельно от `build_rollback_plan` (откат СБОРА): здесь ничего не удаляется,
    только восстанавливаются поля решения. Конфликт — если с момента прогона
    кто-то (человек или другой прогон) уже поменял решение по этому фото, или
    файл прежней принятой копии пропал: план с любым конфликтом не применяется
    целиком (тот же принцип fail-closed, что у отката `tool_type`).
    """
    if snapshot.get("kind") != "product_images_processing_run":
        raise RollbackRefused("на вход подан не снимок прогона обработки")
    if "after" not in snapshot:
        raise RollbackRefused("в снимке нет состояния «после» — прогон не был завершён")

    storage = ProductImage._meta.get_field("display").storage
    items = []
    for id_str, before in snapshot["before"].items():
        pk = int(id_str)
        after = snapshot["after"].get(id_str)
        image = ProductImage.objects.filter(pk=pk).first()
        item = {"id": pk}
        if image is None:
            item["action"], item["reason"] = "conflict", "запись исчезла после прогона"
        elif after is None:
            item["action"], item["reason"] = "conflict", "для записи нет состояния «после»"
        elif _processing_row(image) != after:
            item["action"], item["reason"] = (
                "conflict",
                "запись изменилась после прогона (новое решение человека или воркера)",
            )
        elif before["display"] and not storage.exists(before["display"]):
            item["action"], item["reason"] = "conflict", "файл прежней принятой копии недоступен"
        else:
            item["action"] = "restore"
        items.append(item)

    return {
        "kind": "product_images_processing_rollback_plan",
        "restore": sum(1 for i in items if i["action"] == "restore"),
        "conflict": sum(1 for i in items if i["action"] == "conflict"),
        "items": items,
        "snapshot": snapshot,
    }


@transaction.atomic
def apply_processing_rollback(plan: dict) -> dict:
    if plan.get("kind") != "product_images_processing_rollback_plan":
        raise RollbackRefused("на вход подан не план отката обработки")
    if plan["conflict"]:
        raise RollbackRefused(
            f"откат не применён целиком: конфликтов {plan['conflict']} из {len(plan['items'])}"
        )
    restored = 0
    for id_str, before in plan["snapshot"]["before"].items():
        fields = {f: before[f] for f in PROCESSING_ROLLBACK_FIELDS}
        restored += ProductImage.objects.filter(pk=int(id_str)).update(**fields)
    return {"restored": restored}
