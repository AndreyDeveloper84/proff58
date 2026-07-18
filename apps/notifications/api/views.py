"""API preferences и истории уведомлений (#515). Владелец — только request.user,
других id в путях нет, поэтому доступ к чужим данным конструктивно невозможен."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Notification
from ..services import get_or_create_preference
from .serializers import NotificationPreferenceSerializer, NotificationSerializer


class NotificationPreferenceView(APIView):
    """GET/PATCH /api/account/notifications/preferences/."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        pref = get_or_create_preference(request.user)
        return Response(NotificationPreferenceSerializer(pref).data)

    def patch(self, request):
        pref = get_or_create_preference(request.user)
        serializer = NotificationPreferenceSerializer(pref, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class NotificationListView(generics.ListAPIView):
    """GET /api/account/notifications/ — история, пагинация по умолчанию (LimitOffset)."""

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by("-created_at")


class NotificationUnreadCountView(APIView):
    """GET /api/account/notifications/unread-count/."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(user=request.user, read_at__isnull=True).count()
        return Response({"unread_count": count})


class NotificationMarkReadView(APIView):
    """POST /api/account/notifications/<id>/read/. 404 — не 403, чтобы не палить
    существование чужого id (тот же приём, что MaxAuthStatusView)."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, user=request.user)
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])
        return Response(NotificationSerializer(notification).data)


class NotificationMarkAllReadView(APIView):
    """POST /api/account/notifications/read-all/."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        updated = Notification.objects.filter(user=request.user, read_at__isnull=True).update(
            read_at=timezone.now()
        )
        return Response({"marked": updated}, status=status.HTTP_200_OK)
