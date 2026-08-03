"""Тесты движка извлечения tool_type и витрины каталога."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management import call_command
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
from apps.catalog.queue_contract import _allowed_tool_type_options
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
                {"tool_type": "Буры", "slug": "bury", "source": "1c_subgroup"},
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

    def test_metchiki_plashki_split(self):
        # «Метчики и плашки»: метчик→metchiki, плашка→plashki, держатели/наборы — в свои типы.
        rules = ToolTypeRules.from_file(Path(settings.BASE_DIR) / "data" / "tool_type_rules.json")

        def slug(name):
            return rules.extract("Оснастка и расходники", name, "Метчики и плашки").slug

        self.assertEqual(slug("Метчик винтовой М 6х1,0 HSS STV"), "metchiki")
        self.assertEqual(slug("Плашка BSW 1/2 12ниток"), "plashki")
        self.assertEqual(slug("Набор метчиков M10 DIN352 (3шт)"), "nabory-metchikov-plashek")
        # важный негатив: «метчик» ⊂ «метчикодержатель» НЕ должен утаскивать держатель в metchiki
        self.assertEqual(slug("Метчикодержатель ЗУБР №1 М1-М10"), "osnastka-rezbonarez")
        self.assertEqual(slug("Плашкодержатель М 12-М 14 DIN225"), "osnastka-rezbonarez")

    def test_krugi_shlif_abrasive_subtypes_split(self):
        # «Отрезные и шлифовальные круги» — сборная подгруппа: круги остаются
        # krugi-shlif, а корщётки/наждачка/шарошки/ленты отделяются в свои типы.
        rules = ToolTypeRules.from_file(Path(settings.BASE_DIR) / "data" / "tool_type_rules.json")

        def slug(name):
            return rules.extract(
                "Оснастка и расходники", name, "Отрезные и шлифовальные круги"
            ).slug

        self.assertEqual(slug("Круг лепестковый КЛТ 125х22,2 P60"), "krugi-shlif")
        self.assertEqual(slug("Корщётка дисковая 125мм витая"), "korshchetki")
        self.assertEqual(slug("Бумага шлифовальная P120 рулон"), "nazhdachka")
        self.assertEqual(slug("Шарошка по металлу 10мм"), "sharoshki")
        self.assertEqual(slug("Лента шлифовальная 75х533 P80"), "lenty-shlif")
        self.assertEqual(slug("Надфиль плоский 160мм"), "nadfili-shlif")

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

    def test_otvertki_sets_split_from_screwdrivers(self):
        # «Наборы отвёрток» отделяются в свой тип (как nabory-shlif в #226): уходят из
        # знаменателя otvertki и получают свой фасет. Одиночные отвёртки остаются otvertki;
        # наборы ключей/головок/бит не воруются — их ловят свои правила раньше по порядку.
        rules = ToolTypeRules.from_file(Path(settings.BASE_DIR) / "data" / "tool_type_rules.json")

        def slug(name):
            return rules.extract("Ручной инструмент", name).slug

        self.assertEqual(slug("Набор отверток 10шт KRAFTOOL X-DRIVE"), "nabory-otvertok")
        self.assertEqual(slug("Набор отвертка 6 предметов Ultra Grip КОБАЛЬТ"), "nabory-otvertok")
        self.assertEqual(slug("Отвертка с набором бит 145 предметов Cablexpert"), "nabory-otvertok")
        # одиночная отвёртка остаётся otvertki
        self.assertEqual(slug("Отвертка диэлектрическая SL5,5х125 KRAFTOOL"), "otvertki")
        self.assertEqual(slug("Отвертка PH2x100 ЗУБР"), "otvertki")
        # негативы: наборы соседних типов не воруются (ловятся своими правилами раньше)
        self.assertEqual(slug("Набор ключей рожковых 8 шт ЗУБР"), "klyuchi-gaechnye")
        self.assertEqual(slug("Набор головок 1/2 24шт"), "golovki")
        self.assertEqual(slug("Набор бит 32 предмета KRAFTOOL"), "nabory-instrumenta")


class KeywordAccessoryGuardRegressionTests(TestCase):
    """Регресс ALIAS-CONFLICT-374 (7 групп/25 товаров): слово-триггер описывает
    аксессуар/цель применения внутри названия основного товара — не должен
    переклассифицировать сам товар. Точные названия — из
    scratchpad/phase8/alias-conflict-374-report.md (продукты 47171-47175,
    29722-29730, 40798-40799, 29829/29833, 32151, 31354, 43112 на staging)."""

    def setUp(self):
        self.rules = ToolTypeRules.from_file(
            Path(settings.BASE_DIR) / "data" / "tool_type_rules.json"
        )

    def test_str_pistolety_not_reclassified_as_germetiki(self):
        # «Пистолет ДЛЯ герметиков» — сам товар пистолет, «герметиков» — цель.
        names = (
            "Пистолет для герметиков ЗУБР 310мл ЗУБР полуоткрытый",
            "Пистолет для герметиков ЗУБР 310мл полукорпусной",
            "Пистолет для герметиков ЗУБР 310мл полукорпусной антикапельная система",
            "Пистолет для герметиков ЗУБР 310мл полукорпусной хромированный",
            "Пистолет для герметиков ЗУБР 310мл скелетный",
        )
        for name in names:
            ex = self.rules.extract("Строительное и отделочное", name)
            self.assertEqual(ex.result, ASSIGNED, name)
            self.assertEqual(ex.slug, "str-pistolety", name)

    def test_krepleniya_ognetushiteley_not_reclassified_as_ognetushiteli(self):
        # «Подставка ПОД огнетушитель» — крепление, не сам огнетушитель.
        names = (
            "Подставка под огнетушитель двойная П-15",
            "Подставка под огнетушитель П-10",
            "Подставка под огнетушитель П-10 красная напольная 175х175х340мм (ОП-1-4, ОУ1-2) до 6,5кг",
            "Подставка под огнетушитель П-15",
            "Подставка под огнетушитель П-15 (собранная)",
            "Подставка под огнетушитель П-15 красная напольная р-р 195х195х380мм (ОП-1-6,ОУ1-2) до 8,2кг",
            "Подставка под огнетушитель П-20 красная напольная 230х230х400мм (ОП-1-8, ОУ-1-4) до 12кг",
            "Подставка под огнетушитель ПО-170 (ПО-01,П-10)",
            "Подставка под огнетушитель универсальная",
        )
        for name in names:
            ex = self.rules.extract("Спецодежда и защита", name)
            self.assertNotEqual(ex.slug, "siz-ognetushiteli", name)

    def test_izm_lupy_not_reclassified_as_ochki(self):
        # «Лупа... (очки)/очки с подсветкой» — форм-фактор лупы, не защитные очки.
        names = (
            "Лупа налобная 20х монокулярная (очки) с подсветкой PL4401 (EL-92)",
            "Лупа налобная 3,5х очки с подсветкой PL4406",
        )
        for name in names:
            ex = self.rules.extract("Спецодежда и защита", name)
            self.assertNotEqual(ex.slug, "siz-ochki", name)

    def test_siz_rukava_not_reclassified_as_golovki(self):
        # «Рукав... с головкой ГР-50 и стволом РС-50» — рукав, не пожарная головка/ствол.
        names = (
            'Рукав пожарный РПК(В)-Н/В-50-1,0-М-УХЛ1 "Классик" (18,5 м) с головкой ГР-50 '
            "Ал и стволом РС-50.01 А",
            'Рукав пожарный РПК(В)-Н/В-50-1,0-М-УХЛ1 "Классик" с головкой ГР-50 Ал и стволом '
            "РС-50.01 А",
        )
        for name in names:
            ex = self.rules.extract("Спецодежда и защита", name)
            self.assertEqual(ex.result, ASSIGNED, name)
            self.assertEqual(ex.slug, "siz-rukava", name)

    def test_zubilo_not_reclassified_as_odezhda(self):
        # «Зубило с пластмассовым фартуком» — встроенный щиток инструмента, не одежда.
        ex = self.rules.extract(
            "Спецодежда и защита", "Зубило с пластмассовым фартуком для защиты руки, с"
        )
        self.assertNotEqual(ex.slug, "siz-odezhda")

    def test_svar_apparaty_not_reclassified_as_perchatki(self):
        # «(маска+краги)» — бонус-комплект, «краги» не делают инвертор перчатками.
        ex = self.rules.extract(
            "Спецодежда и защита", 'Свар. инвертор СВАРОГ MIG 200 "REAL"  Black (маска+краги)'
        )
        self.assertNotEqual(ex.slug, "siz-perchatki")

    def test_str_laki_not_reclassified_as_kisti(self):
        # «Цапон лак ... с кисточкой» — сам товар лак, кисточка — встроенный аппликатор.
        ex = self.rules.extract(
            "Строительное и отделочное",
            "Цапон лак прозрачный с кисточкой 20 мл. TSAP-NO-KIS20 Connector",
        )
        self.assertEqual(ex.result, ASSIGNED)
        self.assertEqual(ex.slug, "str-laki")


class TransliterateTests(TestCase):
    """Транслитерация кириллицы для слугов (фолбэк _unique_option_slug, C2)."""

    def test_basic_cyrillic_to_latin(self):
        self.assertEqual(transliterate("Прочая оснастка"), "prochaya osnastka")
        self.assertEqual(transliterate("Щётки"), "schetki")  # щ→sch, ё→e

    def test_latin_and_digits_untouched(self):
        self.assertEqual(transliterate("SDS-MAX 18В"), "sds-max 18v")


class GapRoutingPhase5Tests(TestCase):
    """Taxonomy changeset (gaps Phase 5): маршрутизация по реальному rules-файлу.

    Две новые option (`krep-shplinty`, `puskovye-provoda`) и два reuse-маршрута
    (32407 → `spetsialnye-klyuchi` в «Крепёж и метизы», 30870 → `svar-klemmy`
    в «Электрика и освещение»). Мачта 24523 сознательно не покрывается — отложена.
    """

    def setUp(self):
        self.rules = ToolTypeRules.from_file(
            Path(settings.BASE_DIR) / "data" / "tool_type_rules.json"
        )

    def _slug(self, top, name):
        ex = self.rules.extract(top, name)
        self.assertEqual(ex.result, ASSIGNED, f"{name!r}: ожидался assigned, получен {ex.result}")
        return ex.slug

    def test_shplinty_names_route_to_krep_shplinty(self):
        # Все шесть активных SKU пула шплинтов (cat=367).
        for name in (
            "Штифт со шплинтом",
            "Набор пружинных шплинтов 150 предметов",
            "Набор шплинтов S головки с фиксацией 150 пр.//СИБРТЕХ",
            "Набор шплинтов S головки х L, 1,6х25,2,3х25,2,3х38,3,1х32,3,",
            "Набор шплинтов S головки х L, 3,2х50,4х64,х4,8х76,х6,4х50,6,",
            "Набор штифтов с головкой и отверстием под шплинт 60 пр.//СИБРТЕХ",
        ):
            self.assertEqual(self._slug("Крепёж и метизы", name), "krep-shplinty", name)

    def test_puskovye_provoda_names(self):
        # Пул пусковых проводов: 27249–27254 (без неактивного 27252).
        for name in (
            "Провода стартовые 2,5 м. 500 Ампер",
            "Провода стартовые 2,5м 300А ЗУБР морозостойкие",
            "Провода стартовые 2м 200А ЗУБР морозостойкие",
            "Провода стартовые 3,0 м. 500 Ампер",
            "Провода стартовые 3м 400А ЗУБР морозостойкие",
        ):
            self.assertEqual(self._slug("Электрика и освещение", name), "puskovye-provoda", name)

    def test_santeh_key_routes_to_spetsialnye_klyuchi(self):
        name = "Ключ для сантехнической арматуры №1 для гаек до 40мм 330мм KRAFTOOL PANZER A"
        self.assertEqual(self._slug("Крепёж и метизы", name), "spetsialnye-klyuchi")

    def test_grounding_cable_routes_to_svar_klemmy(self):
        self.assertEqual(
            self._slug("Электрика и освещение", "Кабель с клеммой заземления"),
            "svar-klemmy",
        )

    def test_shpilka_is_not_shplint(self):
        self.assertEqual(
            self._slug("Крепёж и метизы", "Шпилька резьбовая М8х1000 оцинкованная"),
            "krep-shpilki",
        )

    def test_pusko_zaryadnoe_is_not_puskovye_provoda(self):
        self.assertEqual(
            self._slug("Электрика и освещение", "Пуско-зарядное устройство 12/24В 400А"),
            "pusko-zaryadnye",
        )

    def test_power_cable_is_not_puskovye_provoda(self):
        self.assertEqual(
            self._slug("Электрика и освещение", "Кабель ВВГ-П нг(А)-LS 3х2,5"),
            "kabel-provod",
        )

    def test_crocodile_clamps_accessory_is_not_puskovye_provoda(self):
        # Реальный товар 10664: зажимы — аксессуар к проводам, а не сами провода;
        # «пусковых проводов» (род. падеж) не должно матчиться.
        ex = self.rules.extract(
            "Электрика и освещение",
            "Зажимы (крокодилы) для пусковых проводов Airline L 400А, 14х10,5 см",
        )
        self.assertNotEqual(ex.slug, "puskovye-provoda")

    def test_rozhkovy_klyuch_is_not_spetsialny(self):
        ex = self.rules.extract("Крепёж и метизы", "Ключ рожковый комбинированный 14мм")
        self.assertNotEqual(ex.slug, "spetsialnye-klyuchi")

    def test_svarka_keeps_own_svar_klemmy_route(self):
        # Существующий маршрут в «Сварочном оборудовании» не сломан.
        self.assertEqual(
            self._slug("Сварочное оборудование", "Кабель сварочный КГ 1х25"),
            "svar-klemmy",
        )

    def test_reused_option_values_consistent(self):
        # update_or_create в load_tool_types ключуется по (attribute, value):
        # одинаковый slug обязан нести одинаковое value во всех категориях,
        # иначе появится дубль option.
        values: dict[str, set[str]] = {}
        for cat in self.rules.categories:
            for rule in self.rules.options(cat.category):
                if rule.slug in ("svar-klemmy", "spetsialnye-klyuchi"):
                    values.setdefault(rule.slug, set()).add(rule.tool_type)
        self.assertEqual(values["svar-klemmy"], {"Клеммы, зажимы, кабели"})
        self.assertEqual(values["spetsialnye-klyuchi"], {"Специальные ключи"})


class LoadToolTypesGapOptionsTests(TestCase):
    """load_tool_types на реальном rules-файле: идемпотентность и allowed_options export."""

    def test_second_run_creates_nothing_and_gap_options_exported(self):
        call_command("load_tool_types")
        attr = Attribute.objects.get(slug="tool_type")
        first = AttributeOption.objects.filter(attribute=attr).count()

        created = call_command("load_tool_types")

        self.assertEqual(created, "0")
        self.assertEqual(AttributeOption.objects.filter(attribute=attr).count(), first)
        slugs = {o["slug"] for o in _allowed_tool_type_options()}
        for slug in ("krep-shplinty", "puskovye-provoda", "spetsialnye-klyuchi", "svar-klemmy"):
            self.assertIn(slug, slugs)


class LoadToolTypesReuseIdentityTests(TestCase):
    """Reuse существующих DB options: identity строк и sort_order (Wave 7.1/H1).

    load_tool_types материализует options из canonical manifest, ключ — slug:
    существующая запись НЕ дублируется и сохраняет PK/value; sort_order
    по умолчанию НЕ перезаписывается (display metadata), синхронизация —
    только явным ``--update-display``.
    """

    def test_reuse_preserves_pk_value_and_sort_order(self):
        attr = Attribute.objects.create(
            slug="tool_type", name="Тип инструмента", attribute_type=AttributeType.SELECT
        )
        sentinel = 999
        pre = {
            value: AttributeOption.objects.create(
                attribute=attr, value=value, slug=slug, sort_order=sentinel
            )
            for value, slug in (
                ("Специальные ключи", "spetsialnye-klyuchi"),
                ("Клеммы, зажимы, кабели", "svar-klemmy"),
            )
        }

        call_command("load_tool_types")

        for value, opt in pre.items():
            self.assertEqual(
                AttributeOption.objects.filter(attribute=attr, value=value).count(),
                1,
                f"дубль option для {value!r}",
            )
            opt.refresh_from_db()  # тот же PK — новой строки нет
            self.assertEqual(opt.value, value)
            self.assertEqual(
                opt.sort_order,
                sentinel,
                f"{value!r}: sort_order перезаписан без --update-display",
            )

    def test_update_display_syncs_sort_order(self):
        from apps.catalog.taxonomy_manifest import load_manifest

        attr = Attribute.objects.create(
            slug="tool_type", name="Тип инструмента", attribute_type=AttributeType.SELECT
        )
        opt = AttributeOption.objects.create(
            attribute=attr,
            value="Специальные ключи",
            slug="spetsialnye-klyuchi",
            sort_order=999,
        )
        expected = {o.slug: o.sort_order for o in load_manifest().options}["spetsialnye-klyuchi"]

        call_command("load_tool_types", update_display=True)

        opt.refresh_from_db()
        self.assertEqual(opt.sort_order, expected)
        self.assertEqual(
            AttributeOption.objects.filter(attribute=attr, value="Специальные ключи").count(), 1
        )


# --- keyword_at_word_boundary: граница слова с ОБЕИХ сторон (окно CODE-02) ---
#
# В tool_type используется только проверка НАЧАЛА вхождения
# (_keyword_starts_at_word_boundary). Для select-характеристик (attribute_extract)
# нужна и проверка конца — иначе XL матчит XLR. Общая функция живёт рядом с
# исходной механикой и переиспользует _WORD_CHAR, не дублируя её.


def test_keyword_at_word_boundary_requires_both_sides():
    from apps.catalog.tool_type import keyword_at_word_boundary

    # обе границы соблюдены
    assert keyword_at_word_boundary("перчатки xl", "xl")
    assert keyword_at_word_boundary("xl", "xl")  # начало и конец строки — границы
    assert keyword_at_word_boundary("перчатки s-m", "s")  # дефис — граница
    assert keyword_at_word_boundary("перчатки s-m", "m")
    # нарушена граница НАЧАЛА
    assert not keyword_at_word_boundary("stels", "s")
    assert not keyword_at_word_boundary("перчатки ansell", "l")
    # нарушена граница КОНЦА (у tool_type такой проверки нет — новая механика)
    assert not keyword_at_word_boundary("xlr-200", "xl")
    assert not keyword_at_word_boundary("l2000", "l")
    # краевые случаи
    assert not keyword_at_word_boundary("", "xl")
    assert not keyword_at_word_boundary("перчатки xl", "")
