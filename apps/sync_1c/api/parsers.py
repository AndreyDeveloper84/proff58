"""Парсер тела запроса для 1С 7.7 — устойчивый к кодировке.

1С 7.7 выгружает данные в **Windows-1251** и часто шлёт тело без корректного
``charset`` в ``Content-Type`` (исправить на стороне 1С нельзя). DRF по умолчанию
декодирует JSON как UTF-8 → на кириллице получаем ``400`` (UnicodeDecodeError)
или «кракозябры». Поэтому читаем сырые байты и подбираем кодировку сами:
сначала UTF-8 (новые/корректные клиенты), затем CP1251 (1С 7.7).

Порядок кодировок совпадает с файловым импортом (``apps.sync_1c.parsers._decode``).
"""

from __future__ import annotations

import json

from rest_framework.exceptions import ParseError
from rest_framework.parsers import BaseParser

# UTF-8 проверяем первым: валидный UTF-8 почти никогда не является валидным
# CP1251-текстом по ошибке, а кириллица CP1251 (одиночные байты 0xC0–0xFF) как
# UTF-8 обычно не декодируется — значит честно уходим в cp1251.
_ENCODINGS = ("utf-8-sig", "cp1251")


class OneCJSONParser(BaseParser):
    """JSON от 1С в любой кодировке (UTF-8 или Windows-1251).

    Принимает тело независимо от заявленного ``charset`` — кодировку определяем
    по содержимому. ``media_type='*/*'`` — 1С 7.7 не всегда корректно проставляет
    ``Content-Type``, поэтому не привязываемся к нему (эндпоинты и так закрыты
    ключом ``X-Api-Key`` и используются только обменом с 1С).
    """

    media_type = "*/*"

    def parse(self, stream, media_type=None, parser_context=None):
        raw = stream.read()
        if not raw:
            return {}
        text = self.decode(raw)
        try:
            return json.loads(text)
        except ValueError as exc:
            raise ParseError(f"Некорректный JSON в теле запроса: {exc}") from exc

    @staticmethod
    def decode(raw: bytes) -> str:
        for enc in _ENCODINGS:
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        # Последний шанс — не падать на одной битой строке.
        return raw.decode("utf-8", errors="replace")
