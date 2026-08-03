"""DRF-вьюхи заказов и корзины — тонкие, вся логика в services.

Эндпоинты:
  GET    /api/cart/                       — текущая корзина с актуальной ценой
  POST   /api/cart/items/                 — добавить товар
  PATCH  /api/cart/items/{id}/            — изменить количество
  DELETE /api/cart/items/{id}/            — мягкое удаление (undo-window)
  POST   /api/cart/items/{id}/restore/    — восстановить мягко удалённую строку (#380)
  POST   /api/orders/                     — оформить заказ (цена серверная)
  GET    /api/orders/                     — список своих заказов (только аутентифицированный)
  GET    /api/orders/{number}/            — заказ по номеру (только владелец)
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Product
from apps.core.throttling import OrdersRateThrottle

from .. import services
from ..models import Cart, CartItem, CartStatus, Order
from .serializers import (
    AddCartItemSerializer,
    CartViewSerializer,
    CreateOrderSerializer,
    OrderSerializer,
    UpdateCartItemSerializer,
)


def _no_store(response):
    """#438 (m-03): не кешировать и не утекать URL с гостевым токеном.

    Токен заказа с ПДн приходит в query string — запрещаем кеш (browser/proxy) и
    отправку URL как Referer на сторонние ресурсы.
    """
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "no-referrer"
    return response


def _get_session_key(request) -> str:
    """Гарантированно вернуть ключ сессии (создав сессию при необходимости)."""
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key


def _get_or_create_active_cart(request) -> Cart:
    """Активная корзина текущего покупателя (по пользователю или сессии).

    Используем try/except IntegrityError чтобы пережить гонку на partial uniq-constraint
    (два одновременных запроса — оба пытаются создать корзину, один проигрывает → #282).
    """
    user = request.user if request.user.is_authenticated else None
    if user is not None:
        try:
            cart, _ = Cart.objects.get_or_create(
                user=user, status=CartStatus.ACTIVE, defaults={"session_key": ""}
            )
        except IntegrityError:
            cart = Cart.objects.get(user=user, status=CartStatus.ACTIVE)
        return cart

    session_key = _get_session_key(request)
    try:
        cart, _ = Cart.objects.get_or_create(
            session_key=session_key, user__isnull=True, status=CartStatus.ACTIVE
        )
    except IntegrityError:
        cart = Cart.objects.get(
            session_key=session_key, user__isnull=True, status=CartStatus.ACTIVE
        )
    return cart


def _get_active_cart(request) -> Cart | None:
    """Найти активную корзину без создания (None, если нет)."""
    user = request.user if request.user.is_authenticated else None
    if user is not None:
        return Cart.objects.filter(user=user, status=CartStatus.ACTIVE).first()
    session_key = request.session.session_key
    if not session_key:
        return None
    return Cart.objects.filter(
        session_key=session_key, user__isnull=True, status=CartStatus.ACTIVE
    ).first()


def _cart_response(request, cart: Cart) -> Response:
    """Сериализовать корзину с актуальной серверной ценой."""
    user = request.user if request.user.is_authenticated else None
    view = services.get_cart_view(cart, user)
    return Response(CartViewSerializer(view).data)


def _empty_cart_view() -> services.CartView:
    """Нейтральный снимок пустой корзины — без записи в БД и без сессии.

    Нужен, чтобы чтение корзины не заводило гостю сессию: считать в пустой
    корзине нечего, а несохранённый Cart нельзя спрашивать о строках.
    """
    from apps.core.features import is_enabled

    return services.CartView(
        cart=Cart(status=CartStatus.ACTIVE),
        lines=[],
        total=Decimal("0.00"),
        currency="RUB",
        promotions_enabled=is_enabled("promotions"),
    )


class CartView(APIView):
    """GET /api/cart/ — текущая корзина.

    Чтение НЕ создаёт ни корзину, ни сессию: CartProvider зовёт этот эндпоинт на
    каждой странице сайта, и раньше любой посетитель получал cookie `sessionid`
    просто за факт захода. По этой cookie фронт считал человека вошедшим и
    пускал в кабинет, откуда его тут же выбрасывало на форму входа. Сессия
    заводится там, где она действительно нужна, — при добавлении товара.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        cart = _get_active_cart(request)
        if cart is None:
            return Response(CartViewSerializer(_empty_cart_view()).data)
        return _cart_response(request, cart)


class CartPromoView(APIView):
    """POST/DELETE /api/cart/promo/ — применить/снять промокод (#571).

    Код валидируется ДО сохранения: невалидный не прилипает к корзине (400 с
    человеческим текстом). Флаг promotions выключен → 404 (фичи нет). Суммы
    скидок фронт не передаёт никогда — только код; расчёт в get_cart_view.
    """

    permission_classes = [AllowAny]
    throttle_classes = [OrdersRateThrottle]

    def post(self, request):
        from apps.core.features import is_enabled
        from apps.promotions.services import resolve_promo_code

        if not is_enabled("promotions"):
            return Response(status=status.HTTP_404_NOT_FOUND)
        code = str(request.data.get("code", "") or "").strip()
        if not code:
            return Response({"detail": "Укажите промокод."}, status=status.HTTP_400_BAD_REQUEST)
        promo, error = resolve_promo_code(code)
        if error is not None:
            return Response({"detail": error.message}, status=status.HTTP_400_BAD_REQUEST)
        cart = _get_or_create_active_cart(request)
        cart.promo_code = promo.promo_code  # каноническое написание кода
        cart.save(update_fields=["promo_code", "updated_at"])
        return _cart_response(request, cart)

    def delete(self, request):
        from apps.core.features import is_enabled

        if not is_enabled("promotions"):
            return Response(status=status.HTTP_404_NOT_FOUND)
        cart = _get_or_create_active_cart(request)
        if cart.promo_code:
            cart.promo_code = ""
            cart.save(update_fields=["promo_code", "updated_at"])
        return _cart_response(request, cart)


class CartItemsView(APIView):
    """POST /api/cart/items/ — добавить товар в корзину."""

    permission_classes = [AllowAny]
    throttle_classes = [OrdersRateThrottle]  # #9: лимит флуда корзины гостем

    def post(self, request):
        ser = AddCartItemSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        product = get_object_or_404(Product, pk=ser.validated_data["product_id"])
        cart = _get_or_create_active_cart(request)
        try:
            services.add_to_cart(cart, product, ser.validated_data["quantity"])
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=status.HTTP_400_BAD_REQUEST)
        return _cart_response(request, cart)


