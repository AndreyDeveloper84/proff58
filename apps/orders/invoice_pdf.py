"""PDF-счёт из HTML-шаблона (WeasyPrint).

HTML остаётся единственным источником вёрстки (`orders/invoice.html`); здесь только
конвертация. Импорт WeasyPrint ленивый: системные библиотеки pango есть в образе web
(Dockerfile), но локальные окружения без них не должны падать на импорте модуля.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class InvoicePdfError(RuntimeError):
    """PDF не собрался — отдавать HTML вместо документа нельзя, это ошибка сервера."""


def _deny_fetch(url: str, *args, **kwargs):
    raise InvoicePdfError(f"Внешние ресурсы в счёте запрещены: {url[:80]}")


def render_invoice_pdf(html: str) -> bytes:
    try:
        from weasyprint import HTML
    except ImportError as exc:  # pragma: no cover — окружение без pango/weasyprint
        raise InvoicePdfError("WeasyPrint не установлен") from exc
    try:
        # В шаблоне нет внешних ресурсов; любую попытку их загрузить (картинка в
        # пользовательском поле, будущая правка шаблона) отбиваем — генератор PDF
        # не должен ходить в сеть.
        return HTML(string=html, base_url=None, url_fetcher=_deny_fetch).write_pdf()
    except Exception as exc:  # noqa: BLE001 — любая ошибка рендера = ошибка документа
        logger.exception("Не удалось собрать PDF-счёт")
        raise InvoicePdfError(str(exc)) from exc
