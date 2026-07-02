# apps/catalog/image_pipeline.py
"""Минимальный pipeline изображений: скачать → валидировать → ресайз → WebP → thumb.

Вызывается вручную (admin/CLI). Enrich-поток фото не тянет. Идемпотентность —
по URL (хранится в alt-маркере). content_locked уважается.

Безопасность (M-13): только https; хост обязан резолвиться в публичный IP
(защита от SSRF во внутреннюю сеть); redirects запрещены; тело качается стримом
с жёстким лимитом MAX_BYTES; Pillow ограничен по числу пикселей (decompression bomb).
"""
from __future__ import annotations

import io
import ipaddress
import logging
import socket
from urllib.parse import urlparse

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
    MAX_PIXELS = 40_000_000  # ~40 Мп — потолок против decompression bomb
    _CHUNK = 64 * 1024

    def _host_is_public(self, host: str) -> bool:
        """True только если ВСЕ адреса хоста публичные (не private/loopback/link-local/…)."""
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror:
            return False
        if not infos:
            return False
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                return False
        return True

    def _download(self, url: str) -> bytes | None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            log.warning("image url отклонён (не https/без host): %s", url)
            return None
        if not self._host_is_public(parsed.hostname):
            log.warning("image url отклонён (private/непубличный host): %s", url)
            return None
        try:
            resp = requests.get(url, timeout=self.TIMEOUT, stream=True, allow_redirects=False)
            try:
                if resp.status_code != 200:  # redirects запрещены → 3xx трактуем как отказ
                    return None
                clen = resp.headers.get("Content-Length")
                if clen is not None:
                    try:
                        if int(clen) > self.MAX_BYTES:
                            return None
                    except ValueError:
                        pass
                buf = bytearray()
                for chunk in resp.iter_content(self._CHUNK):
                    buf += chunk
                    if (
                        len(buf) > self.MAX_BYTES
                    ):  # hard cap: Content-Length может врать/отсутствовать
                        return None
                return bytes(buf)
            finally:
                resp.close()
        except requests.RequestException as exc:
            log.warning("image download failed %s: %s", url, exc)
            return None

    def _process_bytes(self, raw: bytes):
        try:
            img = Image.open(io.BytesIO(raw))
            if img.size[0] * img.size[1] > self.MAX_PIXELS:  # decompression bomb
                return None
            img.load()
        except (OSError, ValueError, Image.DecompressionBombError):
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
