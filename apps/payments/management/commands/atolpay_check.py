"""Проверка настройки АТОЛ Pay: справочники чека и статус конкретного платежа.

Нужна на этапе подключения. Числовые коды ставки НДС и признаков предмета расчёта
в документации перечислены названиями, без номеров, — а от них зависит, какой чек
уйдёт в ФНС. Команда показывает то, что касса отдаёт на самом деле:

    python manage.py atolpay_check --dictionaries
    python manage.py atolpay_check --status P-20260907-ABC123
    python manage.py atolpay_check --receipt П-20260907-ABC123   # чек заказа, без отправки
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.orders.models import Order
from apps.payments.atolpay import service as atolpay
from apps.payments.atolpay.client import AtolPayError, dictionaries, payment_status
from apps.payments.atolpay.receipt import build_receipt


class Command(BaseCommand):
    help = "Диагностика подключения к АТОЛ Pay: справочники, статус платежа, состав чека."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dictionaries",
            action="store_true",
            help="Справочники чека (предметы расчёта, ставки НДС, единицы измерения).",
        )
        parser.add_argument("--status", metavar="ORDER_ID", help="Статус платежа по orderId кассы.")
        parser.add_argument(
            "--receipt",
            metavar="ORDER_NUMBER",
            help="Собрать чек заказа локально и показать его (в кассу ничего не уходит).",
        )

    def handle(self, *args, **options):
        if not any((options["dictionaries"], options["status"], options["receipt"])):
            raise CommandError("Укажите --dictionaries, --status или --receipt")

        if options["dictionaries"]:
            self._dump("Справочники", self._call(dictionaries))

        if options["status"]:
            order_id = options["status"]
            self._dump(f"Статус {order_id}", self._call(payment_status, order_id))

        if options["receipt"]:
            number = options["receipt"]
            order = Order.objects.filter(order_number=number).prefetch_related("items").first()
            if order is None:
                raise CommandError(f"Заказ {number} не найден")
            self.stdout.write(f"orderId для кассы: {atolpay.ascii_order_id(order.order_number)}")
            self._dump(f"Чек заказа {number}", build_receipt(order))

    def _call(self, func, *args):
        try:
            return func(*args)
        except AtolPayError as exc:
            raise CommandError(f"Касса ответила ошибкой: {exc.code} {exc.message}") from exc

    def _dump(self, title: str, payload) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING(title))
        self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
