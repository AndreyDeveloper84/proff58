"""Демо/симулятор обмена заказами с 1С (#50) — полный round-trip без реальной 1С.

Команда играет роль «1С» и прогоняет весь цикл обмена заказами по контракту
``docs/1c-api-spec.md`` §5.6 на реальных моделях и use-case'ах сайта:

  1. создаёт демо-заказ в статусе ``sync_1c_status=pending`` (как после оформления);
  2. ``export_new_orders`` — то, что 1С получит из ``GET /api/1c/orders/new``;
  3. ``confirm_orders`` — то, что 1С пришлёт в ``POST /api/1c/orders/confirm``
     (подтверждение приёма + резерв + движение ``fulfillment_status``);
  4. печатает JSON обмена и итоговые статусы заказа по трём осям.

Это и проверка работоспособности эндпоинтов заказов на живых данных, и наглядный
«мок 1С» для отладки интеграции, пока со стороны 1С обработка ещё пишется.

Запуск (нужен доступный Postgres; задачи Celery не требуются — операции синхронные):

    python manage.py demo_1c_orders                 # confirmed + успешный резерв
    python manage.py demo_1c_orders --scenario reserve-failed
    python manage.py demo_1c_orders --scenario shipped
    python manage.py demo_1c_orders --keep          # не удалять демо-заказ

По умолчанию демо-заказ удаляется в конце (--keep оставляет его в БД).
"""

from __future__ import annotations

import json
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.orders.models import FulfillmentStatus, Order, OrderItem
from apps.sync_1c import use_cases

_DEMO_ONEC_ID = "1c-order-DEMO"
_DEMO_ONEC_NUMBER = "УТ-DEMO-0001"


def _build_demo_order() -> Order:
    """Создать демо-заказ с одной строкой-снимком (как после checkout'а)."""
    number = f"P-DEMO-{timezone.now():%Y%m%d-%H%M%S}"
    order = Order.objects.create(
        order_number=number,
        customer_name="Демо Покупатель",
        customer_phone="+79000000000",
        customer_email="demo@example.com",
        delivery_method="delivery",
        delivery_address="Пенза, ул. Московская, 1",
        comment="Демо-заказ симулятора 1С",
        payment_method="online",
        total=Decimal("5900.00"),
        currency="RUB",
    )
    OrderItem.objects.create(
        order=order,
        code_1c="1c-000123",
        article="BOSCH-GSB13RE",
        name="Дрель ударная BOSCH GSB 13 RE",
        unit="шт",
        price_final=Decimal("5900.00"),
        quantity=1,
        line_total=Decimal("5900.00"),
        currency="RUB",
    )
    return order


def _confirm_steps(order: Order, scenario: str) -> list[dict]:
    """Список строк подтверждения, как их слала бы 1С (§5.6).

    Несколько шагов = несколько последовательных вызовов ``POST /orders/confirm``
    во времени (1С двигает ось обработки тем же эндпоинтом). Статус заказа
    forward-only по матрице ``orders.transitions`` (new→confirmed→ready→shipped…).
    """
    base = {
        "site_order_id": order.id,
        "order_number": order.order_number,
        "onec_order_id": _DEMO_ONEC_ID,
        "onec_order_number": _DEMO_ONEC_NUMBER,
    }
    ok_reserve = {"ok": True, "reserved_until": "2026-06-17T10:30:00+03:00"}

    if scenario == "reserve-failed":
        # Провал резерва: приём подтверждён (sync-ack), но fulfillment остаётся new.
        return [
            {
                **base,
                "fulfillment_status": "new",
                "reserve": {
                    "ok": False,
                    "lines": [
                        {
                            "external_id": "1c-000123",
                            "requested": "3.000",
                            "available": "1.000",
                            "error": "Недостаточно остатка",
                        }
                    ],
                },
                "comment": "Недостаточно товара на складе",
            }
        ]
    if scenario == "shipped":
        # Реалистичная цепочка: принят → готов → передан в доставку (3 вызова).
        return [
            {**base, "fulfillment_status": "confirmed", "reserve": ok_reserve},
            {**base, "fulfillment_status": "ready", "comment": "Собран"},
            {
                **base,
                "fulfillment_status": "shipped",
                "tracking": "PEK-DEMO-123456",
                "comment": "Передан в доставку",
            },
        ]
    # confirmed (по умолчанию): принят и зарезервирован.
    return [
        {
            **base,
            "fulfillment_status": "confirmed",
            "reserve": ok_reserve,
            "comment": "Заказ принят и зарезервирован",
        }
    ]


