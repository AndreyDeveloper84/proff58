"""Сериализаторы публичного API каталога (read-only)."""

from django.conf import settings
from rest_framework import serializers

from apps.pricing.services import RETAIL, price_for

from ..models import Product, StockStatus
from ..services import attr_value_to_json

# Сколько характеристик отдаём в листинге (карточке хватает 3-5; не раздуваем PLP).
CARD_ATTRS_LIMIT = 10


def _money(value):
    """Decimal → строка (как DRF рендерит DecimalField), либо None."""
    return None if value is None else str(value)


def _attr_dict(pav):
    """Характеристика товара для API: {name, slug, unit, value} (value типизирован)."""
    return {
        "name": pav.attribute.name,
        "slug": pav.attribute.slug,
        "unit": pav.attribute.unit,
        "value": attr_value_to_json(pav),
    }


def _image_url(image, _context=None) -> str | None:
    """URL изображения относительно корня сайта (``/media/…``); None если файла нет.

    Раньше здесь стоял ``request.build_absolute_uri()``, и это ломало витрину:
    Next.js рендерит страницы на сервере, ходит в Django по внутреннему адресу
    ``http://web:8000`` — и в HTML уезжал ``https://web:8000/media/...``, который
    браузер не может разрешить (битые фото во всём каталоге и на карточке
    товара). Хост запрашивающего вообще не должен попадать в контент: витрина и
    media отдаются одним nginx, поэтому относительный путь разрешается верно и
    у браузера, и у SSR. Абсолютный URL нужен только разметке для поисковиков —
    её достраивает фронт (components/product/ProductJsonLd.tsx).
    """
    if not image:
        return None
    try:
        return image.image.url
    except ValueError:
        return None


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
    attributes = serializers.SerializerMethodField()
    stock_qty = serializers.SerializerMethodField()
    is_hit = serializers.SerializerMethodField()
    card_name = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "card_name",
            "slug",
            "brand",
            "category",
            "price",
            "old_price",
            "currency",
            "price_type",
            "stock_status",
            "stock_qty",
            "main_image",
            "short_description",
            "attributes",
            "is_hit",
        )

    def get_card_name(self, obj) -> str:
        """Название для плитки каталога — короткое, с сокращениями как в 1С.

        Полное название («Круг алмазный отрезной 115х1,0…») в плитку не влезает:
        там две строки мелким шрифтом. Пусто — товар ещё не проходил
        normalize_product_names, показываем витринное имя как есть.
        """
        return obj.card_name or obj.name

    def get_is_hit(self, obj) -> bool:
        """Бейдж «Хит»: факт продаж (apps.catalog.sales) либо отметка магазина.

        Строки рейтинга у большинства товаров нет, поэтому обращаемся осторожно:
        OneToOne без записи бросает исключение, а не отдаёт None. Запрос не
        добавляем — sales_stat приходит через select_related выдачи.
        """
        stat = getattr(obj, "sales_stat", None)
        return bool((stat and stat.is_hit) or obj.is_hit_manual)

    def get_stock_qty(self, obj):
        """Остаток для сигнала «мало осталось» (#488).

        Отдаём число ТОЛЬКО когда товар в наличии и остаток невелик
        (0 < qty ≤ CATALOG_LOW_STOCK_THRESHOLD) — иначе null (не раскрываем точные
        большие остатки). Фронт по наличию числа показывает «Мало осталось».
        """
        if obj.stock_status != StockStatus.IN_STOCK:
            return None
        threshold = getattr(settings, "CATALOG_LOW_STOCK_THRESHOLD", 5)
        qty = obj.available_quantity or 0
        return int(qty) if 0 < qty <= threshold else None

    def get_attributes(self, obj):
        """Ключевые характеристики для строки спеков карточки (ограничено и упорядочено).

        Только фильтруемые/сравниваемые, по имени, не более ``CARD_ATTRS_LIMIT``. Полный
        набор — в ``ProductDetailSerializer``. Источник — prefetched ``attribute_values``.
        """
        pavs = [
            p
            for p in obj.attribute_values.all()
            if p.attribute.is_filterable or p.attribute.is_comparable
        ]
        pavs.sort(key=lambda p: p.attribute.name)
        return [_attr_dict(p) for p in pavs[:CARD_ATTRS_LIMIT]]

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
    breadcrumb = serializers.SerializerMethodField()

    class Meta(ProductListSerializer.Meta):
        # attributes уже в базовом списке; detail отдаёт ПОЛНЫЙ набор (override get_attributes ниже).
        fields = ProductListSerializer.Meta.fields + (
            "description",
            "video_url",
            "images",
            "breadcrumb",
        )

    def get_images(self, obj):
        return ProductImageSerializer(obj.images.all(), many=True, context=self.context).data

    def get_attributes(self, obj):
        return [_attr_dict(pav) for pav in obj.attribute_values.all()]  # все, prefetched

    def get_breadcrumb(self, obj):
        if obj.category_id is None:
            return []
        cat = obj.category
        crumbs = [{"name": c.name, "slug": c.slug} for c in cat.get_ancestors()]
        crumbs.append({"name": cat.name, "slug": cat.slug})
        return crumbs


def serialize_compat_item(item, context) -> dict:
    """Элемент секции совместимости (#79): товар как в листинге + плоское ``note``.

    Цена берётся через ProductListSerializer (context должен содержать price_map,
    собранный одним bulk-запросом по всем товарам секций).
    """
    data = ProductListSerializer(item.product, context=context).data
    data["note"] = item.note
    return data
