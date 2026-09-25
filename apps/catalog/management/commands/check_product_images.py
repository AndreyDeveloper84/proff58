"""Проверка целостности файлов фотографий товаров.

Повод: на витрине лежали четыре снимка домкратов, и все четыре оказались
обрезанными JPEG — файл заканчивался на середине, нижнюю половину браузер
дорисовывал зелёной заливкой. Выглядело это не как «битый файл», а как кривая
вёрстка: снимок прижат к верху блока, под ним пустота.

Отличить обрезанный файл от целого глазами по списку нельзя, поэтому проверяем
декодером: ``ImageFile.LOAD_TRUNCATED_IMAGES`` выключен, и Pillow честно падает
на неполных данных.

    check_product_images                 # только сводка
    check_product_images --list          # + пути и товары
    check_product_images --delete-broken # снять битые с витрины (спросит подтверждение)
"""

from __future__ import annotations

from django.core.exceptions import SuspiciousFileOperation
from django.core.management.base import BaseCommand

from apps.catalog.models import ProductImage


def _local_path(field_file):
    """Путь файла на диске; None — файла нет или storage не локальный."""
    try:
        return field_file.path
    except (ValueError, NotImplementedError, SuspiciousFileOperation):
        return None


def _probe(image_module, path) -> str:
    """``ok`` / ``missing`` / ``broken`` — декодером, а не по размеру файла."""
    try:
        with image_module.open(path) as img:
            img.load()  # verify() ловит не всё: обрезку видно только при чтении пикселей
    except FileNotFoundError:
        return "missing"
    except Exception:
        return "broken"
    return "ok"


class Command(BaseCommand):
    help = "Найти повреждённые и отсутствующие файлы фотографий товаров."

    def add_arguments(self, parser):
        parser.add_argument("--list", action="store_true", help="Показать каждый проблемный файл.")
        parser.add_argument(
            "--delete-broken",
            action="store_true",
            help="Удалить записи о битых файлах, чтобы карточка показывала «Фото готовится».",
        )

    def handle(self, *args, **options):
        try:
            from PIL import Image, ImageFile
        except ImportError:
            self.stderr.write("Нужен Pillow: pip install Pillow")
            return

        # Иначе Pillow молча дорисовывает обрезанные файлы, и проверка теряет смысл.
        ImageFile.LOAD_TRUNCATED_IMAGES = False

        broken: list[ProductImage] = []
        missing: list[ProductImage] = []
        # Витринные копии (ADR-0014) — отдельно: запись с целым оригиналом не удаляем,
        # битую копию пересоздаст обработка.
        display_broken: list[ProductImage] = []
        display_missing: list[ProductImage] = []
        total = 0

        for image in ProductImage.objects.select_related("product").iterator(chunk_size=200):
            total += 1
            path = _local_path(image.image)
            if path is not None:
                state = _probe(Image, path)
                if state == "missing":
                    missing.append(image)
                elif state == "broken":
                    broken.append(image)
            if image.display:
                display_path = _local_path(image.display)
                # копия с негодным путём — такая же поломка, как битый файл
                state = _probe(Image, display_path) if display_path else "broken"
                if state == "missing":
                    display_missing.append(image)
                elif state == "broken":
                    display_broken.append(image)

        if options["list"]:
            groups = (
                (broken, "ПОВРЕЖДЁН", "image"),
                (missing, "НЕТ ФАЙЛА", "image"),
                (display_broken, "КОПИЯ ПОВРЕЖДЕНА", "display"),
                (display_missing, "НЕТ КОПИИ", "display"),
            )
            for group, title, field in groups:
                for image in group:
                    name = getattr(image, field).name
                    self.stdout.write(f"  {title}  {name}  ← {image.product.name[:60]}")

        self.stdout.write("")
        self.stdout.write(f"Всего файлов:   {total}")
        self.stdout.write(f"Повреждённых:   {len(broken)}")
        self.stdout.write(f"Отсутствующих:  {len(missing)}")
        healthy = total - len(broken) - len(missing)
        self.stdout.write(self.style.SUCCESS(f"Целых:          {healthy}"))
        display_bad = len(display_broken) + len(display_missing)
        if display_bad:
            self.stdout.write(
                self.style.WARNING(
                    f"Витринных копий с проблемами: {display_bad} "
                    "(записи не удаляются — копию пересоздаст обработка)"
                )
            )

        if not options["delete_broken"]:
            if broken or missing:
                self.stdout.write(
                    "\nФайлы нужно перезалить. Снять битые с витрины: --delete-broken"
                )
            return

        if not (broken or missing):
            return
        answer = input(f"Удалить {len(broken) + len(missing)} записей о фото? [y/N] ")
        if answer.strip().lower() != "y":
            self.stdout.write("Отменено.")
            return
        ids = [i.pk for i in broken + missing]
        ProductImage.objects.filter(pk__in=ids).delete()
        self.stdout.write(self.style.SUCCESS(f"Удалено записей: {len(ids)}"))
