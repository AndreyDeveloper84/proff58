# apps/catalog/image_pipeline.py
"""Минимальный pipeline изображений: скачать → валидировать → ресайз → WebP → thumb.

Вызывается вручную (admin/CLI). Enrich-поток фото не тянет. Идемпотентность —
по URL (хранится в alt-маркере). content_locked уважается.

Безопасность (M-13): только https и порт 443; хост обязан резолвиться в публичный
IP (защита от SSRF во внутреннюю сеть); соединение пиннится к уже проверенному IP
(без повторного DNS — защита от DNS-rebinding/TOCTOU), с проверкой TLS по имени
хоста; redirects запрещены; тело качается с жёстким лимитом MAX_BYTES; Pillow
ограничен по числу пикселей (decompression bomb).
"""
from __future__ import annotations

import io
import ipaddress
import logging
import socket
from urllib.parse import urlparse

import certifi
import urllib3
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

    @staticmethod
    def _ip_is_public(ip_str: str) -> bool:
        ip = ipaddress.ip_address(ip_str)
        return not (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        )

    def _resolve_public_ips(self, host: str) -> list[str] | None:
        """Все адреса хоста; None — если резолв не удался или ЛЮБОЙ адрес непубличный.

        Возвращаем именно проверенный список, чтобы соединяться с одним из этих IP
        (без повторного DNS-резолва requests) — иначе возможен DNS-rebinding: проверка
        видит публичный адрес, а connect уходит на приватный (169.254.169.254 и т.п.).
        """
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror:
            return None
        ips = [info[4][0] for info in infos]
        if not ips or any(not self._ip_is_public(ip) for ip in ips):
            return None
        return ips

    def _host_is_public(self, host: str) -> bool:
        return self._resolve_public_ips(host) is not None

    def _download(self, url: str) -> bytes | None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            log.warning("image url отклонён (не https/без host): %s", url)
            return None
        if parsed.port not in (None, 443):  # M-13: только стандартный https-порт
            log.warning("image url отклонён (нестандартный порт): %s", url)
            return None
        ips = self._resolve_public_ips(parsed.hostname)
        if not ips:
            log.warning("image url отклонён (private/непубличный host): %s", url)
            return None

        # Пиннимся к проверенному IP (без повторного DNS), TLS проверяем по имени хоста.
        pool = urllib3.HTTPSConnectionPool(
            ips[0],
            port=443,
            timeout=urllib3.Timeout(connect=self.TIMEOUT, read=self.TIMEOUT),
            retries=False,
            cert_reqs="CERT_REQUIRED",
            ca_certs=certifi.where(),
            server_hostname=parsed.hostname,
            assert_hostname=parsed.hostname,
        )
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        try:
            resp = pool.urlopen(
                "GET",
                target,
                headers={"Host": parsed.hostname},
                redirect=False,  # redirects запрещены
                preload_content=False,
                decode_content=False,
            )
            try:
                if resp.status != 200:  # 3xx (redirect) и прочее → отказ
                    return None
                clen = resp.headers.get("Content-Length")
                if clen is not None:
                    try:
                        if int(clen) > self.MAX_BYTES:
                            return None
                    except ValueError:
                        pass
                # hard cap: читаем не больше MAX_BYTES+1, чтобы поймать враньё/отсутствие Content-Length
                data = resp.read(self.MAX_BYTES + 1)
                if len(data) > self.MAX_BYTES:
                    return None
                return data
            finally:
                resp.release_conn()
        except (urllib3.exceptions.HTTPError, OSError) as exc:
            log.warning("image download failed %s: %s", url, exc)
            return None
        finally:
            pool.close()

    def _process_bytes(self, raw: bytes):
        # Backstop против decompression bomb: Pillow сам бросит DecompressionBombError
        # при декодировании сверх лимита (не только по заявленному размеру в заголовке).
        Image.MAX_IMAGE_PIXELS = self.MAX_PIXELS
        try:
            img = Image.open(io.BytesIO(raw))
            if img.size[0] * img.size[1] > self.MAX_PIXELS:  # decompression bomb (по заголовку)
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