class CartItemDetailView(APIView):
    """PATCH/DELETE /api/cart/items/{id}/ — изменить/удалить строку."""

    permission_classes = [AllowAny]

    def _get_item(self, request, pk) -> CartItem:
        """Строка только из АКТИВНОЙ корзины текущего покупателя."""
        cart = _get_active_cart(request)
        if cart is None:
            return None
        return CartItem.objects.filter(pk=pk, cart=cart).first()

    def patch(self, request, pk):
        item = self._get_item(request, pk)
        if item is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        ser = UpdateCartItemSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            services.update_cart_item(item, ser.validated_data["quantity"])
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=status.HTTP_400_BAD_REQUEST)
        return _cart_response(request, item.cart)

    def delete(self, request, pk):
        item = self._get_item(request, pk)
        if item is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        cart = item.cart
        services.soft_delete_cart_item(item)
        return _cart_response(request, cart)


class CartItemRestoreView(APIView):
    """POST /api/cart/items/{id}/restore/ — undo-восстановление строки (#380).

    Фронт вызывает в течение undo-окна (~5 сек) после DELETE. Возвращает
    корзину с восстановленной строкой.
    """

    permission_classes = [AllowAny]

    def post(self, request, pk):
        cart = _get_active_cart(request)
        if cart is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        item = CartItem.objects.filter(pk=pk, cart=cart, is_deleted=True).first()
        if item is None:
            return Response(
                {"detail": "Строка не найдена или уже восстановлена."},
                status=status.HTTP_404_NOT_FOUND,
            )
        services.restore_cart_item(item)
        return _cart_response(request, cart)


