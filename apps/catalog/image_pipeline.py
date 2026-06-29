# apps/catalog/image_pipeline.py
"""Минимальный pipeline изображений: скачать → валидировать → ресайз → WebP → thumb.

Вызывается вручную (admin/CLI). Enrich-поток фото не тянет. Идемпотентность —
по URL (хранится в alt-маркере). content_locked уважается.
"""
from __future__ import annotations

import io
import logging

import requests
from django.core.files.base import ContentFile
from PIL import Image, ImageOps

from .models import Product, ProductImage

log = logging.getLogger(__name__)


class ImagePipeline:
    MAX_SIZE = (1200, 1200)
    THUMB_SIZE = (400, 400)
    QUALITY = 85
    TIMEOUT = 10
    MIN_SIDE = 100
    MAX_BYTES = 10 * 1024 * 1024

    def _download(self, url: str) -> bytes | None:
        try:
            r = requests.get(url, timeout=self.TIMEOUT)
            r.raise_for_status()
        except requests.RequestException as exc:
            log.warning("image download failed %s: %s", url, exc)
            return None
        return r.content if len(r.content) <= self.MAX_BYTES else None

    def _process_bytes(self, raw: bytes):
        try:
            img = Image.open(io.BytesIO(raw))
            img.load()
        except (OSError, ValueError):
            return None
        if min(img.size) < self.MIN_SIDE:
            return None
        img = ImageOps.exif_transpose(img).convert("RGB")  # снимаем EXIF

        main_img = img.copy()
        main_img.thumbnail(self.MAX_SIZE)
        main_buf = io.BytesIO()
        main_img.save(main_buf, format="WEBP", quality=self.QUALITY)

        thumb_img = img.copy()
        thumb_img.thumbnail(self.THUMB_SIZE)
        thumb_buf = io.BytesIO()
        thumb_img.save(thumb_buf, format="WEBP", quality=self.QUALITY)
        return ContentFile(main_buf.getvalue()), ContentFile(thumb_buf.getvalue())

    def process_url(
        self, product: Product, url: str, *, is_main: bool = False, source: str = "manual"
    ) -> ProductImage | None:
        if product.content_locked:
            return None
        existing = product.images.filter(alt=url).first()  # идемпотентность по URL
        if existing is not None:
            return existing
        raw = self._download(url)
        if raw is None:
            return None
        processed = self._process_bytes(raw)
        if processed is None:
            return None
        main_file, _thumb = processed
        first = not product.images.exists()
        image = ProductImage(product=product, alt=url, is_main=is_main or first)
        image.image.save(
            f"products/{product.pk}/{abs(hash(url)) % 10**8}.webp", main_file, save=True
        )
        return image

    def process_batch(self, product: Product, urls: list[str]) -> list[ProductImage]:
        out: list[ProductImage] = []
        for i, url in enumerate(urls):
            img = self.process_url(product, url, is_main=(i == 0))
            if img is not None:
                out.append(img)
        return out
