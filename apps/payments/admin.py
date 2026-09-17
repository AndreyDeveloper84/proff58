from decimal import Decimal, InvalidOperation

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from . import refund_requests
from .models import Payment, Refund, RefundRequest, RefundRequestStatus


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("id", "payment", "amount", "currency", "status", "created_at")
    list_filter = ("status", "currency")
    search_fields = ("provider_refund_id", "payment__provider_order_id", "idempotency_key")
    readonly_fields = (
        "payment",
        "amount",
        "currency",
        "status",
        "provider_refund_id",
        "idempotency_key",
        "error_message",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "provider_order_id",
        "order",
        "provider",
        "status",
        "amount",
        "receipt_status",
        "created_at",
    )
    list_filter = ("status", "provider", "method", "receipt_status")
    search_fields = (
        "provider_order_id",
        "provider_payment_id",
        "order__order_number",
    )
    readonly_fields = (
        "provider",
        "provider_order_id",
        "provider_payment_id",
        "order",
        "method",
        "status",
        "amount",
        "currency",
        "confirmation_url",
        "idempotency_key",
        "webhook_payload",
        "paid_at",
        "receipt_id",
        "receipt_status",
        "receipt_error",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False


@admin.register(RefundRequest)
class RefundRequestAdmin(admin.ModelAdmin):
    """Заявки покупателей на возврат денег: менеджер возвращает или отклоняет.

    Деньги двигаются только кнопками (через ``refund_requests``), а не правкой
    полей: поэтому все поля — только для чтения.
    """

    list_display = ("id", "created_at", "order_link", "reason", "amount_paid", "status")
    list_filter = ("status", "reason")
    search_fields = ("order__order_number", "order__customer_name", "order__customer_phone")
    date_hierarchy = "created_at"
    readonly_fields = (
        "decision_panel",
        "order_link",
        "user",
        "reason",
        "comment",
        "status",
        "refund",
        "decision_comment",
        "decided_by",
        "decided_at",
        "created_at",
    )
    fields = readonly_fields

    def has_add_permission(self, request):
        return False  # заявку подаёт только покупатель

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("order", "refund")

    @admin.display(description="Заказ")
    def order_link(self, obj):
        return format_html(
            '<a href="{}">{}</a>',
            reverse("admin:orders_order_change", args=[obj.order_id]),
            obj.order.order_number,
        )

    @admin.display(description="Сумма заказа")
    def amount_paid(self, obj):
        return f"{obj.order.total} {obj.order.currency}"

    @admin.display(description="Решение")
    def decision_panel(self, obj):
        if obj is None or obj.pk is None:
            return "—"
        if obj.status != RefundRequestStatus.PENDING:
            return obj.get_status_display()
        return format_html(
            '<a class="button" style="margin-right:.4rem;" href="{}">Вернуть деньги</a>'
            '<a class="button" style="background:#dc3545;border-color:#dc3545;" href="{}">'
            "Отклонить</a>",
            reverse("admin:payments_refundrequest_decide", args=[obj.pk, "approve"]),
            reverse("admin:payments_refundrequest_decide", args=[obj.pk, "reject"]),
        )

    def get_urls(self):
        return [
            path(
                "<int:request_id>/decide/<str:decision>/",
                self.admin_site.admin_view(self.decide_view),
                name="payments_refundrequest_decide",
            ),
            *super().get_urls(),
        ]

    def decide_view(self, request, request_id, decision):
        """GET — страница подтверждения, POST — возврат или отказ.

        Как и перевод статуса заказа: деньги не двигаются от клика по ссылке.
        """
        if decision not in ("approve", "reject") or not self.has_change_permission(request):
            raise PermissionDenied
        obj = self.get_object(request, str(request_id))
        if obj is None:
            self.message_user(request, "Заявка не найдена.", level=messages.ERROR)
            return redirect("admin:payments_refundrequest_changelist")
        back_url = reverse("admin:payments_refundrequest_change", args=[obj.pk])

        payment = refund_requests.refundable_payment(obj.order)
        remaining = refund_requests.remaining_amount(payment) if payment else Decimal("0")
        error = ""

        if request.method == "POST":
            try:
                if decision == "approve":
                    raw = request.POST.get("amount", "").strip().replace(",", ".")
                    try:
                        amount = Decimal(raw) if raw else None
                    except InvalidOperation:
                        raise ValidationError("Сумма указана неверно.") from None
                    done = refund_requests.approve(obj.pk, amount=amount, actor_id=request.user.pk)
                    text = f"Деньги возвращены: {done.refund.amount} {done.refund.currency}."
                else:
                    refund_requests.reject(
                        obj.pk, comment=request.POST.get("comment", ""), actor_id=request.user.pk
                    )
                    text = "Заявка отклонена, покупатель увидит причину в личном кабинете."
            except ValidationError as exc:
                error = "; ".join(exc.messages)
            else:
                self.log_change(request, obj, text)
                self.message_user(request, text, level=messages.SUCCESS)
                return redirect(back_url)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Заявка на возврат по заказу {obj.order.order_number}",
            "obj": obj,
            "order": obj.order,
            "is_approve": decision == "approve",
            "remaining": remaining,
            "currency": payment.currency if payment else obj.order.currency,
            "has_payment": payment is not None,
            "error": error,
            "form_amount": request.POST.get("amount", ""),
            "form_comment": request.POST.get("comment", ""),
            "back_url": back_url,
        }
        return TemplateResponse(request, "admin/payments/refundrequest/decide.html", context)
