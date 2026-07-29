"""Админка заказов и корзины (минимальная для #26)."""

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError

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
    list_display = (
        "order_number",
        "user",
        "display_status",
        "fulfillment_status",
        "payment_status",
        "sync_1c_status",
        "total",
        "currency",
        "created_at",
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
