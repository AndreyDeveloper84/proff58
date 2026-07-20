"""API доставки: доступные зоны и расчёт стоимости (#54)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import calculate
from .slots import available_slots


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


class DeliverySlotsView(APIView):
    """GET /api/delivery/slots/ — доступные слоты доставки для checkout (#569).

    Query params:
        zone: slug зоны доставки (зональные слоты видны только своей зоне;
              глобальные, без зоны, — всем).

    Отдаёт только активные будущие слоты со свободными местами в горизонте
    DELIVERY_SLOT_HORIZON_DAYS. places_left наружу не отдаём: свободность
    решается сервером в момент оформления, а не обещанием в листинге.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        slots = available_slots(zone_slug=request.query_params.get("zone") or "")
        return Response(
            {
                "slots": [
                    {
                        "id": slot.pk,
                        "date": slot.date.isoformat(),
                        "starts_at": slot.starts_at.strftime("%H:%M"),
                        "ends_at": slot.ends_at.strftime("%H:%M"),
                    }
                    for slot in slots
                ]
            }
        )
