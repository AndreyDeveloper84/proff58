"""Запуск оплаты заказа с витрины.

Почему отдельная вьюха, а не шаг внутри создания заказа: заказ должен быть создан
и сохранён независимо от того, доступна ли касса. Если ЮKassa лежит или ключи не
настроены, покупатель не теряет оформленный заказ — он видит его в статусе
«ожидает оплаты» и повторяет попытку той же кнопкой. Этой же вьюхой оплата
повторяется позже: ``create_payment`` идемпотентен по номеру заказа, поэтому
повторный вызов возвращает существующий платёж и ту же ссылку, а не плодит новые.

Доступ: владелец заказа либо гость по номеру + токену (``?t=``) — тот же контракт,
что у ``GuestOrderView``; чужой заказ по одному номеру не оплатить.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders import services as order_services
from apps.orders.models import FulfillmentStatus, Order
from apps.orders.models import PaymentStatus as OrderPaymentStatus

from . import refund_requests
from .models import RefundReason, RefundRequest
from .services import create_payment

logger = logging.getLogger(__name__)

# Оплатить нельзя то, что уже не едет: отменённый заказ ссылку на оплату получать
# не должен, иначе деньги приходят за то, чего не будет.
_UNPAYABLE_FULFILLMENT = {FulfillmentStatus.CANCELLED}

# Способ оплаты заказа — снимок выбора на витрине ("online"/"invoice"), а не код
# провайдера: онлайн-касса у заказа одна, и её название в поле не хранится.
ONLINE_PAYMENT_METHOD = "online"


def _resolve_order(request, number: str) -> Order | None:
    """Заказ, к которому у запросившего есть доступ: владелец или гость с токеном."""
    if request.user.is_authenticated:
        order = Order.objects.filter(order_number=number, user=request.user).first()
        if order is not None:
            return order
    token = request.query_params.get("t", "") or str(request.data.get("access_token", ""))
    return order_services.get_guest_order_by_token(number, token)


class OrderPaymentView(APIView):
    """POST /api/payments/orders/{number}/ — получить ссылку на оплату заказа."""

    permission_classes = [AllowAny]

    def post(self, request, number):
        if not getattr(settings, "PAYMENTS_ENABLED", False):
            return Response(
                {"detail": "Онлайн-оплата временно недоступна.", "code": "payments_disabled"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        order = _resolve_order(request, number)
        if order is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if order.payment_method != ONLINE_PAYMENT_METHOD:
            return Response(
                {"detail": "Этот заказ оплачивается не онлайн.", "code": "not_online"},
                status=status.HTTP_409_CONFLICT,
            )

        if order.payment_status == OrderPaymentStatus.PAID:
            # Не ошибка: покупатель мог вернуться по старой ссылке уже после оплаты.
            return Response({"payment_status": order.payment_status, "confirmation_url": ""})

        if order.fulfillment_status in _UNPAYABLE_FULFILLMENT:
            return Response(
                {"detail": "Заказ отменён, оплатить его нельзя.", "code": "canceled"},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            payment = create_payment(order)
        except Exception:
            # Касса недоступна или не настроена. Заказ уже оформлен и никуда не
            # делся — отвечаем «попробуйте ещё раз», а не 500 с пустым экраном.
            logger.exception("Не удалось создать платёж для заказа %s", order.order_number)
            return Response(
                {
                    "detail": "Не удалось перейти к оплате. Заказ сохранён — попробуйте позже.",
                    "code": "provider_unavailable",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "payment_status": order.payment_status,
                "confirmation_url": payment.confirmation_url,
                "provider_status": payment.status,
            }
        )


def _refund_state(order: Order) -> dict:
    """Что покупатель видит в блоке «Возврат денег» карточки заказа."""
    blocked = refund_requests.block_reason(order)
    deadline = refund_requests.request_deadline(order)
    history = RefundRequest.objects.filter(order=order).select_related("refund")[:5]
    return {
        "can_request": blocked is None,
        # Причину отказа показываем, только когда есть что объяснить: у заказа
        # с оплатой при получении блока возврата не должно быть вовсе.
        "block_reason": (
            blocked if order.payment_status in refund_requests.REFUNDABLE_ORDER else None
        ),
        "deadline": deadline.isoformat() if deadline else None,
        "reasons": [{"value": value, "label": str(label)} for value, label in RefundReason.choices],
        "requests": [
            {
                "id": r.pk,
                "status": r.status,
                "status_label": r.get_status_display(),
                "reason": r.reason,
                "reason_label": r.get_reason_display(),
                "comment": r.comment,
                "amount": str(r.refund.amount) if r.refund else None,
                "decision_comment": r.decision_comment,
                "created_at": r.created_at.isoformat(),
                "decided_at": r.decided_at.isoformat() if r.decided_at else None,
            }
            for r in history
        ],
    }


class RefundRequestView(APIView):
    """GET/POST /api/payments/orders/{number}/refund-request/ — заявка на возврат.

    Только владелец заказа (гостю нечем подтвердить, что деньги вернуть надо
    именно ему). Правила — в ``refund_requests``; «сейчас нельзя» — 409 с текстом.
    """

    permission_classes = [IsAuthenticated]

    def _order(self, request, number):
        return Order.objects.filter(order_number=number, user=request.user).first()

    def get(self, request, number):
        order = self._order(request, number)
        if order is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(_refund_state(order))

    def post(self, request, number):
        order = self._order(request, number)
        if order is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        reason = str(request.data.get("reason", ""))
        comment = str(request.data.get("comment", ""))
        if reason not in RefundReason.values:
            return Response(
                {"detail": "Выберите причину возврата."}, status=status.HTTP_400_BAD_REQUEST
            )
        if reason == RefundReason.OTHER and not comment.strip():
            return Response(
                {"detail": "Опишите, пожалуйста, причину возврата."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            refund_requests.create_request(
                order.pk, user_id=request.user.pk, reason=reason, comment=comment
            )
        except DjangoValidationError as exc:
            return Response({"detail": " ".join(exc.messages)}, status=status.HTTP_409_CONFLICT)
        order.refresh_from_db()
        return Response(_refund_state(order), status=status.HTTP_201_CREATED)
