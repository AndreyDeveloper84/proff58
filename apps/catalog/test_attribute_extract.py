"""Тесты движка извлечения характеристик и обогащения (Фаза B, #96)."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from apps.catalog.attribute_extract import (
    CONFIDENCE_KEYWORD,
    CONFIDENCE_REGEX,
    AttributeRules,
)
from apps.catalog.models import (
    Attribute,
    AttributeType,
    Category,
    CategoryAttribute,
    FilterKind,
    Product,
    ProductAttributeValue,
)
from apps.catalog.source_priority import Source

# Мини-словарь правил, повторяющий структуру data/attribute_rules.json.
RULES = {
    "version": 1,
    "tool_types": [
        {
            "tool_type": "Дрели и шуруповёрты",
            "slug": "dreli-shurupoverty",
            "category": "Электроинструмент",
            "attributes": [
                {
                    "slug": "voltage",
                    "name": "Напряжение",
                    "kind": "number",
                    "unit": "В",
                    "filter_kind": "range",
                    "patterns": [
                        r"(\d+(?:[.,]\d+)?)\s*-?\s*вольт",
                        r"(\d+(?:[.,]\d+)?)\s*в\b",
                        r"(\d+(?:[.,]\d+)?)\s*v\b",
                    ],
                },
                {
                    "slug": "torque",
                    "name": "Момент",
                    "kind": "number",
                    "unit": "Н·м",
                    "filter_kind": "range",
                    "patterns": [
                        r"(\d+(?:[.,]\d+)?)\s*н[·.\s]?м\b",
                        r"(\d+(?:[.,]\d+)?)\s*n\s*m\b",
                    ],
                },
                {
                    "slug": "battery_included",
                    "name": "АКБ в комплекте",
                    "kind": "boolean",
                    "rules": {
                        "false": ["без акб", "без зу и акб", "body", "solo"],
                        "true": ["с акб", "2 акб"],
                    },
                },
                {
                    "slug": "power_source",
                    "name": "Питание",
                    "kind": "select",
                    "is_seo_facet": True,
                    "options": [
                        {
                            "value": "Аккумуляторный",
                            "slug": "akkumulyatornyy",
                            "keywords": ["аккумуляторн", "акб"],
                        },
                        {"value": "Сетевой", "slug": "setevoy", "keywords": ["сетев"]},
                    ],
                },
                {
                    "slug": "motor_type",
                    "name": "Двигатель",
                    "kind": "select",
                    "options": [
                        {
                            "value": "Бесщёточный",
                            "slug": "beschetochnyy",
                            "keywords": ["бесщеточн", "brushless"],
                        },
                        {"value": "Щёточный", "slug": "schetochnyy", "keywords": ["щеточн"]},
                    ],
                },
            ],
        }
    ],
}

TT = "Дрели и шуруповёрты"


def _by_slug(values):
    return {v.spec.slug: v for v in values}


class NumberExtractionTests(SimpleTestCase):
    def setUp(self):
        self.rules = AttributeRules.from_dict(RULES)

    def _voltage(self, name):
        v = _by_slug(self.rules.extract_all(TT, name)).get("voltage")
        return v.decimal if v else None

    def _torque(self, name):
        v = _by_slug(self.rules.extract_all(TT, name)).get("torque")
        return v.decimal if v else None

    def test_voltage_variants(self):
        self.assertEqual(self._voltage("Шуруповёрт 18В"), 18)
        self.assertEqual(self._voltage("Шуруповёрт 18 В"), 18)
        self.assertEqual(self._voltage("Дрель GSR 18V-50"), 18)
        self.assertEqual(self._voltage("Дрель 20V Max"), 20)
        self.assertEqual(self._voltage("Шуруповёрт 12V"), 12)
        self.assertEqual(self._voltage("Аккумулятор 14.4В"), 14.4)
        self.assertEqual(self._voltage("18-вольтовый шуруповёрт"), 18)
        self.assertEqual(self._voltage("Дрель 18 вольт"), 18)

    def test_torque_variants(self):
        self.assertEqual(self._torque("Момент 55 Нм"), 55)
        self.assertEqual(self._torque("Момент 55Нм"), 55)
        self.assertEqual(self._torque("Drill 55 Nm"), 55)
        self.assertEqual(self._torque("Drill 55NM"), 55)
        self.assertEqual(self._torque("Момент 55 Н·м"), 55)

    def test_number_source_and_confidence(self):
        v = _by_slug(self.rules.extract_all(TT, "Шуруповёрт 18В"))["voltage"]
        self.assertEqual(v.source, Source.NAME_REGEX)
        self.assertEqual(v.confidence, CONFIDENCE_REGEX)

    def test_no_number_means_no_value(self):
        self.assertIsNone(self._voltage("Шуруповёрт аккумуляторный"))


class BooleanBatteryOrderTests(SimpleTestCase):
    """Порядок правил: негативные ДО позитивных (правка ревью №9)."""

    def setUp(self):
        self.rules = AttributeRules.from_dict(RULES)

    def _battery(self, name):
        v = _by_slug(self.rules.extract_all(TT, name)).get("battery_included")
        return v.boolean if v else None

    def test_bez_akb_i_zu_is_false_not_true(self):
        # Ключевой кейс конфликта: «без АКБ и ЗУ» НЕ должно стать True.
        self.assertIs(self._battery("Шуруповёрт без АКБ и ЗУ"), False)

    def test_bez_akb_is_false(self):
        self.assertIs(self._battery("Дрель-шуруповёрт без АКБ"), False)

    def test_body_and_solo_are_false(self):
        self.assertIs(self._battery("Шуруповёрт DCD777 body"), False)
        self.assertIs(self._battery("Гайковёрт solo"), False)

    def test_s_akb_is_true(self):
        self.assertIs(self._battery("Дрель с АКБ"), True)
        self.assertIs(self._battery("Шуруповёрт 2 АКБ в кейсе"), True)

    def test_no_mention_means_no_value(self):
        self.assertIsNone(self._battery("Дрель ударная 18В"))


class SelectExtractionTests(SimpleTestCase):
    def setUp(self):
        self.rules = AttributeRules.from_dict(RULES)

    def _value(self, slug, name):
        v = _by_slug(self.rules.extract_all(TT, name)).get(slug)
        return v.option_value if v else None

    def test_power_source(self):
        self.assertEqual(self._value("power_source", "Шуруповёрт аккумуляторный"), "Аккумуляторный")
        self.assertEqual(self._value("power_source", "Дрель сетевая 600Вт"), "Сетевой")

    def test_brushless_not_matched_as_brushed(self):
        # «бесщёточный» содержит подстроку «щёточн» — порядок вариантов важен.
        self.assertEqual(self._value("motor_type", "Бесщёточный двигатель"), "Бесщёточный")
        self.assertEqual(self._value("motor_type", "Brushless дрель"), "Бесщёточный")

    def test_brushed(self):
        self.assertEqual(self._value("motor_type", "Щёточный мотор"), "Щёточный")

    def test_select_source_and_confidence(self):
        v = _by_slug(self.rules.extract_all(TT, "Дрель сетевая"))["power_source"]
        self.assertEqual(v.source, Source.NAME_KEYWORD)
        self.assertEqual(v.confidence, CONFIDENCE_KEYWORD)


class ConfidenceValidatorTests(TestCase):
    def test_out_of_range_confidence_rejected(self):
        cat = Category.add_root(name="Электроинструмент", slug="ei")
        attr = Attribute.objects.create(
            slug="voltage", name="Напряжение", attribute_type=AttributeType.DECIMAL
        )
        product = Product.objects.create(name="Дрель", category=cat)
        pav = ProductAttributeValue(
            product=product, attribute=attr, value_decimal=18, confidence=999
        )
        with self.assertRaises(ValidationError):
            pav.full_clean()


class RangeFilterStorefrontTests(TestCase):
    def setUp(self):
        self.root = Category.add_root(
            name="Электроинструмент", slug="elektroinstrument", on_site=True
        )
        self.attr = Attribute.objects.create(
            slug="voltage",
            name="Напряжение",
            attribute_type=AttributeType.DECIMAL,
            unit="В",
            is_filterable=True,
        )
        CategoryAttribute.objects.create(
            category=self.root,
            attribute=self.attr,
            is_filter=True,
            filter_kind=FilterKind.RANGE,
        )
        self.p18 = self._product("Дрель 18В", 18)
        self.p20 = self._product("Дрель 20В", 20)

    def _product(self, name, voltage):
        p = Product.objects.create(name=name, category=self.root, stock_quantity=1)
        ProductAttributeValue.objects.create(
            product=p, attribute=self.attr, value_decimal=voltage, source=Source.NAME_REGEX
        )
        return p

    def test_range_filter_narrows_to_match(self):
        r = self.client.get(
            "/catalog/elektroinstrument/", {"voltage_min": "18", "voltage_max": "18"}
        )
        self.assertContains(r, "Дрель 18В")
        self.assertNotContains(r, "Дрель 20В")

    def test_no_range_shows_all(self):
        r = self.client.get("/catalog/elektroinstrument/")
        self.assertContains(r, "Дрель 18В")
        self.assertContains(r, "Дрель 20В")


class EnrichAttributesCommandTests(TestCase):
    """Интеграция: команда обогащения на реальном data/attribute_rules.json."""

    def setUp(self):
        self.root = Category.add_root(
            name="Электроинструмент", slug="elektroinstrument", on_site=True
        )
        call_command("load_attributes")  # реальный словарь из data/
        self.product = Product.objects.create(
            name="Шуруповёрт аккумуляторный 18В 55 Нм без АКБ бесщёточный",
            original_name="Шуруповёрт аккумуляторный 18В 55 Нм без АКБ бесщёточный",
            category=self.root,
            attrs_cache={"tool_type": "Дрели и шуруповёрты"},
        )

    def test_enrich_sets_values_and_respects_manual(self):
        voltage = Attribute.objects.get(slug="voltage")
        # Ручное значение напряжения — авто-обогащение его трогать НЕ должно.
        ProductAttributeValue.objects.create(
            product=self.product, attribute=voltage, value_decimal=99, source=Source.MANUAL
        )

        call_command("enrich_attributes")

        def pav(slug):
            return ProductAttributeValue.objects.get(
                product=self.product, attribute__slug=slug
            )

        # Напряжение защищено источником manual.
        self.assertEqual(float(pav("voltage").value_decimal), 99)
        self.assertEqual(pav("voltage").source, Source.MANUAL)
        # Остальное проставлено из названия.
        self.assertEqual(float(pav("torque").value_decimal), 55)
        self.assertIs(pav("battery_included").value_boolean, False)
        self.assertEqual(pav("power_source").value_option.value, "Аккумуляторный")
        self.assertEqual(pav("motor_type").value_option.value, "Бесщёточный")
        # attrs_cache (read-model) обновлён.
        self.product.refresh_from_db()
        self.assertEqual(self.product.attrs_cache["torque"], 55)
        self.assertEqual(self.product.attrs_cache["power_source"], "Аккумуляторный")
        self.assertIs(self.product.attrs_cache["battery_included"], False)