class OrdersView(APIView):
    """POST /api/orders/ (любой), GET /api/orders/ (только аутентифицированный)."""

    throttle_classes = [OrdersRateThrottle]  # #9: лимит флуда оформления заказов

    def get_permissions(self):
        if self.request.method == "POST":
            return [AllowAny()]
        return [IsAuthenticated()]

    def post(self, request):
        ser = CreateOrderSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        cart = _get_active_cart(request)
        if cart is None:
            return Response({"detail": "Корзина пуста."}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user if request.user.is_authenticated else None
        customer_data = {
            "customer_name": data["customer_name"],
            "customer_phone": data["customer_phone"],
            "customer_email": data["customer_email"],
            "customer_type": data["customer_type"],
            "company_name": data["company_name"],
            "inn": data["inn"],
            "kpp": data["kpp"],
            "legal_address": data["legal_address"],
        }
        delivery = {
            "delivery_method": data["delivery_method"],
            "delivery_address": data["delivery_address"],
            "delivery_zone": data["delivery_zone"],
            "delivery_slot_id": data["delivery_slot_id"],
            "comment": data["comment"],
        }
        try:
            order = services.place_order(
                cart,
                user=user,
                customer_data=customer_data,
                delivery=delivery,
                payment_method=data["payment_method"],
            )
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=status.HTTP_400_BAD_REQUEST)
        resp_data = OrderSerializer(order).data
        if order.access_token:
            resp_data["access_token"] = order.access_token
        return Response(resp_data, status=status.HTTP_201_CREATED)

    def get(self, request):
        # #438 (m-05): пагинация истории заказов — иначе для B2B-аккаунта ответ
        # растёт неограниченно (все заказы + строки).
        qs = (
            Order.objects.filter(user=request.user)
            .prefetch_related("items")
            .order_by("-created_at")
        )
        paginator = LimitOffsetPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(OrderSerializer(page, many=True).data)


class OrderDetailView(APIView):
    """GET /api/orders/{number}/ — заказ по номеру, только владелец.

    Гостевые заказы по номеру не публичны (риск перебора номеров и утечки ПДн):
    доступ требует аутентификации и принадлежности заказа пользователю.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, number):
        order = (
            Order.objects.filter(order_number=number, user=request.user)
            .prefetch_related("items")
            .first()
        )
        if order is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(OrderSerializer(order).data)


class GuestOrderView(APIView):
    """Доступ к гостевому заказу по номеру + токену (без логина)."""

    permission_classes = [AllowAny]

    def get(self, request, number):
        token = request.query_params.get("t", "")
        order = services.get_guest_order_by_token(number, token)
        if order is None:
            return _no_store(Response(status=status.HTTP_404_NOT_FOUND))
        return _no_store(Response(OrderSerializer(order).data))


class InvoiceView(APIView):
    """HTML-счёт для B2B-заказа. Для гостя — по токену."""

    permission_classes = [AllowAny]

    def get(self, request, number):
        token = request.query_params.get("t", "")
        user = request.user if request.user.is_authenticated else None

        if user:
            order = Order.objects.filter(order_number=number, user=user).first()
        elif token:
            order = services.get_guest_order_by_token(number, token)
        else:
            return _no_store(Response(status=status.HTTP_404_NOT_FOUND))

        if order is None:
            return _no_store(Response(status=status.HTTP_404_NOT_FOUND))

        if order.customer_type != "b2b":
            return Response(
                {"detail": "Счёт доступен только для B2B-заказов."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from django.http import HttpResponse
        from django.template.loader import render_to_string

        from apps.orders.invoice import prepare_invoice

        invoice = prepare_invoice(order)
        html = render_to_string("orders/invoice.html", {"invoice": invoice})
        # Счёт содержит ПДн; при гостевом токене в URL — запрещаем кеш/referrer.
        return _no_store(HttpResponse(html, content_type="text/html"))


class AccountInvoicesView(APIView):
    """GET /api/account/invoices/ — счета B2B текущего пользователя (#560).

    Owner-only: только счета по заказам самого пользователя. У B2C-аккаунта
    список пуст (счета выставляются только B2B-заказам). Пагинация — как у
    списка заказов (#438/m-05).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from ..models import B2BInvoice
        from .serializers import B2BInvoiceSerializer

        qs = (
            B2BInvoice.objects.filter(order__user=request.user)
            .select_related("order")
            .order_by("-issued_at")
        )
        paginator = LimitOffsetPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(B2BInvoiceSerializer(page, many=True).data)


class AccountInvoiceDetailView(APIView):
    """GET /api/account/invoices/{number}/ — детали счёта, только владелец."""

    permission_classes = [IsAuthenticated]

    def get(self, request, number):
        from ..models import B2BInvoice
        from .serializers import B2BInvoiceSerializer

        invoice = (
            B2BInvoice.objects.filter(number=number, order__user=request.user)
            .select_related("order")
            .first()
        )
        if invoice is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(B2BInvoiceSerializer(invoice).data)
