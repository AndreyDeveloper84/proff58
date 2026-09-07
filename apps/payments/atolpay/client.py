"""HTTP-клиент АТОЛ Pay Ecom.

Отличия от ЮKassa, из-за которых нужен отдельный клиент:

- авторизация — голый токен в ``Authorization`` (без ``Bearer``/``Basic``);
- все суммы в **копейках** (целые), количество — в тысячных долях;
- заголовка идемпотентности нет вовсе: повтор гасится уникальностью ``orderId``
  (касса отвечает ``PAYMENT_EXISTS``);
- ответ приходит в двух формах — плоской (``{"orderId": ..., "paymentUrl": ...}``)
  и в конверте (``{"status": "success", "data": {...}}``). Документация показывает
  обе, поэтому распаковываем любую;
- ошибка может приехать с кодом 200 и телом ``{"status": "error", ...}``.

Ошибки нормализуются в :class:`AtolPayError` — вызывающий смотрит на ``code``
(``PAYMENT_EXISTS``, ``AUTH_ERROR``, ``INVALID_RECEIPT_AMOUNT``, …), а не парсит текст.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from decimal import ROUND_HALF_UP, Decimal
from urllib.error import HTTPError, URLError

from django.conf import settings

logger = logging.getLogger(__name__)


class AtolPayError(RuntimeError):
    """Ошибка кассы: код и сообщение АТОЛ, http-статус (0 — сетевой сбой)."""

    def __init__(self, code: str = "", message: str = "", http_status: int = 0):
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(f"АТОЛ Pay: {code or http_status or 'network'} {message}".strip())


def to_kopecks(amount: Decimal | str | int | float) -> int:
    """Рубли → копейки. Округление банковское не годится: чек считается по копейке."""
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def to_thousandths(quantity: int | Decimal) -> int:
    """Количество → тысячные доли (1 шт = 1000)."""
    return int((Decimal(str(quantity)) * 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _base_url() -> str:
    return getattr(settings, "ATOLPAY_BASE_URL", "").rstrip("/")


def _unwrap(payload: dict) -> dict:
    """Достать полезную часть ответа и превратить ``status: error`` в исключение."""
    if not isinstance(payload, dict):
        raise AtolPayError(message="неожиданный формат ответа")
    if payload.get("status") == "error":
        raise AtolPayError(
            code=str(payload.get("errorCode", "")),
            message=str(payload.get("errorMessage", "")),
        )
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return payload


def request(method: str, path: str, body: dict | None = None) -> dict:
    """Запрос к API АТОЛ Pay. Бросает :class:`AtolPayError` на любой сбой."""
    token = getattr(settings, "ATOLPAY_TOKEN", "")
    if not token or not _base_url():
        raise AtolPayError(
            code="NOT_CONFIGURED", message="ATOLPAY_TOKEN/ATOLPAY_BASE_URL не заданы"
        )

    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(
        f"{_base_url()}/{path.lstrip('/')}",
        data=data,
        headers={"Authorization": token, "Content-Type": "application/json"},
        method=method,
    )

    timeout = getattr(settings, "ATOLPAY_TIMEOUT", 15)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = {}
        # Ошибку кассы логируем кодом, а не телом: в теле бывают данные заказа.
        code = str(parsed.get("errorCode", ""))
        logger.error("АТОЛ Pay %s /%s → HTTP %s (%s)", method, path, exc.code, code or "-")
        raise AtolPayError(
            code=code,
            message=str(parsed.get("errorMessage", "")),
            http_status=exc.code,
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        logger.error("АТОЛ Pay %s /%s → сеть недоступна: %s", method, path, exc)
        raise AtolPayError(code="NETWORK_ERROR", message=str(exc)) from exc

    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise AtolPayError(message="ответ не является JSON") from exc

    return _unwrap(payload)


def register_payment(body: dict) -> dict:
    """POST /payments — регистрация платежа. Возвращает orderId/amount/paymentUrl."""
    return request("POST", "payments", body)


def payment_status(order_id: str) -> dict:
    """GET /payments/{orderId}/status — числовой статус платежа (авторитетный)."""
    return request("GET", f"payments/{order_id}/status")


def cancel_payment(order_id: str, amount_kopecks: int | None = None) -> dict:
    """POST /payments/{orderId}/cancel — отмена или возврат (решает сама касса).

    Без суммы — на всю сумму заказа. Частичная отмена доступна не у всех банков
    (у Альфы её нет — там всегда частичный возврат), для нас разница только в
    комиссии, ветка обработки одна.
    """
    body: dict = {}
    if amount_kopecks is not None:
        body["amount"] = amount_kopecks
    return request("POST", f"payments/{order_id}/cancel", body)


def dictionaries() -> dict:
    """GET /receipts/dictionaries — справочники чека (предметы расчёта, ставки НДС)."""
    return request("GET", "receipts/dictionaries")
