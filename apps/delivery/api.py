"""API доставки: доступные зоны и расчёт стоимости (#54)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import calculate


class DeliveryZonesView(APIView):
    """GET /api/delivery/zones/ — список активных зон с рассчитанной стоимостью.

    Query params:
        cart_total: сумма корзины (Decimal) для расчёта бесплатной доставки.
        zone: slug конкретной зоны (опционально, для уточнения стоимости).
    """

    permission_classes = [AllowAny]

    def get(self, request):
        raw_total = request.query_params.get("cart_total", "0")
        try:
            cart_total = Decimal(raw_total)
            if cart_total < 0:
                raise InvalidOperation
        except InvalidOperation:
            return Response(
                {"detail": "cart_total должен быть неотрицательным числом."}, status=400
            )

        zone_slug = request.query_params.get("zone") or None
        zones = calculate(zone_slug=zone_slug, cart_total=cart_total)
        return Response({"zones": zones})
