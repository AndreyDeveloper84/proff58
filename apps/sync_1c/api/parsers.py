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
    # Жёсткий лимит размера тела (~10 MB). Защита от дешёвого OOM-DoS:
    # stream.read() буферизует весь запрос в памяти (#282).
    MAX_BODY_BYTES = 10 * 1024 * 1024

    def parse(self, stream, media_type=None, parser_context=None):
        raw = stream.read(self.MAX_BODY_BYTES + 1)
        if len(raw) > self.MAX_BODY_BYTES:
            raise ParseError(f"Тело запроса превышает {self.MAX_BODY_BYTES // (1024 * 1024)} МБ.")
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
        # Кодировка не определена — возвращаем 400 вместо тихой замены (#282).
        raise ParseError("Не удалось декодировать тело запроса: неизвестная кодировка.")
