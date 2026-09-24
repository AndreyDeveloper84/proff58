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
    check_product_images --main-conflicts  # read-only: товары с 0 или 2+ is_main

`--main-conflicts` — отдельная read-only диагностика (доработка контролёра
качества, §7 задания): в БД нет ограничения «один `is_main` на товар» (только
код держит инвариант при обычной работе), поэтому перед любой автоматической
нормализацией нужно сначала УВИДЕТЬ существующие конфликты, а не чинить их
миграцией наугад. Ничего не правит.
"""

from __future__ import annotations

from django.core.exceptions import SuspiciousFileOperation
from django.core.management.base import BaseCommand
from django.db.models import Count

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
        parser.add_argument(
            "--main-conflicts",
            action="store_true",
            help="Read-only: товары с 0 или 2+ is_main=True. Ничего не меняет.",
        )

    def handle(self, *args, **options):
        if options["main_conflicts"]:
            return self._main_conflicts()
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

    def _main_conflicts(self) -> None:
        """Read-only: товары, где `is_main` нарушает инвариант «ровно одно фото»."""
        from apps.catalog.models import Product

        main_counts = (
            ProductImage.objects.filter(is_main=True)
            .values("product_id")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
            .order_by("-n")
        )
        multiple = list(main_counts)
        no_main = (
            Product.objects.filter(images__isnull=False)
            .exclude(images__is_main=True)
            .values_list("pk", flat=True)
            .distinct()
            .order_by("pk")
        )
        no_main_ids = list(no_main)

        self.stdout.write("КОНФЛИКТЫ is_main (read-only, ничего не изменено)")
        self.stdout.write(f"  товаров с 2+ is_main: {len(multiple)}")
        for row in multiple[:20]:
            self.stdout.write(f"    товар #{row['product_id']}: {row['n']} главных фото")
        if len(multiple) > 20:
            self.stdout.write(f"    ... и ещё {len(multiple) - 20}")
        self.stdout.write(f"  товаров с фото, но без главного: {len(no_main_ids)}")
        if no_main_ids:
            self.stdout.write(f"    например: {', '.join(map(str, no_main_ids[:20]))}")
