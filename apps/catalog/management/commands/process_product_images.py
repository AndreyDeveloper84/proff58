"""Бэкфилл автообработки фото товаров (ADR-0014).

    process_product_images --dry-run            # только посчитать классы фона
    process_product_images --dry-run --out report.json
    process_product_images                      # в очередь: необработанные и упавшие
    process_product_images --status queued      # перепоставить зависшие в очереди
    process_product_images --outdated           # пересоздать копии после смены параметров
    process_product_images --source huter --limit 50

Команда сама фото не обрабатывает — только ставит задачи в очередь `images`
(воркер `celery-images`, строго по одному). Повторная постановка безопасна: задача
идемпотентна. `--dry-run` читает файлы, но ничего не пишет ни в БД, ни в media.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from apps.catalog import image_autoprocess, image_processing
from apps.catalog.models import ImageProcessingStatus, ImageSource, ProductImage
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
        parser.add_argument("--dry-run", action="store_true", help="Только посчитать классы фона.")
        parser.add_argument("--out", help="--dry-run: записать отчёт JSON в файл.")

    def handle(self, *args, **options):
        statuses = tuple(options["status"] or DEFAULT_STATUSES)
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
            if image_autoprocess.enqueue(image_id, statuses=statuses, outdated=options["outdated"]):
                queued += 1
            else:
                skipped += 1
        self.stdout.write(self.style.SUCCESS(f"Поставлено в очередь: {queued}"))
        if skipped:
            self.stdout.write(
                self.style.WARNING(
                    f"Не поставлено: {skipped} (статус уже сменился или брокер недоступен — "
                    "см. лог)"
                )
            )

    def _dry_run(self, qs, out: str | None) -> None:
        kinds: Counter[str] = Counter()
        rows = []
        for image in qs.iterator(chunk_size=200):
            try:
                with image.image.storage.open(image.image.name, "rb") as fh:
                    kind = image_processing.classify(image_processing.open_image(fh.read()))
            except (OSError, image_processing.UnreadableImage):
                kind = "unreadable"
            kinds[kind] += 1
            rows.append({"id": image.pk, "product_id": image.product_id, "kind": kind})

        labels = {
            image_processing.ImageKind.WHITE: "белый фон (обработается сразу)",
            image_processing.ImageKind.ALPHA: "прозрачный фон (обработается сразу)",
            image_processing.ImageKind.BLACK: "чёрный фон (ждёт нейросеть)",
            image_processing.ImageKind.OTHER: "прочий фон (ждёт нейросеть)",
            "unreadable": "не читается",
        }
        self.stdout.write(f"DRY-RUN: фото {sum(kinds.values())}, ничего не записано")
        for kind, label in labels.items():
            self.stdout.write(f"  {label:38} {kinds.get(kind, 0)}")
        if out:
            path = Path(out)
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"kind": "product_images_autoprocess_dry_run", "counts": kinds, "items": rows}
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self.stdout.write(f"JSON записан: {path}")
