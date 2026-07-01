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

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import status
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


def _get_session_key(request) -> str:
    """Гарантированно вернуть ключ сессии (создав сессию при необходимости)."""
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key


def _get_or_create_active_cart(request) -> Cart:
    """Активная корзина текущего покупателя (по пользователю или сессии)."""
    user = request.user if request.user.is_authenticated else None
    if user is not None:
        cart, _ = Cart.objects.get_or_create(
            user=user, status=CartStatus.ACTIVE, defaults={"session_key": ""}
        )
        return cart

    session_key = _get_session_key(request)
    cart, _ = Cart.objects.get_or_create(
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


class CartView(APIView):
    """GET /api/cart/ — текущая корзина."""

    permission_classes = [AllowAny]

    def get(self, request):
        cart = _get_or_create_active_cart(request)
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
        qs = (
            Order.objects.filter(user=request.user)
            .prefetch_related("items")
            .order_by("-created_at")
        )
        return Response(OrderSerializer(qs, many=True).data)


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
        if not token:
            return Response(status=status.HTTP_404_NOT_FOUND)
        order = Order.objects.filter(order_number=number, access_token=token, user=None).first()
        if order is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(OrderSerializer(order).data)


class InvoiceView(APIView):
    """HTML-счёт для B2B-заказа. Для гостя — по токену."""

    permission_classes = [AllowAny]

    def get(self, request, number):
        token = request.query_params.get("t", "")
        user = request.user if request.user.is_authenticated else None

        if user:
            order = Order.objects.filter(order_number=number, user=user).first()
        elif token:
            order = Order.objects.filter(order_number=number, access_token=token, user=None).first()
        else:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if order is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

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
        return HttpResponse(html, content_type="text/html")
