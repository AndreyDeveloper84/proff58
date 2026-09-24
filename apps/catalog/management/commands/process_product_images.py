"""Бэкфилл, точечное применение и предпросмотр автообработки фото (ADR-0014).

Постановка в очередь (как раньше, ничего не изменилось):

    process_product_images --dry-run            # только посчитать классы фона
    process_product_images --dry-run --out report.json
    process_product_images                      # в очередь: необработанные и упавшие
    process_product_images --status queued      # перепоставить зависшие в очереди
    process_product_images --outdated           # пересоздать копии после смены параметров
    process_product_images --source huter --limit 50
    process_product_images --rembg              # чёрный фон — в сервис нейросети

Точечное применение по зафиксированным ID (доработка контролёра качества, НЕ
общий бэкфилл выше — синхронно, обходит `FEATURE_PRODUCT_IMAGE_AUTOPROCESS`, но
не `content_locked`/`rejected`):

    process_product_images --manifest ids.json --dry-run --artifacts-dir out/  # предпросмотр
    process_product_images --manifest ids.json --snapshot run.json --apply     # применение
    catalog_images_ops --mode processing-rollback --snapshot run.json --apply  # откат

Предпросмотр локальных файлов вне каталога, без БД (пилот на образцах):

    process_product_images --files a.jpg b.webp --artifacts-dir out/ --out report.json

Прочее не меняет: команда без `--manifest`/`--files` только ставит задачи в
очередь `images` (воркер `celery-images`, строго по одному) — саму обработку не
делает. `--dry-run` без `--manifest` читает файлы, но ничего не пишет ни в БД, ни
в media; кроме классов фона считает, что уйдёт менеджеру на проверку, и товары
без главного фото.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from apps.catalog import image_autoprocess, image_processing, image_quality, image_rembg
from apps.catalog.image_reversibility import (
    build_processing_run_snapshot,
    finalize_processing_run_snapshot,
)
from apps.catalog.models import ImageProcessingStatus, ImageSource, Product, ProductImage
from apps.core.features import is_enabled

DEFAULT_STATUSES = (ImageProcessingStatus.NONE, ImageProcessingStatus.FAILED)


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("нужно целое число больше нуля")
    return number


class Command(BaseCommand):
    help = "Поставить фото товаров в очередь автообработки (или посчитать классы: --dry-run)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--status",
            action="append",
            choices=[
                s for s in ImageProcessingStatus.values if s != ImageProcessingStatus.REJECTED
            ],
            help="Какие статусы брать (можно несколько). По умолчанию none и failed.",
        )
        parser.add_argument(
            "--outdated",
            action="store_true",
            help="Добавить готовые записи со старой версией параметров обработки.",
        )
        parser.add_argument("--source", choices=ImageSource.values)
        parser.add_argument("--limit", type=_positive_int)
        parser.add_argument(
            "--rembg",
            action="store_true",
            help="Фото «ждёт удаления фона» — в очередь сервиса нейросети celery-rembg.",
        )
        parser.add_argument("--dry-run", action="store_true", help="Только посчитать классы фона.")
        parser.add_argument("--out", help="--dry-run: записать отчёт JSON в файл.")
        parser.add_argument(
            "--manifest",
            help='JSON со списком ID ProductImage ({"ids":[...]} или [...]) — точечное '
            "применение/предпросмотр вместо --status/--source/--limit.",
        )
        parser.add_argument(
            "--files",
            nargs="+",
            help="Локальные файлы вне каталога — только предпросмотр, без БД и без записи.",
        )
        parser.add_argument(
            "--artifacts-dir",
            help="--dry-run/--files: папка для листов сравнения исходник→предложение.",
        )
        parser.add_argument(
            "--snapshot",
            help="--manifest --apply: файл снимка «до/после» для отката "
            "(catalog_images_ops --mode processing-rollback).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="--manifest: применить синхронно (обходит FEATURE_PRODUCT_IMAGE_AUTOPROCESS, "
            "не content_locked/rejected). Требует --snapshot.",
        )
        parser.add_argument(
            "--redecide",
            action="store_true",
            help="Пересчитать решение контролёра по сохранённым признакам после смены "
            "версии правил — без перерисовки файла и без нейросети.",
        )
        parser.add_argument(
            "--promote-observed",
            action="store_true",
            help="Опубликовать кандидатов из «наблюдения» после включения их маршрута "
            "в PRODUCT_IMAGE_AUTO_ACCEPT_ROUTES — без перерисовки и без нейросети.",
        )

    def handle(self, *args, **options):
        if options["promote_observed"]:
            return self._promote_observed()
        if options["redecide"]:
            return self._redecide(options)
        if options["files"]:
            return self._preview_files(options["files"], options)
        if options["manifest"]:
            return self._manifest(options)
        default = (ImageProcessingStatus.NEEDS_REMBG,) if options["rembg"] else DEFAULT_STATUSES
        statuses = tuple(options["status"] or default)
        if options["rembg"] and set(statuses) - {ImageProcessingStatus.NEEDS_REMBG}:
            # Иначе задача, вышедшая без работы, вернула бы фото в «ждёт удаления
            # фона» — статус, которого для этих записей уже не существует.
            raise CommandError("--rembg работает только со статусом needs_rembg")
        condition = Q(processing_status__in=statuses)
        if options["outdated"]:
            condition |= Q(
                processing_status__in=image_autoprocess.SETTLED,
                processing_version__lt=image_processing.PROCESSING_VERSION,
            )
        qs = (
            ProductImage.objects.filter(condition, product__content_locked=False)
            .exclude(image="")
            # «Оставить оригинал» — решение менеджера, бэкфилл его не перебивает
            .exclude(processing_status=ImageProcessingStatus.REJECTED)
            .order_by("pk")
        )
        if options["source"]:
            qs = qs.filter(source=options["source"])
        if options["limit"]:
            qs = qs[: options["limit"]]

        if options["dry_run"]:
            self._dry_run(qs, options.get("out"))
            return

        if not is_enabled(image_autoprocess.FLAG):
            raise CommandError(
                "автообработка выключена: FEATURE_PRODUCT_IMAGE_AUTOPROCESS=False. "
                "Посчитать без записи можно с --dry-run"
            )
        queued = skipped = 0
        for image_id in list(qs.values_list("pk", flat=True)):
            if image_autoprocess.enqueue(
                image_id, statuses=statuses, outdated=options["outdated"], rembg=options["rembg"]
            ):
                queued += 1
            else:
                skipped += 1
        self.stdout.write(self.style.SUCCESS(f"Поставлено в очередь: {queued}"))
        if options["rembg"] and queued:
            self.stdout.write(
                "Задачи ждут сервис нейросети. Поднять на время обработки:\n"
                "  docker compose -f docker-compose.prod.yml --profile rembg up -d celery-rembg\n"
                "Погасить после: docker compose -f docker-compose.prod.yml stop celery-rembg"
            )
        if skipped:
            self.stdout.write(
                self.style.WARNING(
                    f"Не поставлено: {skipped} (статус уже сменился или брокер недоступен — "
                    "см. лог)"
                )
            )

    def _dry_run(self, qs, out: str | None) -> None:
        kinds: Counter[str] = Counter()
        small = duplicates = 0
        rows = []
        # кадры каждого товара, уже встреченные в прогоне (сами дубли не в счёт)
        seen: defaultdict[int, list[tuple[int, str]]] = defaultdict(list)
        for image in qs.iterator(chunk_size=200):
            row = {"id": image.pk, "product_id": image.product_id}
            rows.append(row)
            try:
                with image.image.storage.open(image.image.name, "rb") as fh:
                    result = image_processing.process(fh.read())
            except (OSError, image_processing.UnreadableImage):
                row["kind"] = "unreadable"
                kinds["unreadable"] += 1
                continue
            row["kind"] = result.kind
            kinds[result.kind] += 1
            if result.square is not None and result.square.small:
                row["small"] = True
                small += 1
            frames = seen[image.product_id]
            first = next(
                (
                    pk
                    for pk, mark in frames
                    if image_processing.is_duplicate(result.fingerprint, mark)
                ),
                None,
            )
            if first is None:
                frames.append((image.pk, result.fingerprint))
            else:
                row["duplicate_of"] = first
                duplicates += 1

        without_main = list(
            Product.objects.filter(images__isnull=False)
            .exclude(images__is_main=True)
            .values_list("pk", flat=True)
            .distinct()
            .order_by("pk")
        )

        labels = {
            image_processing.ImageKind.WHITE: "белый фон (обработается сразу)",
            image_processing.ImageKind.ALPHA: "прозрачный фон (обработается сразу)",
            image_processing.ImageKind.BLACK: "чёрный фон (ждёт нейросеть)",
            image_processing.ImageKind.OTHER: "прочий фон (не обрабатывается)",
            image_processing.ImageKind.BLANK: "пустой кадр (на проверку)",
            "unreadable": "не читается",
        }
        self.stdout.write(f"DRY-RUN: фото {sum(kinds.values())}, ничего не записано")
        for kind, label in labels.items():
            self.stdout.write(f"  {label:38} {kinds.get(kind, 0)}")
        self.stdout.write("Пойдут на проверку менеджеру:")
        self.stdout.write(f"  {'мелкие (товар меньше половины квадрата)':38} {small}")
        self.stdout.write(f"  {'повтор кадра того же товара':38} {duplicates}")
        self.stdout.write(f"Товаров с фото, но без главного фото: {len(without_main)}")
        if without_main:
            self.stdout.write(f"  например: {', '.join(map(str, without_main[:10]))}")
        if out:
            path = Path(out)
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "kind": "product_images_autoprocess_dry_run",
                "counts": kinds,
                "small": small,
                "duplicates": duplicates,
                "products_without_main": without_main,
                "items": rows,
            }
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self.stdout.write(f"JSON записан: {path}")

    # --- точечное применение по манифесту и предпросмотр --------------------

    def _manifest_ids(self, path: str) -> list[int]:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        ids = raw.get("ids") if isinstance(raw, dict) else raw
        if not ids or not all(isinstance(i, int) for i in ids):
            raise CommandError('--manifest: нужен JSON {"ids": [int, ...]} или [int, ...]')
        return list(dict.fromkeys(ids))  # без дублей, порядок сохранён

    def _promote_observed(self) -> None:
        count = image_autoprocess.promote_observed()
        self.stdout.write(self.style.SUCCESS(f"Опубликовано из наблюдения: {count}"))

    def _redecide(self, options) -> None:
        qs = ProductImage.objects.filter(
            processing_status__in=image_autoprocess.SETTLED,
            qc_rules_version__lt=image_quality.QC_RULES_VERSION,
        ).exclude(qc_features={})
        if options["limit"]:
            qs = qs[: options["limit"]]
        counts: Counter[str] = Counter()
        for image_id in list(qs.values_list("pk", flat=True)):
            counts[image_autoprocess.redecide(image_id)] += 1
        self.stdout.write(f"Пересчитано без перерисовки: {sum(counts.values())}")
        for status, n in sorted(counts.items()):
            self.stdout.write(f"  {status}: {n}")

    def _manifest(self, options) -> None:
        ids = self._manifest_ids(options["manifest"])
        qs = ProductImage.objects.filter(pk__in=ids).exclude(
            processing_status=ImageProcessingStatus.REJECTED
        )
        found_ids = list(qs.values_list("pk", flat=True))
        missing = sorted(set(ids) - set(found_ids))
        if missing:
            self.stdout.write(self.style.WARNING(f"Не найдены или rejected: {missing}"))

        if options["dry_run"]:
            self._preview_manifest(qs, options.get("out"), options.get("artifacts_dir"))
            return
        if not options["apply"]:
            raise CommandError("--manifest без --dry-run требует --apply")
        if not options["snapshot"]:
            raise CommandError("--apply с --manifest требует --snapshot FILE (нужен для отката)")

        snapshot = build_processing_run_snapshot(found_ids)
        processed: Counter[str] = Counter()
        for image_id in found_ids:
            result = image_autoprocess.process_image(image_id, rembg=options["rembg"], force=True)
            processed[result] += 1
        finalize_processing_run_snapshot(snapshot)
        path = Path(options["snapshot"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"Применено синхронно: {len(found_ids)} фото"))
        for status, n in sorted(processed.items()):
            self.stdout.write(f"  {status}: {n}")
        self.stdout.write(
            f"Снимок для отката: {path}\n"
            f"  Откат: catalog_images_ops --mode processing-rollback --snapshot {path} --apply"
        )

    @staticmethod
    def _write_artifact(
        artifacts_dir: str | None, label: str, raw: bytes, proposed: bytes | None
    ) -> None:
        if not artifacts_dir:
            return
        out_dir = Path(artifacts_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(label))
        (out_dir / f"{stem}-original.bin").write_bytes(raw)
        if proposed is not None:
            (out_dir / f"{stem}-proposed.webp").write_bytes(proposed)

    def _preview_one(self, label, raw: bytes) -> dict:
        """Один файл → решение контролёра. Общий код для `--files` (без БД, без
        дублей/назначения — их некому проверить) и предпросмотра `--manifest`."""
        row: dict = {"item": label}
        try:
            result = image_processing.process(raw)
        except image_processing.UnreadableImage as exc:
            row["error"] = f"не читается: {exc}"
            return row
        row["kind"] = result.kind
        square = result.square
        route = image_quality.Route.TRIM
        mask_bbox = None
        is_empty = result.kind == image_processing.ImageKind.BLANK

        if result.kind == image_processing.ImageKind.OTHER:
            row["decision"] = "skipped"
            row["reasons"] = []
            return row
        if square is None and not is_empty:  # чёрный фон
            if not image_rembg.is_available():
                row["decision"] = "needs_rembg"
                row["reasons"] = []
                row["note"] = "нейросеть недоступна в этом образе — не измерено"
                return row
            rendered = image_rembg.render(image_processing.open_image(raw))
            if rendered is None:
                is_empty = True
            else:
                square, mask_bbox = rendered
                route = image_quality.Route.REMBG_BLACK
        if is_empty:
            row["decision"] = "auto_reject_candidate"
            row["reasons"] = ["empty"]
            return row

        source_img = image_processing.open_image(raw)
        if route == image_quality.Route.TRIM:
            source_rgb = (
                image_processing.flatten_on_white(source_img)
                if result.kind == image_processing.ImageKind.ALPHA
                else source_img.convert("RGB")
            )
            content_bbox = image_processing.content_bbox(source_rgb)
        else:
            content_bbox = mask_bbox
        square_rgb = image_processing.open_image(square.content).convert("RGB")
        product_share = (
            image_processing.product_share_for_size(
                content_bbox[2] - content_bbox[0], content_bbox[3] - content_bbox[1]
            )
            if content_bbox
            else 0.0
        )
        features = image_quality.analyze(
            source_size=source_img.size,
            content_bbox=content_bbox,
            square=square,
            square_rgb=square_rgb,
            product_share=product_share,
        )
        verdict = image_quality.decide(
            features,
            route=route,
            is_duplicate=False,
            is_empty=False,
            purpose_confirmed_subject=True,
        )
        row["decision"] = verdict.decision
        row["reasons"] = verdict.reasons
        row["features"] = features.to_dict()
        row["_proposed"] = square.content
        return row

    def _preview_files(self, files: list[str], options) -> None:
        artifacts_dir = options.get("artifacts_dir")
        rows = []
        for file_path in files:
            raw = Path(file_path).read_bytes()
            row = self._preview_one(file_path, raw)
            proposed = row.pop("_proposed", None)
            rows.append(row)
            if "error" in row:
                self.stdout.write(self.style.ERROR(f"{file_path}: {row['error']}"))
                continue
            reasons = f" ({', '.join(row['reasons'])})" if row.get("reasons") else ""
            self.stdout.write(f"{file_path}: {row['decision']}{reasons}")
            self._write_artifact(artifacts_dir, Path(file_path).stem, raw, proposed)
        self._write_preview_report(options.get("out"), rows)

    def _preview_manifest(self, qs, out: str | None, artifacts_dir: str | None) -> None:
        rows = []
        for image in qs.iterator(chunk_size=200):
            try:
                with image.image.storage.open(image.image.name, "rb") as fh:
                    raw = fh.read()
            except OSError as exc:
                rows.append({"item": image.pk, "product_id": image.product_id, "error": str(exc)})
                continue
            row = self._preview_one(image.pk, raw)
            row["product_id"] = image.product_id
            proposed = row.pop("_proposed", None)
            rows.append(row)
            reasons = f" ({', '.join(row['reasons'])})" if row.get("reasons") else ""
            label = row.get("decision") or row.get("error", "")
            self.stdout.write(f"#{image.pk} (товар {image.product_id}): {label}{reasons}")
            self._write_artifact(artifacts_dir, image.pk, raw, proposed)
        self._write_preview_report(out, rows)

    def _write_preview_report(self, out: str | None, rows: list[dict]) -> None:
        if not out:
            return
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"kind": "product_images_manifest_preview", "items": rows}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(f"JSON записан: {path}")
