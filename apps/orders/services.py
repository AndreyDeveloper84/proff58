"""Сервисный слой заказов и корзины — вся бизнес-логика #26.

Тонкие вьюхи и «худые» модели: правила, валидация и оркестрация — здесь.
Цена ВСЕГДА серверная (через ``pricing.price_for``), никогда из тела запроса.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.accounts.models import CustomerType
from apps.accounts.phone import normalize_phone
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
    ReservationStatus,
    Sync1CStatus,
)

_ZERO = Decimal("0.00")

# TTL резерва (#423, B-03): по истечении janitor освобождает неоплаченный резерв.
RESERVATION_TTL_SECONDS = 24 * 3600


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
    """Добавить товар в корзину (или увеличить количество существующей строки).

    Если для этого товара есть soft-deleted строка — восстанавливает её.
    """
    qty = _validate_qty(qty)
    _ensure_active_product(product)

    # Проверяем сначала мягко удалённую строку (чтобы не нарушить unique constraint).
    deleted_item = CartItem.objects.filter(cart=cart, product=product, is_deleted=True).first()
    if deleted_item:
        deleted_item.is_deleted = False
        deleted_item.deleted_at = None
        deleted_item.quantity = qty
        deleted_item.save(update_fields=["is_deleted", "deleted_at", "quantity", "updated_at"])
        return deleted_item

    item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        is_deleted=False,
        defaults={"quantity": qty},
    )
    if not created:
        # F() — атомарный инкремент на стороне БД, защита от lost-update (#282).
        CartItem.objects.filter(pk=item.pk).update(
            quantity=models.F("quantity") + qty,
            updated_at=timezone.now(),
        )
        item.refresh_from_db()
    return item


def update_cart_item(item: CartItem, qty: int) -> CartItem:
    """Установить количество строки корзины (абсолютное значение)."""
    qty = _validate_qty(qty)
    item.quantity = qty
    item.save(update_fields=["quantity", "updated_at"])
    return item


def remove_from_cart(item: CartItem) -> None:
    """Физически удалить строку (для внутреннего использования)."""
    item.delete()


def soft_delete_cart_item(item: CartItem) -> None:
    """Мягко удалить строку — скрыть из корзины с возможностью восстановления (#380)."""
    item.is_deleted = True
    item.deleted_at = timezone.now()
    item.save(update_fields=["is_deleted", "deleted_at", "updated_at"])


def restore_cart_item(item: CartItem) -> CartItem:
    """Восстановить мягко удалённую строку корзины (undo-действие, #380)."""
    if not item.is_deleted:
        return item
    item.is_deleted = False
    item.deleted_at = None
    item.save(update_fields=["is_deleted", "deleted_at", "updated_at"])
    return item


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
    has_mixed_currencies: bool = False


def get_cart_view(cart: Cart, user=None) -> CartView:
    """Собрать представление корзины с АКТУАЛЬНОЙ ценой каждой строки.

    Цена считается на лету через price_for(product, user, qty) — никогда не
    берётся из хранилища. Строки без цены попадают в выдачу с line_total=None.
    При смешении валют: has_mixed_currencies=True, total=0 (#375).
    """
    lines: list[CartLine] = []
    total = _ZERO
    order_currency: str | None = None
    has_mixed_currencies = False

    items = cart.items.filter(is_deleted=False).select_related("product")
    for item in items:
        product = item.product
        result = price_for(product, user, item.quantity)
        if order_currency is None:
            order_currency = result.currency
        elif result.currency != order_currency:
            has_mixed_currencies = True

        if result.final is not None and not has_mixed_currencies:
            line_total = result.final * item.quantity
            total += line_total
        elif result.final is not None:
            line_total = result.final * item.quantity
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

    if has_mixed_currencies:
        total = _ZERO

    return CartView(
        cart=cart,
        lines=lines,
        total=total,
        currency=order_currency or "RUB",
        has_mixed_currencies=has_mixed_currencies,
    )


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
        # #421 (B-01): храним нормализованный номер, чтобы claim по verified-телефону
        # находил заказ независимо от исходного формата ввода.
        "customer_phone": normalize_phone(customer_data.get("customer_phone") or ""),
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
            snapshot["customer_phone"] = normalize_phone(getattr(user, "phone", "") or "")
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

    product_ids = list(cart.items.filter(is_deleted=False).values_list("product_id", flat=True))
    if not product_ids:
        raise ValidationError("Корзина пуста.")

    locked_products = {
        p.pk: p for p in Product.objects.select_for_update().filter(pk__in=product_ids)
    }
    items = list(cart.items.filter(is_deleted=False))

    # Тип покупателя. Для аутентифицированного — из учётной записи. Для гостя —
    # #430 (M-06, ADR #444): разрешён гостевой B2B invoice-заказ (запрос счёта без
    # регистрации). Прежний запрет (#282) снят: единого ценника больше нет опта,
    # поэтому «объявить себя B2B» не даёт ценового преимущества; B2B-реквизиты
    # валидируются ниже, цена та же розничная.
    if user is not None and getattr(user, "is_authenticated", False):
        customer_type = getattr(user, "customer_type", CustomerType.B2C)
    elif (customer_data.get("customer_type") or "").lower() == CustomerType.B2B:
        customer_type = CustomerType.B2B
    else:
        customer_type = CustomerType.B2C

    snapshot = _customer_snapshot(user, customer_type, customer_data)

    # Серверная валидация B2B-реквизитов и способа оплаты (#323, #430/M-06).
    if customer_type == CustomerType.B2B:
        from .invoice import validate_b2b_requisites

        errors = validate_b2b_requisites(
            inn=snapshot["inn"],
            company_name=snapshot["company_name"],
            kpp=snapshot["kpp"],
            legal_address=snapshot["legal_address"],
            email=snapshot["customer_email"],
        )
        if errors:
            raise ValidationError(errors[0])
        if payment_method and payment_method != "invoice":
            raise ValidationError("B2B-заказ оплачивается только по счёту.")
        payment_method = "invoice"
    elif payment_method == "invoice":
        raise ValidationError("Оплата по счёту доступна только для B2B-заказов.")

    is_guest = user is None or not getattr(user, "is_authenticated", False)

    # Серверная валидация контакта гостя (#321).
    if is_guest:
        if not snapshot["customer_name"].strip():
            raise ValidationError("Имя обязательно для гостевого заказа.")
        if not snapshot["customer_phone"].strip():
            raise ValidationError("Телефон обязателен для гостевого заказа.")

    access_token = uuid.uuid4().hex if is_guest else ""

    order = Order(
        order_number=_generate_order_number(),
        user=None if is_guest else user,
        access_token=access_token,
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

    # #429 (M-05, ADR #444): стоимость доставки считается СЕРВЕРОМ по серверной
    # корзине (единый источник правды), включается в итог и облагается НДС вместе
    # с товарами. При manual_required (нет весогабаритов для СДЭК) стоимость
    # неизвестна → delivery_cost=null, итог предварительный (только товары).
    from apps.delivery.services import quote_for_order

    quote = quote_for_order(
        zone_slug=delivery.get("delivery_zone", "") or "",
        goods_total=total,
        items=items,
    )
    order.delivery_zone = quote.zone_slug
    order.delivery_cost = quote.cost
    # Значения статусов delivery.services совпадают с Order.DeliveryCalcStatus.
    order.delivery_calc_status = quote.status
    order.delivery_snapshot = quote.snapshot
    grand_total = total + (quote.cost or _ZERO)

    order.total = grand_total
    order.currency = order_currency or "RUB"
    # #430 (M-06): снимок НДС для B2B (цена включает НДС; ставка фиксируется на
    # момент заказа). База НДС — итог (товары + доставка). Для B2C поля нулевые.
    if customer_type == CustomerType.B2B:
        from apps.pricing.vat import vat_breakdown

        rate = int(getattr(settings, "VAT_RATE_PERCENT", 0))
        net, vat = vat_breakdown(grand_total, rate)
        order.vat_rate = rate
        order.amount_without_vat = net
        order.vat_amount = vat
    # #423 (B-03): резерв удержан выше (available -= qty, reserved += qty по строкам).
    # Фиксируем статус и TTL — janitor освободит его, если заказ не оплатят вовремя.
    order.reservation_status = ReservationStatus.HELD
    order.reserved_until = timezone.now() + timedelta(seconds=RESERVATION_TTL_SECONDS)
    order.save(
        update_fields=[
            "total",
            "currency",
            "delivery_zone",
            "delivery_cost",
            "delivery_calc_status",
            "delivery_snapshot",
            "vat_rate",
            "amount_without_vat",
            "vat_amount",
            "reservation_status",
            "reserved_until",
            "updated_at",
        ]
    )

    # Корзину не удаляем: фиксируем как оформленную (история + идемпотентность).
    cart.status = CartStatus.ORDERED
    cart.ordered_at = timezone.now()
    cart.save(update_fields=["status", "ordered_at", "updated_at"])

    # Публикуем событие после коммита (подписчик увидит закоммиченные данные).
    order_id = order.id
    transaction.on_commit(lambda: order_created.send(sender=Order, order_id=order_id))

    return order


def claim_guest_orders(user) -> int:
    """Привязать гостевые заказы к аккаунту по телефону. Возвращает число привязанных.

    #421 (B-01): claim разрешён ТОЛЬКО для подтверждённого номера
    (``user.phone_verified``). Иначе регистрация чужого ещё не занятого номера
    захватила бы историю заказов, адрес и B2B-реквизиты жертвы. Владение
    подтверждается через OTP в MAX (см. integration_max.handlers.auth).

    Матчинг — по нормализованному номеру (customer_phone заказов и телефоны
    пользователей приведены к канону), чтобы разные форматы одного номера не
    расходились. select_for_update защищает от гонки параллельного claim.
    """
    if not getattr(user, "phone_verified", False):
        return 0
    phone = normalize_phone(getattr(user, "phone", ""))
    if not phone:
        return 0
    with transaction.atomic():
        ids = list(
            Order.objects.select_for_update()
            .filter(user__isnull=True, customer_phone=phone)
            .values_list("pk", flat=True)
        )
        if not ids:
            return 0
        return Order.objects.filter(pk__in=ids).update(user=user)
