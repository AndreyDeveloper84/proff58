"""Рендерер ответов для 1С 7.7 — в кодировке Windows-1251.

1С 7.7 читает HTTP-ответы как **cp1251**, а DRF по умолчанию отдаёт JSON в
UTF-8 → кириллица в ответах (тексты ошибок, detail) приходит «кракозябрами».
Отдаём тело в cp1251 и проставляем ``charset=windows-1251`` в ``Content-Type``.

Симметрично приёму (``OneCJSONParser``): на входе декодируем cp1251, на выходе
кодируем cp1251.
"""

from __future__ import annotations

from rest_framework.renderers import JSONRenderer


class OneCJSONRenderer(JSONRenderer):
    """JSON в Windows-1251 для обмена с 1С 7.7."""

    charset = "windows-1251"
    # Кириллицу пишем как есть (не \uXXXX), чтобы 1С прочитала её как cp1251-текст.
    ensure_ascii = False

    def render(self, data, accepted_media_type=None, renderer_context=None):
        rendered = super().render(data, accepted_media_type, renderer_context)
        text = rendered.decode("utf-8") if isinstance(rendered, bytes | bytearray) else rendered
        # backslashreplace — чтобы не падать на редком символе вне cp1251 (эмодзи и т.п.).
        return text.encode("windows-1251", errors="backslashreplace")
