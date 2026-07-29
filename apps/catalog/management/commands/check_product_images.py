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

from django.core.management.base import BaseCommand

from apps.catalog.models import ProductImage


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
        total = 0

        for image in ProductImage.objects.select_related("product").iterator(chunk_size=200):
            total += 1
            try:
                path = image.image.path
            except (ValueError, NotImplementedError):
                continue
            try:
                with Image.open(path) as img:
                    img.load()  # verify() ловит не всё: обрезку видно только при чтении пикселей
            except FileNotFoundError:
                missing.append(image)
            except Exception:
                broken.append(image)

        if options["list"]:
            for group, title in ((broken, "ПОВРЕЖДЁН"), (missing, "НЕТ ФАЙЛА")):
                for image in group:
                    self.stdout.write(f"  {title}  {image.image.name}  ← {image.product.name[:60]}")

        self.stdout.write("")
        self.stdout.write(f"Всего файлов:   {total}")
        self.stdout.write(f"Повреждённых:   {len(broken)}")
        self.stdout.write(f"Отсутствующих:  {len(missing)}")
        healthy = total - len(broken) - len(missing)
        self.stdout.write(self.style.SUCCESS(f"Целых:          {healthy}"))

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
