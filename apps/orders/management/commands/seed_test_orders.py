"""Сидер тестовых заказов для приёмки обмена с 1С (#50).

Создаёт в БД разнообразные заказы в статусе «новый, не выгружен»
(`fulfillment_status=new`, `sync_1c_status=pending`) — именно такие отдаёт
`GET /api/1c/orders/new`. Нужны, чтобы разработчик 1С мог тестировать свою
сторону обмена на реальных данных:

  1. забрать заказы — `GET /api/1c/orders/new`;
  2. подтвердить приём/резерв и двигать статус — `POST /api/1c/orders/confirm`;
  3. наблюдать заказы и смену осей статусов в админке `/admin/orders/order/`.

Строки заказа по возможности берут **реальные `code_1c`** из каталога (чтобы 1С
смогла сопоставить и зарезервировать товар); если каталог пуст — подставляются
демонстрационные коды.

Запуск (нужен доступный Postgres):

    python manage.py seed_test_orders                 # создать 5 заказов
    python manage.py seed_test_orders --count 10      # создать 10
    python manage.py seed_test_orders --reset         # удалить прежние TEST-1C-* и создать заново
    python manage.py seed_test_orders --reset --count 0   # только удалить тестовые заказы

Заказы помечены номером с префиксом ``TEST-1C-`` — так их легко найти в админке
и безопасно удалить через ``--reset`` (реальные заказы не затрагиваются).
"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import CustomerType
from apps.catalog.models import Product
from apps.orders.models import (
    FulfillmentStatus,
    Order,
    OrderItem,
    PaymentStatus,
    Sync1CStatus,
)

TEST_PREFIX = "TEST-1C-"

# Демо-строки на случай пустого каталога (коды условные — 1С сопоставит свои).
_FALLBACK_LINES = [
    {
        "code_1c": "1c-000123",
        "article": "BOSCH-GSB13RE",
        "name": "Дрель ударная BOSCH GSB 13 RE",
        "unit": "шт",
        "price": Decimal("5900.00"),
    },
    {
        "code_1c": "1c-000456",
        "article": "MAKITA-HR2470",
        "name": "Перфоратор Makita HR2470",
        "unit": "шт",
        "price": Decimal("8990.00"),
    },
    {
        "code_1c": "1c-000789",
        "article": "DEWALT-DCD791",
        "name": "Дрель-шуруповёрт DeWALT DCD791",
        "unit": "шт",
        "price": Decimal("12500.00"),
    },
]

# Шаблоны заказов (по кругу). Все проходят фильтр export_new_orders:
# sync_1c_status=pending, fulfillment=new, не cancelled, не payment=expired.
_SCENARIOS = [
    {
        "label": "B2C, онлайн оплачен, доставка",
        "customer_type": CustomerType.B2C,
        "customer_name": "Иван Иванов",
        "customer_phone": "+79001112233",
        "customer_email": "ivan@example.com",
        "payment_method": "online",
        "payment_status": PaymentStatus.PAID,
        "delivery_method": "delivery",
        "delivery_address": "Пенза, ул. Московская, 1",
        "comment": "Позвонить за час",
        "n_lines": 1,
    },
    {
        "label": "B2C, наличные, самовывоз",
        "customer_type": CustomerType.B2C,
        "customer_name": "Пётр Петров",
        "customer_phone": "+79004445566",
        "customer_email": "petr@example.com",
        "payment_method": "cash",
        "payment_status": PaymentStatus.PENDING,
        "delivery_method": "pickup",
        "delivery_address": "",
        "comment": "Самовывоз со склада",
        "n_lines": 2,
    },
    {
        "label": "B2B, безнал ожидает оплаты, доставка",
        "customer_type": CustomerType.B2B,
        "customer_name": "ООО «СтройМонтаж» / Сидоров С.С.",
        "customer_phone": "+78412700700",
        "customer_email": "zakup@stroymontazh.example",
        "company_name": "ООО «СтройМонтаж»",
        "inn": "5836012345",
        "kpp": "583601001",
        "legal_address": "440000, г. Пенза, ул. Кирова, 10",
        "payment_method": "invoice",
        "payment_status": PaymentStatus.PENDING,
        "delivery_method": "delivery",
        "delivery_address": "Пенза, пр. Победы, 75, склад",
        "comment": "Нужны оригиналы документов",
        "n_lines": 3,
    },
    {
        "label": "B2C, онлайн ожидает оплаты, доставка",
        "customer_type": CustomerType.B2C,
        "customer_name": "Анна Смирнова",
        "customer_phone": "+79007778899",
        "customer_email": "anna@example.com",
        "payment_method": "online",
        "payment_status": PaymentStatus.PENDING,
        "delivery_method": "delivery",
        "delivery_address": "Заречный, ул. Зелёная, 3",
        "comment": "",
        "n_lines": 1,
    },
    {
        "label": "B2B, безнал оплачен, самовывоз",
        "customer_type": CustomerType.B2B,
        "customer_name": "ИП Кузнецов А.А.",
        "customer_phone": "+78412600600",
        "customer_email": "kuznetsov@example",
        "company_name": "ИП Кузнецов Алексей Анатольевич",
        "inn": "583500123456",
        "kpp": "",
        "legal_address": "440000, г. Пенза, ул. Суворова, 144",
        "payment_method": "invoice",
        "payment_status": PaymentStatus.PAID,
        "delivery_method": "pickup",
        "delivery_address": "",
        "comment": "Заберёт водитель",
        "n_lines": 2,
    },
]


def _catalog_lines() -> list[dict]:
    """Реальные строки из каталога (товары с непустым code_1c) или fallback."""
    products = list(
        Product.objects.exclude(code_1c__isnull=True).exclude(code_1c="").order_by("id")[:20]
    )
    lines = []
    for p in products:
        lines.append(
            {
                "code_1c": p.code_1c,
                "article": p.article or "",
                "name": p.name or p.code_1c,
                "unit": p.unit or "шт",
                "price": p.price if p.price is not None else Decimal("1000.00"),
                "product": p,
            }
        )
    return lines or _FALLBACK_LINES


def _make_order(seq: int, scenario: dict, pool: list[dict]) -> Order:
    """Создать один тестовый заказ со строками-снимками по сценарию."""
    today = timezone.now().strftime("%Y%m%d")
    number = f"{TEST_PREFIX}{today}-{seq:03d}"

    order = Order.objects.create(
        order_number=number,
        fulfillment_status=FulfillmentStatus.NEW,
        sync_1c_status=Sync1CStatus.PENDING,
        payment_status=scenario["payment_status"],
        payment_method=scenario["payment_method"],
        customer_type=scenario["customer_type"],
        customer_name=scenario["customer_name"],
        customer_phone=scenario["customer_phone"],
        customer_email=scenario.get("customer_email", ""),
        company_name=scenario.get("company_name", ""),
        inn=scenario.get("inn", ""),
        kpp=scenario.get("kpp", ""),
        legal_address=scenario.get("legal_address", ""),
        delivery_method=scenario["delivery_method"],
        delivery_address=scenario.get("delivery_address", ""),
        comment=scenario.get("comment", ""),
        currency="RUB",
    )

    total = Decimal("0.00")
    n = scenario["n_lines"]
    for i in range(n):
        src = pool[(seq + i) % len(pool)]
        qty = 1 + (i % 3)  # 1..3
        price = src["price"]
        line_total = price * qty
        total += line_total
        OrderItem.objects.create(
            order=order,
            product=src.get("product"),
            code_1c=src["code_1c"],
            article=src["article"],
            name=src["name"],
            unit=src["unit"],
            price_final=price,
            quantity=qty,
            line_total=line_total,
            currency="RUB",
        )

    order.total = total
    order.save(update_fields=["total"])
    return order


class Command(BaseCommand):
    help = "Создать тестовые заказы (new/pending) для приёмки обмена заказами с 1С."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count", type=int, default=5, help="Сколько заказов создать (по умолч. 5)."
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Сначала удалить прежние тестовые заказы (номер с префиксом TEST-1C-).",
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        if opts["reset"]:
            qs = Order.objects.filter(order_number__startswith=TEST_PREFIX)
            deleted = qs.count()
            qs.delete()
            self.stdout.write(self.style.WARNING(f"Удалено прежних тестовых заказов: {deleted}."))

        count = opts["count"]
        if count <= 0:
            self.stdout.write(self.style.SUCCESS("Создание заказов пропущено (--count 0)."))
            return

        pool = _catalog_lines()
        src_note = (
            "реальные товары каталога"
            if pool and pool[0].get("product") is not None
            else "демо-коды (каталог пуст)"
        )

        created = []
        for seq in range(1, count + 1):
            scenario = _SCENARIOS[(seq - 1) % len(_SCENARIOS)]
            order = _make_order(seq, scenario, pool)
            created.append((order, scenario["label"]))

        self.stdout.write(
            self.style.SUCCESS(
                f"Создано тестовых заказов: {len(created)} (строки: {src_note}).\n"
                f"Все — fulfillment=new, sync_1c=pending → попадают в GET /api/1c/orders/new."
            )
        )
        for order, label in created:
            self.stdout.write(
                f"  • {order.order_number} | {label} | "
                f"{order.customer_type} | оплата={order.payment_status} | "
                f"строк={order.items.count()} | {order.total} {order.currency}"
            )
        self.stdout.write(
            "\nАдминка: /admin/orders/order/  (фильтр по sync_1c_status=Ожидает выгрузки)"
        )
