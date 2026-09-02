"""Изображения из выгрузки парсера сайта производителя → каталог.

Вторая половина контура: `parser/` собрал карточки (`products.json`), эта
команда находит наши товары и заводит фотографии через `ImagePipeline`.

    # план (по умолчанию — ничего не пишет)
    catalog_images_import_scraped --export var/huter/products.json --source huter
    catalog_images_import_scraped --export … --source huter --out plan.json

    # запись
    catalog_images_import_scraped --export … --source huter --apply

Матчинг — **по артикулу, полным совпадением**. У Webasyst-источников JSON-LD
отдаёт `sku`, буквально равный нашему `Product.article`: на huter.su так
совпали 64 наших товара из 70. Матчинг по модели из названия (которым живёт
`scraped_import` для характеристик) здесь не нужен и был бы слабее — он даёт
похожесть, а не равенство, а фотография не тот случай, где похожести хватает.

Границы, каждая закреплена тестом:

* **dry-run по умолчанию** — без `--apply` в БД не появляется ничего;
* `manual` источником прогона быть не может: иначе откат прогона перестанет
  отличать спарсенное от загруженного руками;
* товар с `content_locked` не трогаем;
* совпадение только полное; подстрока (`70/6/2` ⊄ `70/6/25`) не считается;
* наш суффикс фасовки `_z01` снимается — у производителя его нет;
* если наш артикул носят два товара, карточка не привязывается ни к одному:
  выбирать за куратора команда не вправе;
* товар, у которого фото уже есть, пропускается (`--include-with-images`
  снимает это ограничение).

Повторный прогон дублей не плодит: идемпотентность по `(product, source_url)`
и `(product, checksum)` держит `ImagePipeline`, оба ключа подпёрты
ограничениями БД.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.image_pipeline import ImagePipeline
from apps.catalog.models import ImageSource, Product, ProductImage, ProductStatus

#: Наш внутренний суффикс фасовки. У производителя его нет.
#: В каталоге встречаются обе формы разделителя — `41189-z01` и `27361-10_z01`,
#: поэтому снимаем и дефис, и подчёркивание.
_PACK_SUFFIX_RE = re.compile(r"[-_]z\d+$", re.IGNORECASE)


def normalize_article(raw: str | None) -> str | None:
    """Артикул → ключ сравнения: регистр и пробелы снимаются, РАЗДЕЛИТЕЛИ НЕТ.

    Разделители обязаны сохраняться, и это доказано боевым прогоном 02.09.2026.
    Первая редакция сносила их «для надёжности» — и склеила разные артикулы:

        наш   70/13/3  →  70133
        huter 70/1/33  →  70133      ← тот же ключ

    В результате буру AG-150 записалась фотография аккумуляторного триммера
    GET-28Li; так пострадали четыре товара, прогон пришлось откатывать целиком.
    Сравнение полное, а не «по очищенной форме»: у номенклатуры разделитель
    несёт смысл, а не оформление.

    Тот же вывод уже зафиксирован в ВИ-сборщике
    (``connectors/sources/vseinstrumenti/normalizers.py``): «Разделители
    (``-``, ``/``, пробел) НЕ удаляются».
    """
    if not raw:
        return None
    value = _PACK_SUFFIX_RE.sub("", raw.strip())
    value = re.sub(r"\s+", "", value).casefold()
    return value or None


class Command(BaseCommand):
    help = "Изображения из выгрузки парсера производителя в каталог (dry-run по умолчанию)"

    def add_arguments(self, parser):
        parser.add_argument("--export", required=True,
                            help="products.json, собранный parser.main")
        parser.add_argument("--source", required=True,
                            choices=[s for s in ImageSource.values],
                            help="источник файлов; manual запрещён")
        parser.add_argument("--brand", help="ограничить наши товары брендом")
        parser.add_argument("--limit", type=int, help="взять не больше N совпадений")
        parser.add_argument("--apply", action="store_true",
                            help="писать в БД (без флага — только план)")
        parser.add_argument("--include-with-images", action="store_true",
                            help="не пропускать товары, у которых фото уже есть")
        parser.add_argument("--out", help="файл для машиночитаемого отчёта")

    def handle(self, *args, **opts):
        source = opts["source"]
        if source == ImageSource.MANUAL:
            raise CommandError(
                "source=manual запрещён: прогон обязан быть отличим от ручной "
                "загрузки, иначе его нельзя откатить, не задев чужое"
            )

        export_path = Path(opts["export"])
        if not export_path.exists():
            raise CommandError(f"выгрузка не найдена: {export_path}")
        payload = json.loads(export_path.read_text(encoding="utf-8"))
        cards = payload.get("products", payload if isinstance(payload, list) else [])

        report = self._plan(cards, source=source, brand=opts.get("brand"),
                            include_with_images=opts["include_with_images"],
                            limit=opts.get("limit"))

        if opts["apply"]:
            self._apply(report, source=source)

        report["applied"] = bool(opts["apply"])
        self._print(report)
        if opts.get("out"):
            Path(opts["out"]).write_text(
                json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        return None

    # --- план ------------------------------------------------------------- #

    def _plan(self, cards, *, source, brand, include_with_images, limit):
        products = Product.objects.filter(status=ProductStatus.PUBLISHED, is_active=True)
        if brand:
            products = products.filter(brand=brand)

        # индекс наших товаров по ключу артикула; коллизии оставляем видимыми,
        # чтобы неоднозначность стала отказом, а не молчаливым выбором первого
        by_key: dict[str, list[Product]] = defaultdict(list)
        for product in products.only("id", "article", "name", "content_locked"):
            key = normalize_article(product.article)
            if key:
                by_key[key].append(product)

        with_images = set(
            ProductImage.objects.values_list("product_id", flat=True).distinct()
        )

        matched: list[dict] = []
        counters = {"cards_total": len(cards), "cards_without_images": 0,
                    "cards_without_sku": 0, "unmatched_cards": 0,
                    "ambiguous": 0, "locked": 0, "already_has_images": 0}

        for card in cards:
            images = [i for i in (card.get("images") or []) if i.get("url")]
            if not images:
                counters["cards_without_images"] += 1
                continue
            key = normalize_article(card.get("manufacturer_sku"))
            if not key:
                counters["cards_without_sku"] += 1
                continue
            candidates = by_key.get(key) or []
            if not candidates:
                counters["unmatched_cards"] += 1
                continue
            if len(candidates) > 1:
                # выбирать за куратора команда не вправе
                counters["ambiguous"] += 1
                continue
            product = candidates[0]
            if product.content_locked:
                counters["locked"] += 1
                continue
            if product.id in with_images and not include_with_images:
                counters["already_has_images"] += 1
                continue
            matched.append({
                "product_id": product.id,
                "our_article": product.article,
                "our_name": product.name,
                "source_sku": card.get("manufacturer_sku"),
                "source_name": card.get("name"),
                "source_url": card.get("source_url"),
                "images": [i["url"] for i in images],
                "source": source,
            })
            if limit and len(matched) >= limit:
                break

        # Один товар не может забрать две карточки. Так проявился дефект
        # склейки артикулов 02.09.2026: товар попадал в план дважды и получал
        # два РАЗНЫХ фото. Даже когда обе карточки формально совпали, выбирать
        # верную должен куратор, а не команда.
        seen = Counter(m["product_id"] for m in matched)
        duplicates = {pid for pid, n in seen.items() if n > 1}
        if duplicates:
            counters["duplicate_cards"] = len(duplicates)
            matched = [m for m in matched if m["product_id"] not in duplicates]
        else:
            counters["duplicate_cards"] = 0

        return {"kind": "images_import_plan", "source": source,
                "matched": matched, "images_total": sum(len(m["images"]) for m in matched),
                **counters}

    # --- запись ------------------------------------------------------------ #

    def _apply(self, report, *, source):
        pipeline = ImagePipeline()
        created = failed = 0
        for item in report["matched"]:
            product = Product.objects.filter(pk=item["product_id"]).first()
            if product is None:  # товар исчез между планом и записью
                failed += 1
                continue
            saved = []
            for position, url in enumerate(item["images"]):
                image = pipeline.process_url(
                    product, url, is_main=(position == 0), source=source,
                )
                if image is not None:
                    saved.append(image.id)
            item["created_image_ids"] = saved
            created += len(saved)
            if not saved:
                failed += 1
        report["images_created"] = created
        report["products_without_result"] = failed

    # --- вывод ------------------------------------------------------------- #

    def _print(self, report):
        write = self.stdout.write
        head = "ЗАПИСЬ" if report["applied"] else "ПЛАН (dry-run, в БД ничего не пишется)"
        write(f"=== {head} · источник {report['source']} ===")
        write(f"  карточек в выгрузке:        {report['cards_total']}")
        write(f"  совпало с нашими товарами:  {len(report['matched'])}")
        write(f"  изображений к загрузке:     {report['images_total']}")
        write("  пропущено:")
        write(f"    карточка без изображений: {report['cards_without_images']}")
        write(f"    карточка без sku:         {report['cards_without_sku']}")
        write(f"    наш товар не найден:      {report['unmatched_cards']}")
        write(f"    артикул неоднозначен:     {report['ambiguous']}")
        write(f"    товар с content_locked:   {report['locked']}")
        write(f"    фото уже есть:            {report['already_has_images']}")
        write(f"    две карточки на товар:    {report.get('duplicate_cards', 0)}")
        if report["applied"]:
            write(f"  СОЗДАНО изображений:        {report['images_created']}")
            write(f"  товаров без результата:     {report['products_without_result']}")
        for item in report["matched"][:20]:
            write("    %-8s %-14s %s" % (item["product_id"], item["our_article"],
                                         item["our_name"][:52]))
