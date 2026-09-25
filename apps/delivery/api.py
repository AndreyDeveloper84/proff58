"""API доставки: доступные зоны и расчёт стоимости (#54)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.throttling import DeliveryLookupRateThrottle

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


def _cdek_unavailable() -> Response:
    return Response(
        {"detail": "Доставка СДЭК сейчас недоступна."}, status=status.HTTP_503_SERVICE_UNAVAILABLE
    )


class CdekCitiesView(APIView):
    """GET /api/delivery/cdek/cities/?q= — подсказки городов России (DRF-2299).

    От двух символов; кеш ответа СДЭК — час. СДЭК выключен или не отвечает — 503.
    """

    permission_classes = [AllowAny]
    throttle_classes = [DeliveryLookupRateThrottle]

    def get(self, request):
        from apps.integration_ship import services as ship
        from apps.integration_ship.providers.cdek import CdekError

        if not ship.cdek_enabled():
            return _cdek_unavailable()
        query = (request.query_params.get("q") or "").strip()[:100]
        try:
            cities = ship.cdek_cities(query)
        except CdekError:
            return _cdek_unavailable()
        return Response(
            {"cities": [{"code": c.code, "name": c.name, "full_name": c.full_name} for c in cities]}
        )


class CdekPointsView(APIView):
    """GET /api/delivery/cdek/points/?city_code= — пункты выдачи СДЭК в городе (DRF-2299)."""

    permission_classes = [AllowAny]
    throttle_classes = [DeliveryLookupRateThrottle]

    def get(self, request):
        from apps.integration_ship import services as ship
        from apps.integration_ship.providers.cdek import CdekError

        if not ship.cdek_enabled():
            return _cdek_unavailable()
        try:
            city_code = int(request.query_params.get("city_code") or 0)
        except ValueError:
            city_code = 0
        if city_code <= 0:
            return Response(
                {"detail": "city_code — код города СДЭК."}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            points = ship.cdek_points(city_code)
        except CdekError:
            return _cdek_unavailable()
        return Response(
            {
                "points": [
                    {
                        "code": p.code,
                        "name": p.name,
                        "address": p.address,
                        "work_time": p.work_time,
                        "latitude": p.latitude,
                        "longitude": p.longitude,
                    }
                    for p in points
                ]
            }
        )