def _dump(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


class Command(BaseCommand):
    help = "Демо полного round-trip обмена заказами с 1С (#50): export → confirm."

    def add_arguments(self, parser):
        parser.add_argument(
            "--scenario",
            choices=("confirmed", "reserve-failed", "shipped"),
            default="confirmed",
            help="Сценарий ответа 1С (по умолч. confirmed).",
        )
        parser.add_argument(
            "--keep",
            action="store_true",
            help="Не удалять демо-заказ после прогона (по умолч. удаляется).",
        )

    def handle(self, *args, **opts):
        scenario = opts["scenario"]
        order = _build_demo_order()
        self.stdout.write(
            self.style.SUCCESS(f"Создан демо-заказ #{order.id} ({order.order_number}).")
        )

        # Шаг 1. GET /orders/new — что 1С получит на запрос новых заказов.
        _log, exported = use_cases.export_new_orders()
        mine = [it for it in exported if it["site_order_id"] == order.id]
        self.stdout.write("\n=== 1С → GET /api/1c/orders/new (ответ сайта) ===")
        self.stdout.write(_dump({"items": mine}))

        # Шаг 2. POST /orders/confirm — что 1С пришлёт обратно (один или несколько вызовов).
        steps = _confirm_steps(order, scenario)
        for n, confirm_item in enumerate(steps, start=1):
            label = f" (вызов {n}/{len(steps)})" if len(steps) > 1 else ""
            self.stdout.write(
                f"\n=== 1С → POST /api/1c/orders/confirm{label} (сценарий: {scenario}) ==="
            )
            self.stdout.write(_dump({"items": [confirm_item]}))
            _log2, results = use_cases.confirm_orders([confirm_item])
            self.stdout.write("--- Ответ сайта на confirm ---")
            self.stdout.write(_dump({"items": results}))

        # Шаг 3. Итоговое состояние заказа по трём осям.
        order.refresh_from_db()
        self.stdout.write("\n=== Итоговые статусы заказа (3 оси) ===")
        self.stdout.write(
            _dump(
                {
                    "fulfillment_status": order.fulfillment_status,
                    "payment_status": order.payment_status,
                    "sync_1c_status": order.sync_1c_status,
                    "external_order_id": order.external_order_id,
                    "external_order_number": order.external_order_number,
                    "tracking_number": order.tracking_number,
                    "exported_at": order.exported_at,
                    "reserved_until": order.reserved_until,
                    "display_status": order.display_status,
                }
            )
        )

        expected = {
            "confirmed": FulfillmentStatus.CONFIRMED,
            "reserve-failed": FulfillmentStatus.NEW,
            "shipped": FulfillmentStatus.SHIPPED,
        }[scenario]
        ok = order.fulfillment_status == expected
        msg = (
            f"OK: обработка → {order.fulfillment_status}, выгрузка → {order.sync_1c_status}."
            if ok
            else f"ВНИМАНИЕ: ожидался fulfillment={expected}, получено {order.fulfillment_status}."
        )
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(msg) if ok else self.style.ERROR(msg))

        order_id = order.id
        if opts["keep"]:
            self.stdout.write(self.style.WARNING(f"Демо-заказ #{order_id} оставлен (--keep)."))
        else:
            order.delete()
            self.stdout.write(self.style.WARNING(f"Демо-заказ #{order_id} удалён."))
