"""Бэкфилл автообработки фото товаров (ADR-0014).

    process_product_images --dry-run            # только посчитать классы фона
    process_product_images --dry-run --out report.json
    process_product_images                      # в очередь: необработанные и упавшие
    process_product_images --status queued      # перепоставить зависшие в очереди
    process_product_images --outdated           # пересоздать копии после смены параметров
    process_product_images --source huter --limit 50
    process_product_images --rembg              # чёрный и прочий фон — в сервис нейросети

Команда сама фото не обрабатывает — только ставит задачи в очередь `images`
(воркер `celery-images`, строго по одному). Повторная постановка безопасна: задача
идемпотентна. `--dry-run` читает файлы, но ничего не пишет ни в БД, ни в media.
Кроме классов фона он считает, что уйдёт менеджеру на проверку (мелкие фото,
повторы кадра среди отобранных фото), и товары, у которых есть фото, но нет главного.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from apps.catalog import image_autoprocess, image_processing
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

    def handle(self, *args, **options):
        default = (ImageProcessingStatus.NEEDS_REMBG,) if options["rembg"] else DEFAULT_STATUSES
        statuses = tuple(options["status"] or default)
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
            image_processing.ImageKind.OTHER: "прочий фон (ждёт нейросеть)",
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
