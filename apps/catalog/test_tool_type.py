"""Тесты движка извлечения tool_type и витрины каталога."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.test import TestCase

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    EnrichmentResult,
    ImportRun,
    Product,
    ProductAttributeValue,
)
from apps.catalog.tool_type import (
    ASSIGNED,
    MODERATION,
    RECATEGORIZE,
    ToolTypeRules,
    normalize,
    transliterate,
)

RULES = {
    "version": 1,
    "categories": [
        {
            "category": "Электроинструмент",
            "extraction": "priority_keyword",
            "rules": [
                {
                    "tool_type": "Перфораторы",
                    "slug": "perforatory",
                    "match_keywords": ["перфоратор"],
                },
                {
                    "tool_type": "Дрели и шуруповёрты",
                    "slug": "dreli",
                    "match_keywords": ["дрель", "шуруповерт"],
                },
                {
                    "tool_type": "⚠ Сварка",
                    "slug": "_recat_weld",
                    "match_keywords": ["сварочн"],
                    "action": "recategorize",
                },
            ],
        },
        {
            "category": "Оснастка и расходники",
            "extraction": "inherit_1c_subgroup",
            "rules": [
                {"tool_type": "Сверла", "slug": "sverla", "source": "1c_subgroup"},
                {
                    "tool_type": "Переходные кольца",
                    "slug": "perehodnye-koltsa",
                    "subgroup": "Сверла",
                    "match_keywords": ["кольцо переходн"],
                },
            ],
        },
    ],
}


class ExtractionEngineTests(TestCase):
    def setUp(self):
        self.rules = ToolTypeRules.from_dict(RULES)

    def test_normalize_yo_and_case(self):
        self.assertEqual(normalize("ПёрфоратоР"), "перфоратор")

    def test_priority_first_match_wins(self):
        # «перфоратор» стоит первым правилом и выигрывает, даже если есть «дрель».
        ex = self.rules.extract("Электроинструмент", "Перфоратор-дрель Bosch")
        self.assertEqual(ex.result, ASSIGNED)
        self.assertEqual(ex.slug, "perforatory")
        self.assertEqual(ex.matched_keyword, "перфоратор")

    def test_yo_in_name_matches(self):
        ex = self.rules.extract("Электроинструмент", "Шуруповёрт аккумуляторный")
        self.assertEqual(ex.result, ASSIGNED)
        self.assertEqual(ex.slug, "dreli")

    def test_recategorize_sets_no_tool_type(self):
        ex = self.rules.extract("Электроинструмент", "Аппарат сварочный инверторный")
        self.assertEqual(ex.result, RECATEGORIZE)
        self.assertEqual(ex.slug, "_recat_weld")

    def test_no_match_is_moderation(self):
        ex = self.rules.extract("Электроинструмент", "Удлинитель силовой 50м")
        self.assertEqual(ex.result, MODERATION)

    def test_inherit_subgroup(self):
        ex = self.rules.extract("Оснастка и расходники", "Сверло по металлу 5мм", subgroup="Свёрла")
        self.assertEqual(ex.result, ASSIGNED)
        self.assertEqual(ex.tool_type, "Свёрла")
        self.assertEqual(ex.slug, "sverla")  # канонический slug по нормализованному совпадению

    def test_inherit_keyword_override_inside_subgroup(self):
        # «Кольцо переходное» в подгруппе «Сверла» → свой tool_type, а не sverla.
        ex = self.rules.extract(
            "Оснастка и расходники", "Кольцо переходное 20х16", subgroup="Сверла"
        )
        self.assertEqual(ex.result, ASSIGNED)
        self.assertEqual(ex.slug, "perehodnye-koltsa")

    def test_inherit_override_does_not_touch_plain_items(self):
        # Обычное сверло в той же подгруппе override не задевает → sverla.
        ex = self.rules.extract("Оснастка и расходники", "Сверло по металлу 5мм", subgroup="Сверла")
        self.assertEqual(ex.slug, "sverla")

    def test_inherit_override_is_scoped_to_its_subgroup(self):
        # Тот же ключ в ДРУГОЙ подгруппе («Буры») не срабатывает (скоуп по subgroup).
        ex = self.rules.extract("Оснастка и расходники", "Кольцо переходное 20х16", subgroup="Буры")
        self.assertEqual(ex.tool_type, "Буры")
        self.assertNotEqual(ex.slug, "perehodnye-koltsa")

    def test_options_exclude_recategorize(self):
        opts = self.rules.options("Электроинструмент")
        slugs = {o.slug for o in opts}
        self.assertIn("perforatory", slugs)
        self.assertNotIn("_recat_weld", slugs)


class StorefrontTests(TestCase):
    def setUp(self):
        self.root = Category.add_root(
            name="Электроинструмент", slug="elektroinstrument", on_site=True
        )
        self.leaf = self.root.add_child(name="Сетевой инструмент", slug="setevoy", on_site=True)
        self.attr = Attribute.objects.create(
            slug="tool_type",
            name="Тип инструмента",
            attribute_type=AttributeType.SELECT,
            is_filterable=True,
        )
        self.opt = AttributeOption.objects.create(
            attribute=self.attr, value="Перфораторы", slug="perforatory"
        )
        self.p1 = Product.objects.create(
            code_1c="1",
            name="Перфоратор Bosch",
            category=self.leaf,
            stock_quantity=5,
            attrs_cache={"tool_type": "Перфораторы"},
        )
        ProductAttributeValue.objects.create(
            product=self.p1, attribute=self.attr, value_option=self.opt
        )
        # товар без tool_type (модерация), без остатка
        self.p2 = Product.objects.create(
            code_1c="2",
            name="Удлинитель",
            category=self.leaf,
            stock_quantity=0,
        )

    def test_index_lists_top_category(self):
        r = self.client.get("/catalog/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Электроинструмент")

    def test_category_shows_tool_type_tile_and_products(self):
        r = self.client.get("/catalog/elektroinstrument/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Перфораторы")  # плитка tool_type
        self.assertContains(r, "tool_type=perforatory")  # ссылка-фасет
        self.assertContains(r, "⚠ модерация")  # бейдж у p2

    def test_tool_type_filter(self):
        r = self.client.get("/catalog/elektroinstrument/", {"tool_type": "perforatory"})
        self.assertContains(r, "Перфоратор Bosch")
        self.assertNotContains(r, "Удлинитель")

    def test_in_stock_filter(self):
        r = self.client.get("/catalog/elektroinstrument/", {"in_stock": "1"})
        self.assertContains(r, "Перфоратор Bosch")
        self.assertNotContains(r, "Удлинитель")


class LogModelsTests(TestCase):
    def test_import_run_str_and_stats(self):
        run = ImportRun.objects.create(source="catalog_fixed.json", stats={"products_imported": 10})
        self.assertIn("catalog_fixed.json", str(run))
        self.assertEqual(run.stats["products_imported"], 10)

    def test_enrichment_result_choices(self):
        self.assertEqual(set(EnrichmentResult.values), {"assigned", "moderation", "recategorize"})


class RealRulesRegressionTests(TestCase):
    """Регресс на реальном data/tool_type_rules.json."""

    def test_diamond_discs_subgroup_maps_to_canonical_slug(self):
        # Имя подгруппы в правиле выровнено с категорией сайта «Алмазные круги».
        # Иначе inherit не матчит → фолбэк-slug (tip-N) → характеристики дисков
        # (disc_diameter/bore/disc_type) не извлекаются. См. фикс tip-5 → krugi-almaznye.
        rules = ToolTypeRules.from_file(Path(settings.BASE_DIR) / "data" / "tool_type_rules.json")
        ex = rules.extract(
            "Оснастка и расходники", "Круг алмаз. отрез. 125х1,2х10х22,23", "Алмазные круги"
        )
        self.assertEqual(ex.result, ASSIGNED)
        self.assertEqual(ex.slug, "krugi-almaznye")

    def test_osnastka_subgroups_have_canonical_slugs(self):
        # Имена правил выровнены с категориями сайта (как #185), иначе inherit падает
        # в tip-N, который теперь публичен в URL фасетов (?attr_tool_type=tip-N).
        rules = ToolTypeRules.from_file(Path(settings.BASE_DIR) / "data" / "tool_type_rules.json")
        expected = {
            "Отрезные и шлифовальные круги": "krugi-shlif",
            "Наборы бит и насадок": "nabory-bit",
            "Развёртки и фрезы": "razvertki-frezy",
            "Прочая оснастка": "prochaya-osnastka",
        }
        for subgroup, slug in expected.items():
            ex = rules.extract("Оснастка и расходники", "товар", subgroup)
            self.assertEqual(ex.result, ASSIGNED, subgroup)
            self.assertEqual(ex.slug, slug, subgroup)

    def test_diamond_disc_accessories_split_by_keyword(self):
        # Аксессуары внутри подгруппы «Алмазные круги» получают свой tool_type,
        # не засоряя фасет отрезных дисков (D).
        rules = ToolTypeRules.from_file(Path(settings.BASE_DIR) / "data" / "tool_type_rules.json")
        cases = {
            "Кольцо переходное 22,23х20 для дисков": "perehodnye-koltsa",
            "Чашка алмазная 125 мм KRAFTOOL двухрядная": "chashki-shlif",
            "Головка алмазная шлифовальная d95 АЛАТОН": "golovki-shlif",
            "Франкфурт шлифовальный GFB 00": "golovki-shlif",
            "Приспособление для алмазного сверления": "prisposobleniya-osnastka",
            # сами отрезные/дисковые круги остаются krugi-almaznye
            "Круг алмаз. отрез. 125х1,4х10х22,23 1A1R Turbo": "krugi-almaznye",
            "Круг алмазный 11V9 125х40х20 Tyrolit": "krugi-almaznye",
        }
        for name, slug in cases.items():
            ex = rules.extract("Оснастка и расходники", name, "Алмазные круги")
            self.assertEqual(ex.slug, slug, name)

    def test_bury_subtypes_split_from_masonry_bits(self):
        # Внутри подгруппы «Буры» наборы/удлинители/садовые отделяются, бур остаётся bury.
        rules = ToolTypeRules.from_file(Path(settings.BASE_DIR) / "data" / "tool_type_rules.json")

        def slug(name):
            return rules.extract("Оснастка и расходники", name, "Буры").slug

        self.assertEqual(slug("Бур 6х110 SDS PLUS СЕБ"), "bury")
        self.assertEqual(slug("Набор буров SDS-plus 7 шт. Uragan"), "nabory-burov")
        self.assertEqual(slug("Удлинитель для бура SDS-plus 300мм ЗУБР"), "osnastka-burov")
        self.assertEqual(slug("Бур садовый шнековый, 1085 мм"), "sadovye-bury")

    def test_koronki_subtypes_split(self):
        # «Коронки»: наборы и оснастка (адаптеры/удлинители/центр.свёрла) отделяются.
        rules = ToolTypeRules.from_file(Path(settings.BASE_DIR) / "data" / "tool_type_rules.json")

        def slug(name):
            return rules.extract("Оснастка и расходники", name, "Коронки").slug

        self.assertEqual(slug("Коронка 65мм по бетону SDS+ СЕБ"), "koronki")
        self.assertEqual(slug("Набор буровых коронок 5шт 33,50,68,82,100мм"), "nabory-koronok")
        self.assertEqual(slug("Адаптер для алмазных коронок KRAFTOOL М16"), "osnastka-koronok")
        self.assertEqual(slug("Удлинитель для коронок 200мм"), "osnastka-koronok")

    def test_sverla_subtypes_split(self):
        # «Сверла»: зенковки/наборы/оснастка отделяются; «сверло с зенкером» — это сверло.
        rules = ToolTypeRules.from_file(Path(settings.BASE_DIR) / "data" / "tool_type_rules.json")

        def slug(name):
            return rules.extract("Оснастка и расходники", name, "Сверла").slug

        self.assertEqual(slug("Сверло по металлу ц/х 6,0 мм Р6М5"), "sverla")
        self.assertEqual(slug("Зенковка к/х 16.0 угол 60"), "zenkovki")
        self.assertEqual(slug("Набор свёрл по металлу 19 шт ЗУБР"), "nabory-sverel")
        self.assertEqual(slug("Удлинитель для сверла 300мм"), "osnastka-sverel")
        # важный негатив: сверло С зенкером — это сверло, не зенковка
        self.assertEqual(slug("Сверло с зенкером для мебельных стяжек 5,0мм"), "sverla")

    def test_tail_osnastka_subtypes_split(self):
        # Хвост Оснастки: целевой тип остаётся, наборы/оснастка отделяются.
        rules = ToolTypeRules.from_file(Path(settings.BASE_DIR) / "data" / "tool_type_rules.json")

        def slug(name, sub):
            return rules.extract("Оснастка и расходники", name, sub).slug

        self.assertEqual(slug("Долото 20х250 SDS+ СЕБ", "Пики и долота"), "piki-dolota")
        self.assertEqual(slug("Набор долот SDS-max 3шт", "Пики и долота"), "nabory-piki")
        self.assertEqual(slug("Бита PH2 25мм ЗУБР", "Биты"), "bity")
        self.assertEqual(slug("Адаптер для бит магнитный 60мм KRAFTOOL", "Биты"), "osnastka-bit")
        self.assertEqual(slug("Полотно по металлу для лобзика", "Пилки и полотна"), "pilki-polotna")
        self.assertEqual(slug("Набор пилок для лобзика 5шт", "Пилки и полотна"), "nabory-pilok")
        self.assertEqual(slug("Резец проходной 16х16 Т15К6", "Резцы"), "reztsy")
        self.assertEqual(slug("Набор резцов 12шт хвост 12мм", "Резцы"), "osnastka-reztsov")

    def test_accessory_overrides_are_subgroup_scoped(self):
        # Override-ключи действуют только в своей подгруппе: «держатель» в «Биты» даёт
        # оснастку для бит (свой тип), а НЕ disc-аксессуар prisposobleniya-osnastka.
        rules = ToolTypeRules.from_file(Path(settings.BASE_DIR) / "data" / "tool_type_rules.json")
        ex = rules.extract("Оснастка и расходники", "Держатель бит для шуруповерта", "Биты")
        self.assertEqual(ex.slug, "osnastka-bit")
        self.assertNotEqual(ex.slug, "prisposobleniya-osnastka")
        # «Коронка ...+переходник» — настоящая коронка (ключ «переходник» убран из koronki).
        ex = rules.extract(
            "Оснастка и расходники", "Коронка алм. 22хМ16 бетон+переходник", "Коронки"
        )
        self.assertEqual(ex.slug, "koronki")

    def test_akkumulyatory_does_not_swallow_cordless_tools(self):
        # Правило «аккумулятор» стоит последним: садовая/прочая техника
        # «аккумуляторная» классифицируется по своему типу, а не как АКБ.
        rules = ToolTypeRules.from_file(Path(settings.BASE_DIR) / "data" / "tool_type_rules.json")

        def res(name):
            return rules.extract("Электроинструмент", name)

        # настоящая АКБ → akkumulyatory
        self.assertEqual(res("Аккумулятор Einhell PXC 18В 4,0А/ч").slug, "akkumulyatory")
        # садовая техника → recategorize (не akkumulyatory)
        self.assertEqual(res("Газонокосилка аккумуляторная ЗУБР ГКЛ-4336").result, RECATEGORIZE)
        self.assertEqual(res("Опрыскиватель аккумуляторный ЗУБР ОПЛ-10").result, RECATEGORIZE)
        # зарядное устройство → zaryadnye
        self.assertEqual(res("Зарядное устройство ЗУБР 14,4-18В для АКБ Li-ion").slug, "zaryadnye")
        # фонарь аккумуляторный → recategorize в свет
        self.assertEqual(res("Фонарь BOSCH GLI 18V-1900 без АКБ и ЗУ").result, RECATEGORIZE)
        # набор аккумуляторного инструмента → nabory-elektro
        self.assertEqual(
            res("Набор аккумуляторного инструмента Metabo Combo").slug, "nabory-elektro"
        )


class TransliterateTests(TestCase):
    """Транслитерация кириллицы для слугов (фолбэк _unique_option_slug, C2)."""

    def test_basic_cyrillic_to_latin(self):
        self.assertEqual(transliterate("Прочая оснастка"), "prochaya osnastka")
        self.assertEqual(transliterate("Щётки"), "schetki")  # щ→sch, ё→e

    def test_latin_and_digits_untouched(self):
        self.assertEqual(transliterate("SDS-MAX 18В"), "sds-max 18v")
