"""Сервисный слой заказов и корзины — вся бизнес-логика #26.

Тонкие вьюхи и «худые» модели: правила, валидация и оркестрация — здесь.
Цена ВСЕГДА серверная (через ``pricing.price_for``), никогда из тела запроса.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.accounts.models import CustomerType
from apps.catalog.models import Product
from apps.core.events import order_created
from apps.pricing.services import price_for

from .models import (
    Cart,
    CartItem,
    CartStatus,
    FulfillmentStatus,
    Order,
    OrderItem,
    PaymentStatus,
    Sync1CStatus,
)

_ZERO = Decimal("0.00")


# ---------------------------------------------------------------------------
# Корзина
# ---------------------------------------------------------------------------
def _ensure_active_product(product: Product) -> None:
    """Товар должен быть опубликован и виден на витрине, иначе отказ."""
    if not product.is_visible:
        raise ValidationError("Товар недоступен для заказа.")


def _validate_qty(qty: int) -> int:
    """Количество — целое ≥ 1."""
    try:
        qty = int(qty)
    except (TypeError, ValueError):
        raise ValidationError("Некорректное количество.") from None
    if qty < 1:
        raise ValidationError("Количество должно быть не меньше 1.")
    return qty


def add_to_cart(cart: Cart, product: Product, qty: int = 1) -> CartItem:
    """Добавить товар в корзину (или увеличить количество существующей строки)."""
    qty = _validate_qty(qty)
    _ensure_active_product(product)

    item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        defaults={"quantity": qty},
    )
    if not created:
        item.quantity += qty
        item.save(update_fields=["quantity", "updated_at"])
    return item


def update_cart_item(item: CartItem, qty: int) -> CartItem:
    """Установить количество строки корзины (абсолютное значение)."""
    qty = _validate_qty(qty)
    item.quantity = qty
    item.save(update_fields=["quantity", "updated_at"])
    return item


def remove_from_cart(item: CartItem) -> None:
    """Удалить строку из корзины."""
    item.delete()


@dataclass(frozen=True)
class CartLine:
    """Строка корзины с актуальной (серверной) ценой для вывода."""

    item: CartItem
    product: Product
    quantity: int
    price_final: Decimal | None
    price_base: Decimal | None
    discount: Decimal | None
    price_type: str
    currency: str
    line_total: Decimal | None  # None, если у товара нет цены


@dataclass(frozen=True)
class CartView:
    """Снимок корзины для вывода: строки + итог."""

    cart: Cart
    lines: list[CartLine]
    total: Decimal
    currency: str


def get_cart_view(cart: Cart, user=None) -> CartView:
    """Собрать представление корзины с АКТУАЛЬНОЙ ценой каждой строки.

    Цена считается на лету через price_for(product, user, qty) — никогда не
    берётся из хранилища. Строки без цены попадают в выдачу с line_total=None.
    """
    lines: list[CartLine] = []
    total = _ZERO
    currency = "RUB"

    items = cart.items.select_related("product").all()
    for item in items:
        product = item.product
        result = price_for(product, user, item.quantity)
        if currency == "RUB" and result.currency:
            currency = result.currency
        if result.final is not None:
            line_total = result.final * item.quantity
            total += line_total
        else:
            line_total = None
        lines.append(
            CartLine(
                item=item,
                product=product,
                quantity=item.quantity,
                price_final=result.final,
                price_base=result.base,
                discount=result.discount,
                price_type=result.price_type,
                currency=result.currency,
                line_total=line_total,
            )
        )

    return CartView(cart=cart, lines=lines, total=total, currency=currency)


# ---------------------------------------------------------------------------
# Оформление заказа
# ---------------------------------------------------------------------------
def _generate_order_number() -> str:
    """Человекочитаемый уникальный номер заказа.

    Формат: ``П-YYYYMMDD-XXXXXX`` (дата + короткий случайный суффикс).
    Уникальность гарантируется БД (unique), коллизию повторяем.
    """
    today = timezone.now().strftime("%Y%m%d")
    for _attempt in range(10):
        suffix = uuid.uuid4().hex[:6].upper()
        number = f"П-{today}-{suffix}"
        if not Order.objects.filter(order_number=number).exists():
            return number
    # Крайне маловероятно: отдаём заведомо уникальный длинный хвост.
    return f"П-{today}-{uuid.uuid4().hex.upper()}"


def _customer_snapshot(user, customer_type: str, customer_data: dict) -> dict:
    """Снимок покупателя для заказа.

    customer_data (контактные данные из формы) имеет приоритет над данными
    профиля; недостающее добирается из User/Profile. Для B2B копируются
    реквизиты организации.
    """
    customer_data = customer_data or {}
    snapshot = {
        "customer_type": customer_type,
        "customer_name": customer_data.get("customer_name") or "",
        "customer_phone": customer_data.get("customer_phone") or "",
        "customer_email": customer_data.get("customer_email") or "",
        "company_name": "",
        "inn": "",
        "kpp": "",
        "legal_address": "",
    }

    # Добор контактов из учётной записи
    if user is not None and getattr(user, "is_authenticated", False):
        if not snapshot["customer_name"]:
            snapshot["customer_name"] = getattr(user, "full_name", "") or ""
        if not snapshot["customer_phone"]:
            snapshot["customer_phone"] = getattr(user, "phone", "") or ""
        if not snapshot["customer_email"]:
            snapshot["customer_email"] = getattr(user, "email", "") or ""

    # Реквизиты B2B: приоритет — переданные данные, затем профиль
    if customer_type == CustomerType.B2B:
        profile = None
        if user is not None and getattr(user, "is_authenticated", False):
            profile = getattr(user, "profile", None)
        snapshot["company_name"] = customer_data.get("company_name") or (
            getattr(profile, "company_name", "") if profile else ""
        )
        snapshot["inn"] = customer_data.get("inn") or (
            getattr(profile, "inn", "") if profile else ""
        )
        snapshot["kpp"] = customer_data.get("kpp") or (
            getattr(profile, "kpp", "") if profile else ""
        )
        snapshot["legal_address"] = customer_data.get("legal_address") or (
            getattr(profile, "legal_address", "") if profile else ""
        )

    return snapshot


@transaction.atomic
def place_order(
    cart: Cart,
    *,
    user=None,
    customer_data: dict | None = None,
    delivery: dict | None = None,
    payment_method: str = "",
) -> Order:
    """Главный use-case: оформить заказ из корзины.

    Гарантии:
    - идемпотентность: пустая или уже оформленная корзина → ValidationError
      (повторное оформление не плодит заказы);
    - цена ВСЕГДА серверная (повторный price_for на момент оформления);
    - снимок покупателя и строк фиксируется в заказе;
    - корзина не очищается физически (status=ordered);
    - событие order_created публикуется РОВНО один раз после commit.
    """
    customer_data = customer_data or {}
    delivery = delivery or {}

    # Блокируем корзину на время оформления (защита от гонок/двойного клика).
    cart = Cart.objects.select_for_update().get(pk=cart.pk)

    if cart.status != CartStatus.ACTIVE:
        raise ValidationError("Корзина уже оформлена в заказ.")

    product_ids = list(cart.items.values_list("product_id", flat=True))
    if not product_ids:
        raise ValidationError("Корзина пуста.")

    locked_products = {
        p.pk: p for p in Product.objects.select_for_update().filter(pk__in=product_ids)
    }
    items = list(cart.items.all())

    # Тип покупателя: для аутентифицированного — из учётной записи.
    customer_type = customer_data.get("customer_type") or CustomerType.B2C
    if user is not None and getattr(user, "is_authenticated", False):
        customer_type = getattr(user, "customer_type", CustomerType.B2C)

    snapshot = _customer_snapshot(user, customer_type, customer_data)

    order = Order(
        order_number=_generate_order_number(),
        user=user if (user is not None and getattr(user, "is_authenticated", False)) else None,
        fulfillment_status=FulfillmentStatus.NEW,
        payment_status=PaymentStatus.PENDING,
        sync_1c_status=Sync1CStatus.PENDING,
        delivery_method=delivery.get("delivery_method", "") or "",
        delivery_address=delivery.get("delivery_address", "") or "",
        comment=delivery.get("comment", "") or "",
        payment_method=payment_method or "",
        total=_ZERO,
        currency="RUB",
        **snapshot,
    )
    order.save()

    total = _ZERO
    order_currency = None
    for item in items:
        product = locked_products.get(item.product_id)

        if product is None or not product.is_visible:
            raise ValidationError(f"Товар «{getattr(product, 'name', '—')}» недоступен для заказа.")

        qty = item.quantity
        available = product.available_quantity or _ZERO
        if Decimal(qty) > available:
            raise ValidationError(
                f"Недостаточно товара «{product.name}»: доступно {available}, запрошено {qty}."
            )

        result = price_for(product, user, qty)
        if result.final is None:
            raise ValidationError(f"У товара «{product.name}» не задана цена.")

        if order_currency is None:
            order_currency = result.currency
        elif result.currency != order_currency:
            raise ValidationError(
                f"Смешение валют в корзине: {order_currency} и {result.currency}."
            )

        line_total = result.final * qty
        total += line_total

        Product.objects.filter(pk=product.pk).update(
            available_quantity=models.F("available_quantity") - qty,
            reserved_quantity=models.F("reserved_quantity") + qty,
        )

        OrderItem.objects.create(
            order=order,
            product=product,
            code_1c=product.code_1c or "",
            article=product.article or "",
            name=product.name,
            unit=product.unit or "",
            price_base=result.base,
            price_final=result.final,
            discount=result.discount,
            price_type=result.price_type,
            currency=result.currency,
            quantity=qty,
            line_total=line_total,
        )

    order.total = total
    order.currency = order_currency or "RUB"
    order.save(update_fields=["total", "currency", "updated_at"])

    # Корзину не удаляем: фиксируем как оформленную (история + идемпотентность).
    cart.status = CartStatus.ORDERED
    cart.ordered_at = timezone.now()
    cart.save(update_fields=["status", "ordered_at", "updated_at"])

    # Публикуем событие после коммита (подписчик увидит закоммиченные данные).
    order_id = order.id
    transaction.on_commit(lambda: order_created.send(sender=Order, order_id=order_id))

    return order
