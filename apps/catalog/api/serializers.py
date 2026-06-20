"""Сериализаторы публичного API каталога (read-only)."""

from rest_framework import serializers

from apps.pricing.services import RETAIL, price_for

from ..models import Product
from ..services import attr_value_to_json


def _money(value):
    """Decimal → строка (как DRF рендерит DecimalField), либо None."""
    return None if value is None else str(value)


def _image_url(image, context) -> str | None:
    """Абсолютный URL изображения; None если файла нет."""
    if not image:
        return None
    try:
        url = image.image.url
    except ValueError:
        return None
    request = context.get("request") if context else None
    return request.build_absolute_uri(url) if request is not None else url


class CategoryRefSerializer(serializers.Serializer):
    name = serializers.CharField()
    slug = serializers.CharField()


class ProductImageSerializer(serializers.Serializer):
    url = serializers.SerializerMethodField()
    alt = serializers.CharField()
    is_main = serializers.BooleanField()

    def get_url(self, obj):
        return _image_url(obj, self.context)


class ProductListSerializer(serializers.ModelSerializer):
    category = CategoryRefSerializer(read_only=True)
    main_image = serializers.SerializerMethodField()
    price_type = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "slug",
            "brand",
            "category",
            "price",
            "old_price",
            "currency",
            "price_type",
            "stock_status",
            "main_image",
            "short_description",
        )

    def get_main_image(self, obj):
        images = list(obj.images.all())  # prefetched — без новых запросов
        if not images:
            return None
        main = next((i for i in images if i.is_main), images[0])
        return _image_url(main, self.context)

    def get_price_type(self, obj):
        return ""  # реальное значение проставляется в to_representation (один price_for на товар)

    def to_representation(self, instance):
        """Цену отдаём ТОЛЬКО через pricing (ADR-0006).

        В листинге view кладёт в context bulk ``price_map`` (опт-цены одним
        запросом) — берём готовый PriceResult оттуда. Вне листинга (карточка и
        пр.) ``price_map`` нет — фолбэк на поэлементный ``price_for``: для
        B2C/анонима без БД (Product.price), для B2B — 1 запрос.
        """
        data = super().to_representation(instance)
        request = self.context.get("request")
        user = getattr(request, "user", None) if request is not None else None
        price_map = self.context.get("price_map")
        if price_map is not None and instance.pk in price_map:
            result = price_map[instance.pk]
        else:
            result = price_for(instance, user)
        data["price"] = _money(result.final)
        data["old_price"] = (
            _money(instance.old_price) if result.price_type == RETAIL and result.discount else None
        )
        data["currency"] = result.currency
        data["price_type"] = result.price_type
        return data


class ProductDetailSerializer(ProductListSerializer):
    images = serializers.SerializerMethodField()
    attributes = serializers.SerializerMethodField()
    breadcrumb = serializers.SerializerMethodField()

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + (
            "description",
            "images",
            "attributes",
            "breadcrumb",
        )

    def get_images(self, obj):
        return ProductImageSerializer(obj.images.all(), many=True, context=self.context).data

    def get_attributes(self, obj):
        return [
            {
                "name": pav.attribute.name,
                "slug": pav.attribute.slug,
                "unit": pav.attribute.unit,
                "value": attr_value_to_json(pav),
            }
            for pav in obj.attribute_values.all()  # prefetched
        ]

    def get_breadcrumb(self, obj):
        if obj.category_id is None:
            return []
        cat = obj.category
        crumbs = [{"name": c.name, "slug": c.slug} for c in cat.get_ancestors()]
        crumbs.append({"name": cat.name, "slug": cat.slug})
        return crumbs
