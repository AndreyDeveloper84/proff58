"""Публичный эндпоинт приёма заявок по товару (create-only, без auth, throttled)."""

from __future__ import annotations

from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle

from .serializers import ProductInquirySerializer


class ProductInquiryCreateView(generics.CreateAPIView):
    serializer_class = ProductInquirySerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "inquiry"
