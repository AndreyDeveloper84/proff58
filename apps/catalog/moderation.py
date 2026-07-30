"""Конвейер модерации: один товар — заполнить — опубликовать — следующий.

Разбор каталога — самая объёмная ручная работа в проекте (тысячи товаров без
категории и характеристик). В обычном списке это выглядит как навигация:
открыть товар, проскроллить форму из семи блоков, сохранить, вернуться в
список, найти следующий. Конвейер убирает навигацию: на экране один товар,
только те поля, которых ему не хватает, и три кнопки.

Здесь — очередь и работа с данными; отрисовка и маршрут в admin.py.
"""

from __future__ import annotations

from django import forms
from django.db import transaction

from apps.core.events import EventSource, product_updated

from . import queues
from .models import (
    AttributeType,
    Category,
    CategoryAttribute,
    Product,
    ProductAttributeValue,
    ProductStatus,
    Source,
)

# Поле PAV, в которое пишется значение, по типу характеристики.
_VALUE_FIELD = {
    AttributeType.INTEGER: "value_integer",
    AttributeType.DECIMAL: "value_decimal",
    AttributeType.BOOLEAN: "value_boolean",
    AttributeType.SELECT: "value_option",
    AttributeType.MULTISELECT: "value_option",
    AttributeType.TEXT: "value_text",
}


def queue():
    """Очередь модерации — та же выборка, что за счётчиком «Требуют внимания»."""
    return queues.needs_attention().order_by("id")


def next_product(after_id: int | None = None) -> Product | None:
    """Следующий товар очереди. ``after_id`` — тот, который только что закрыли."""
    qs = queue()
    if after_id:
        found = qs.filter(id__gt=after_id).first()
        if found is not None:
            return found
    return qs.first()


def attribute_field(category_attribute: CategoryAttribute) -> forms.Field:
    """Поле формы под тип характеристики."""
    attribute = category_attribute.attribute
    label = attribute.name + (f", {attribute.unit}" if attribute.unit else "")
    common = {"label": label, "required": False}

    if attribute.attribute_type == AttributeType.INTEGER:
        return forms.IntegerField(**common)
    if attribute.attribute_type == AttributeType.DECIMAL:
        return forms.DecimalField(**common)
    if attribute.attribute_type == AttributeType.BOOLEAN:
        return forms.NullBooleanField(**common)
    if attribute.attribute_type in (AttributeType.SELECT, AttributeType.MULTISELECT):
        return forms.ModelChoiceField(queryset=attribute.options.all(), **common)
    return forms.CharField(**common)


class ModerationForm(forms.Form):
    """Форма одного шага конвейера: категория, витринные тексты, характеристики.

    Поля характеристик строятся под категорию товара, поэтому форма создаётся
    на каждый товар заново. Обязательные идут первыми и помечены звёздочкой в
    подписи — но `required=False` сознательно: человек должен иметь возможность
    сохранить черновик и уйти, а недостачу поймает публикация.
    """

    ATTR_PREFIX = "attr_"

    category = forms.ModelChoiceField(
        queryset=Category.objects.none(), required=False, label="Категория"
    )
    card_name = forms.CharField(required=False, label="Название для плитки каталога")
    short_description = forms.CharField(
        required=False, label="Короткое описание", widget=forms.Textarea(attrs={"rows": 3})
    )

    def __init__(self, *args, product: Product, **kwargs):
        super().__init__(*args, **kwargs)
        self.product = product
        self.fields["category"].queryset = Category.objects.filter(is_active=True).order_by("path")
        self.fields["category"].initial = product.category_id
        self.fields["card_name"].initial = product.card_name
        self.fields["short_description"].initial = product.short_description

        self.attribute_rows: list[tuple[str, CategoryAttribute]] = []
        # Поля строим по категории ИЗ ФОРМЫ, а не из сохранённого товара: человек
        # выбирает категорию и заполняет её характеристики в один приём. Если
        # смотреть на product.category_id, при первом сохранении полей ещё нет —
        # значит, введённое молча теряется.
        category_id = self._submitted_category_id() or product.category_id
        if not category_id:
            return

        existing = {pav.attribute_id: pav for pav in product.attribute_values.all()}
        links = (
            CategoryAttribute.objects.filter(category_id=category_id)
            .select_related("attribute")
            .order_by("-is_required", "sort_order", "attribute__name")
        )
        for link in links:
            name = f"{self.ATTR_PREFIX}{link.attribute_id}"
            field = attribute_field(link)
            if link.is_required:
                field.label = f"{field.label} *"
            pav = existing.get(link.attribute_id)
            if pav is not None:
                value_field = _VALUE_FIELD.get(link.attribute.attribute_type, "value_text")
                field.initial = getattr(pav, value_field, None)
            self.fields[name] = field
            self.attribute_rows.append((name, link))

    def _submitted_category_id(self) -> int | None:
        """Категория из присланных данных (до валидации — полей ещё нет)."""
        if not self.is_bound:
            return None
        raw = self.data.get(self.add_prefix("category"))
        try:
            return int(raw) if raw else None
        except (TypeError, ValueError):
            return None

    @property
    def attribute_fields(self):
        """Связанные поля характеристик — шаблону нужен BoundField, а не имя."""
        return [self[name] for name, _ in self.attribute_rows]

    def apply(self) -> Product:
        """Сохранить введённое. Значения характеристик считаются подтверждёнными
        человеком — source=manual, confidence=100 (то же правило, что в админке
        значений характеристик)."""
        product = self.product
        data = self.cleaned_data

        changed: list[str] = []
        if data.get("category") and data["category"].pk != product.category_id:
            product.category = data["category"]
            product.category_is_manual = True  # авторазбор 1С это больше не тронет
            changed += ["category", "category_is_manual"]
        for field in ("card_name", "short_description"):
            if data.get(field) is not None and data[field] != getattr(product, field):
                setattr(product, field, data[field])
                changed.append(field)
        if changed:
            product.save(update_fields=[*changed, "updated_at"])

        for name, link in self.attribute_rows:
            value = data.get(name)
            value_field = _VALUE_FIELD.get(link.attribute.attribute_type, "value_text")
            if value in (None, ""):
                ProductAttributeValue.objects.filter(
                    product=product, attribute_id=link.attribute_id
                ).delete()
                continue
            ProductAttributeValue.objects.update_or_create(
                product=product,
                attribute_id=link.attribute_id,
                defaults={
                    value_field: value,
                    "source": Source.MANUAL,
                    "confidence": 100,
                },
            )
        return product


def publish(product: Product, *, actor_id: int | None = None) -> list[str]:
    """Опубликовать товар. Возвращает список причин, если публиковать нельзя."""
    product.refresh_from_db()
    errors = product.publication_errors()
    if errors:
        return errors
    product.status = ProductStatus.PUBLISHED
    product.is_active = True
    product.save(update_fields=["status", "is_active", "updated_at"])
    _emit(product.pk, ["status", "is_active"])
    return []


def send_to_review(product: Product) -> None:
    """Отложить товар: он останется в очереди, но помечен как просмотренный."""
    if product.status != ProductStatus.NEEDS_REVIEW:
        product.status = ProductStatus.NEEDS_REVIEW
        product.save(update_fields=["status", "updated_at"])
        _emit(product.pk, ["status"])


def _emit(product_id: int, fields: list[str]) -> None:
    transaction.on_commit(
        lambda: product_updated.send(
            sender=Product,
            product_id=product_id,
            source=EventSource.ADMIN,
            changed_fields=fields,
        )
    )
