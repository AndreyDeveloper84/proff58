"""Админка заказов и корзины (минимальная для #26)."""

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from .fulfillment import advance_fulfillment, next_steps
from .models import B2BInvoice, Cart, CartItem, FulfillmentStatus, Order, OrderItem
from .transitions import allowed_transitions, can_transition


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        "product",
        "code_1c",
        "article",
        "name",
        "unit",
        "price_base",
        "price_final",
        "discount",
        "price_type",
        "currency",
        "quantity",
        "line_total",
    )
    can_delete = False


class OrderAdminForm(forms.ModelForm):
    """Форма заказа, знающая матрицу переходов обработки.

    До этого админка была единственным местом, где `fulfillment_status` менялся
    в обход `transitions.py`: обмен с 1С и жизненный цикл счёта матрицу
    соблюдают, а ручная правка поля — нет. Итог — «Выполнен» → «Новый» и
    «Отменён» → «В доставке» сохранялись молча.
    """

    class Meta:
        model = Order
        # Состав полей всё равно задаёт ModelAdmin.get_form (он исключает
        # readonly_fields), базовой форме перечислять их незачем.
        fields = "__all__"  # noqa: DJ007

    def clean_fulfillment_status(self):
        new = self.cleaned_data["fulfillment_status"]
        if not self.instance.pk:
            return new  # новый заказ — двигать нечего
        # На момент clean_<field> instance ещё хранит значение из БД: поля формы
        # переносятся в объект позже, в _post_clean.
        old = self.instance.fulfillment_status
        if can_transition(old, new):
            return new

        labels = dict(FulfillmentStatus.choices)
        targets = allowed_transitions(old)
        allowed = ", ".join(sorted(str(labels[t]) for t in targets))
        message = f"Из статуса «{labels[old]}» нельзя перевести в «{labels[new]}»."
        message += f" Допустимо: {allowed}." if allowed else " Это конечный статус."
        raise forms.ValidationError(message)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    form = OrderAdminForm
    change_form_template = "admin/orders/order/change_form.html"
    list_display = (
        "order_number",
        "created_at",
        "customer",
        "total_money",
        "status_badge",
        "next_action",
    )
    list_filter = ("fulfillment_status", "payment_status", "sync_1c_status", "customer_type")
    search_fields = ("order_number", "customer_name", "customer_phone", "inn")
    # «Заказы за сегодня» без этого было нечем отфильтровать.
    date_hierarchy = "created_at"
    save_on_top = True
    # user — autocomplete (UserAdmin.search_fields есть), слот — raw_id
    # (у DeliverySlotAdmin поиска нет). Оба поля рендерили полный селект.
    autocomplete_fields = ("user",)
    raw_id_fields = ("delivery_slot",)
    inlines = [OrderItemInline]
    # Заказ хранит СНИМКИ на момент оформления: правка их руками не пересчитывает
    # строки и разъезжается с платежом и выгрузкой в 1С. Поэтому снимок промо и
    # доставки, разбивка НДС, скидки, номер, резерв, токен и поля, которые пишет
    # 1С, — только для чтения.
    #
    # ВНЕ этого списка сознательно оставлены `total`, `delivery_cost`,
    # `delivery_zone` и `delivery_calc_status`: при delivery_calc_status=
    # manual_required стоимость доставки определяет менеджер (см. help_text поля),
    # и сегодня админка — единственное место, где это делается. Пересчёта итогов
    # вне place_order пока нет, так что заморозка total обрубила бы живой сценарий.
    # Правильное решение — действие «Указать стоимость доставки», которое зовёт
    # сервис; до него поля остаются редактируемыми.
    readonly_fields = (
        "display_status",
        "status_panel",
        "history",
        "fulfillment_status",
        "order_number",
        "promo_code",
        "promo_snapshot",
        "items_discount_total",
        "delivery_discount",
        "delivery_snapshot",
        "delivery_slot_snapshot",
        "vat_rate",
        "vat_amount",
        "amount_without_vat",
        "currency",
        "reservation_status",
        "reserved_until",
        "external_order_id",
        "external_order_number",
        "exported_at",
        "access_token",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            None,
            {
                "description": (
                    "Обработка двигается кнопками выше — они зовут доменный сервис "
                    "(проверка перехода, возврат резерва при отмене, уведомление "
                    "покупателю). Поле «Обработка» показано только для справки."
                ),
                "fields": ("status_panel", "fulfillment_status", "payment_status", "comment"),
            },
        ),
        (
            "Покупатель",
            {
                "fields": (
                    "user",
                    "customer_name",
                    "customer_phone",
                    "customer_email",
                    "customer_type",
                )
            },
        ),
        (
            "Организация (B2B)",
            {
                "classes": ("collapse",),
                "fields": ("company_name", "inn", "kpp", "legal_address"),
            },
        ),
        (
            "Доставка",
            {
                "description": (
                    "При «Требуется ручной расчёт» стоимость доставки определяете вы: "
                    "введите её здесь и поправьте сумму заказа."
                ),
                "fields": (
                    "delivery_method",
                    "delivery_address",
                    "delivery_zone",
                    "delivery_cost",
                    "delivery_calc_status",
                    "delivery_slot",
                    "tracking_number",
                ),
            },
        ),
        (
            "Деньги — снимок на момент оформления",
            {
                "fields": (
                    "total",
                    "currency",
                    "items_discount_total",
                    "delivery_discount",
                    "promo_code",
                    "vat_rate",
                    "vat_amount",
                    "amount_without_vat",
                    "payment_method",
                ),
            },
        ),
        (
            "Резерв склада и выгрузка в 1С",
            {
                "fields": (
                    "reservation_status",
                    "reserved_until",
                    "sync_1c_status",
                    "exported_at",
                    "external_order_id",
                    "external_order_number",
                ),
            },
        ),
        ("История изменений", {"fields": ("history",)}),
        (
            "Техническая информация",
            {
                "classes": ("collapse",),
                "fields": (
                    "order_number",
                    "access_token",
                    "promo_snapshot",
                    "delivery_snapshot",
                    "delivery_slot_snapshot",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    # ------------------------------------------------------------------ список

    @admin.display(description="Покупатель")
    def customer(self, obj):
        phone = obj.customer_phone or (obj.user.phone if obj.user_id else "")
        name = obj.customer_name or (obj.user.full_name if obj.user_id else "") or "—"
        return format_html("{}<br><span style='opacity:.6;'>{}</span>", name, phone or "—")

    @admin.display(description="Сумма", ordering="total")
    def total_money(self, obj):
        return f"{obj.total} {obj.currency}"

    @admin.display(description="Статус")
    def status_badge(self, obj):
        """Один человекочитаемый статус вместо четырёх технических.

        Оси оплаты и выгрузки остаются, но мелкой подписью: менеджеру нужен
        ответ «что с заказом», а не три равнозначных поля.
        """
        return format_html(
            "<b>{}</b><br><span style='opacity:.6;font-size:.85em;'>оплата: {} · 1С: {}</span>",
            obj.display_status,
            obj.get_payment_status_display(),
            obj.get_sync_1c_status_display(),
        )

    @admin.display(description="Что сделать")
    def next_action(self, obj):
        """Кнопки следующего допустимого шага прямо в списке."""
        steps = next_steps(obj)
        if not steps:
            return format_html("<span style='opacity:.5;'>—</span>")
        return format_html_join(
            " ",
            '<a class="button" style="padding:.15rem .5rem;font-size:.85em;{}" href="{}">{}</a>',
            (
                (
                    (
                        "background:#dc3545;border-color:#dc3545;"
                        if value == FulfillmentStatus.CANCELLED
                        else ""
                    ),
                    reverse("admin:orders_order_advance", args=[obj.pk, value]),
                    label,
                )
                for value, label in steps
            ),
        )

    # ---------------------------------------------------------------- карточка

    @admin.display(description="Статус заказа")
    def status_panel(self, obj):
        """Шапка карточки: где заказ и куда его можно двинуть."""
        if obj is None or obj.pk is None:
            return "—"
        steps = next_steps(obj)
        buttons = (
            format_html_join(
                " ",
                '<a class="button" style="margin-right:.4rem;{}" href="{}">{}</a>',
                (
                    (
                        (
                            "background:#dc3545;border-color:#dc3545;"
                            if value == FulfillmentStatus.CANCELLED
                            else ""
                        ),
                        reverse("admin:orders_order_advance", args=[obj.pk, value]),
                        label,
                    )
                    for value, label in steps
                ),
            )
            if steps
            else mark_safe(
                "<span style='opacity:.6;'>Заказ в конечном статусе.</span>"
            )  # noqa: S308
        )
        return format_html(
            "<div style='padding:.6rem .8rem;border-radius:.4rem;"
            "background:rgba(128,128,128,.08);max-width:44rem;'>"
            "<div style='font-size:1.15rem;font-weight:700;margin-bottom:.1rem;'>{}</div>"
            "<div style='opacity:.65;font-size:.88rem;margin-bottom:.55rem;'>"
            "оплата: {} · выгрузка в 1С: {} · резерв: {}</div>{}</div>",
            obj.display_status,
            obj.get_payment_status_display(),
            obj.get_sync_1c_status_display(),
            obj.get_reservation_status_display(),
            buttons,
        )

    @admin.display(description="Кто и что менял")
    def history(self, obj):
        """Журнал правок из админки (django LogEntry) — «кто поставил этот статус».

        Раньше ответа на этот вопрос не было нигде.
        """
        if obj is None or obj.pk is None:
            return "—"
        entries = (
            LogEntry.objects.filter(
                content_type=ContentType.objects.get_for_model(Order), object_id=str(obj.pk)
            )
            .select_related("user")
            .order_by("-action_time")[:20]
        )
        if not entries:
            return mark_safe(
                "<span style='opacity:.6;'>Правок из админки пока не было.</span>"
            )  # noqa: S308
        return format_html_join(
            "",
            "<div style='margin:.15rem 0;'>" "<span style='opacity:.6;'>{}</span> — {} — {}</div>",
            (
                (
                    timezone.localtime(e.action_time).strftime("%d.%m.%Y %H:%M"),
                    e.user.get_username() if e.user else "система",
                    e.get_change_message() or e.object_repr,
                )
                for e in entries
            ),
        )

    # ------------------------------------------------------------------ кнопки

    def get_urls(self):
        return [
            path(
                "<int:order_id>/advance/<str:target>/",
                self.admin_site.admin_view(self.advance_view),
                name="orders_order_advance",
            ),
            *super().get_urls(),
        ]

    def advance_view(self, request, order_id, target):
        """Перевод статуса: GET — страница подтверждения, POST — сам переход.

        Меняем состояние только на POST. Ссылка-переход по GET двигала бы заказ
        от случайного клика или префетча браузера, а тут денежный контур и
        уведомление покупателю. Заодно на подтверждении объясняем последствия —
        как того и требует согласованный принцип «сначала объясни, потом делай».
        """
        if not self.has_change_permission(request):
            raise PermissionDenied

        order = self.get_object(request, str(order_id))
        if order is None:
            self.message_user(request, "Заказ не найден.", level=messages.ERROR)
            return redirect("admin:orders_order_changelist")

        labels = dict(FulfillmentStatus.choices)
        if request.method != "POST":
            consequences = ["Покупатель получит уведомление о новом статусе."]
            if target == FulfillmentStatus.CANCELLED:
                consequences.insert(0, "Резерв товаров вернётся в свободный остаток.")
                consequences.append("Отмена необратима — статус конечный.")
            context = {
                **self.admin_site.each_context(request),
                "title": f"Заказ {order.order_number}",
                "order": order,
                "target_label": labels.get(target, target),
                "consequences": consequences,
                "is_cancel": target == FulfillmentStatus.CANCELLED,
                "back_url": reverse("admin:orders_order_change", args=[order.pk]),
            }
            return TemplateResponse(request, "admin/orders/order/advance_confirm.html", context)

        try:
            order = advance_fulfillment(order_id, target, actor_id=request.user.pk)
        except ValidationError as exc:
            self.message_user(request, "; ".join(exc.messages), level=messages.ERROR)
        else:
            self.log_change(request, order, f"Обработка → {order.get_fulfillment_status_display()}")
            self.message_user(
                request,
                f"Заказ {order.order_number}: {order.display_status}.",
                level=messages.SUCCESS,
            )
        return redirect("admin:orders_order_change", order_id)

    @admin.display(description="Статус для клиента")
    def display_status(self, obj):
        return obj.display_status


@admin.register(B2BInvoice)
class B2BInvoiceAdmin(admin.ModelAdmin):
    """Счета B2B (#559). Оплату отмечает менеджер action'ом — он ведёт заказ и
    резерв через invoice_lifecycle (paid + confirm), а не правкой полей руками."""

    list_display = ("number", "order", "status", "issued_at", "valid_until", "paid_at")
    list_filter = ("status",)
    search_fields = ("number", "order__order_number", "order__inn", "order__company_name")
    readonly_fields = ("order", "number", "issued_at", "valid_until", "paid_at", "status")
    actions = ["mark_paid"]

    def has_add_permission(self, request):  # счёт создаёт только place_order
        return False

    @admin.action(description="Отметить оплаченным (заказ → оплачен, резерв списан)")
    def mark_paid(self, request, queryset):
        from .invoice_lifecycle import mark_invoice_paid

        done = 0
        for invoice in queryset:
            try:
                mark_invoice_paid(invoice.pk)
                done += 1
            except ValidationError as exc:
                self.message_user(request, "; ".join(exc.messages), level=messages.ERROR)
        if done:
            self.message_user(request, f"Оплачено счетов: {done}.", level=messages.SUCCESS)


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    # Без raw_id каждая строка корзины рендерила селект со ВСЕМ каталогом.
    raw_id_fields = ("product",)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "session_key", "status", "ordered_at", "created_at")
    list_filter = ("status",)
    inlines = [CartItemInline]
