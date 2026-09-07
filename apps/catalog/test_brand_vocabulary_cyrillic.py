"""Кириллические алиасы латинских брендов — контракт и границы.

Трек заведён по факту блокера pilot-30: товар «Крестики Remocolor» не
сматчился с источником, потому что у нас бренд латиницей, а у ВИ кириллицей
(«Ремоколор»), и матчер увидел ``article_exact+brand_conflict`` при точном
совпадении артикула.

Добавлены ТОЛЬКО формы, подтверждённые данными каталога. Тесты закрепляют и
то, что добавлено, и то, что сознательно НЕ добавлено: без второго списка
следующее окно легко «дополнит» словарь правдоподобными догадками.

БД не требуется — словарь и его потребители читаются без ORM.
"""

from __future__ import annotations

import pytest

from apps.catalog.brand_identity import decide_brand
from apps.catalog.brand_vocabulary import load_brand_vocabulary
from apps.catalog.taxonomy_audit import _is_brand_node

VOCAB = load_brand_vocabulary()

# Подтверждено вхождениями в названиях каталога, каждое проверено вручную.
CONFIRMED = {
    "ремоколор": "REMOCOLOR",  # 12 вхождений: «Болторез 900 мм РемоКолор»
    "редиус": "REDIUS",  # 5: «АППГ-1 Редиус 168», «Клапан (РЕДИУС)»
    "патриот": "PATRIOT",  # 4: «Мотоблок ПАТРИОТ УРАЛ М»
}

# Сгенерированные транслитерации, отвергнутые при проверке данными.
# Каждая строка — причина отказа, а не просто «не нашли».
REJECTED = {
    "хобби": "единственное вхождение — линейка Husqvarna «Хобби», не бренд HOBBI",
    "спарта": "7 вхождений из 8 — модели обуви «ЛЕДИ СПАРТА», «СПАРТА ТОФ»",
    "крафтул": "в каталоге не встречается — форма не подтверждена",
    "стайер": "в каталоге не встречается",
    "хутер": "в каталоге не встречается",
    "гринда": "в каталоге не встречается",
}


class TestConfirmedAliases:
    @pytest.mark.parametrize("alias,canonical", sorted(CONFIRMED.items()))
    def test_alias_maps_to_canonical(self, alias, canonical):
        assert VOCAB.canonical_by_alias.get(alias) == canonical

    @pytest.mark.parametrize("alias,canonical", sorted(CONFIRMED.items()))
    def test_latin_form_survives(self, alias, canonical):
        """Кириллица добавлена рядом с латиницей, а не вместо неё."""
        assert VOCAB.canonical_by_alias.get(canonical.casefold()) == canonical

    def test_real_catalog_names_now_resolve(self):
        cases = [
            ("Болторез 900 мм РемоКолор", "REMOCOLOR"),
            ("Круг алмаз. отрез. 125х22,2 ТУРБО РемоКолор", "REMOCOLOR"),
            ("АППГ-1 Редиус 168", "REDIUS"),
            ("Клапан обратный КО-3-К31 (РЕДИУС)", "REDIUS"),
            ("Мотоблок ПАТРИОТ УРАЛ М бензиновый", "PATRIOT"),
        ]
        for name, canonical in cases:
            decision = decide_brand(name)
            assert canonical in decision.manufacturers, name


class TestRejectedForms:
    """Отвергнутые формы обязаны остаться вне словаря.

    Тест защищает не от опечатки, а от соблазна: все шесть форм выглядят
    правдоподобно, и без явного списка их легко добавить «за компанию».
    """

    @pytest.mark.parametrize("alias,reason", sorted(REJECTED.items()))
    def test_not_in_vocabulary(self, alias, reason):
        assert alias not in VOCAB.canonical_by_alias, reason

    def test_husqvarna_line_is_not_brand_hobbi(self):
        decision = decide_brand('Набор заточной Husqvarna "Хобби" 3/8 мм')
        assert "HOBBI" not in decision.manufacturers

    def test_sparta_footwear_is_not_brand_sparta(self):
        decision = decide_brand("Полуботинки ЛЕДИ СПАРТА цв. чер. термопласт ПУ р38")
        assert "SPARTA" not in decision.manufacturers


class TestNoRegressionForOtherConsumers:
    def test_category_tree_untouched(self):
        """F4 не должен начать считать категории узлами-брендов.

        Замер на стенде: узлов-брендов 5 → 5, ни одного добавленного.
        """
        for name in (
            "Мешки для пылесосов",
            "Перчатки и рукавицы",
            "Ручной инструмент",
            "Ящики для инструмента",
            "Леска для триммера",
        ):
            assert not _is_brand_node(name), name

    def test_existing_cyrillic_brands_unaffected(self):
        assert VOCAB.canonical_by_alias.get("зубр") == "ЗУБР"
        assert "ЗУБР" in decide_brand("Бинт строительный ЗУБР 1240-06-30").manufacturers

    def test_change_is_additive_only(self):
        """Ни один прежний алиас не потерян и не переназначен."""
        for alias, canonical in (
            ("remocolor", "REMOCOLOR"),
            ("redius", "REDIUS"),
            ("patriot", "PATRIOT"),
            ("kraftool", "KRAFTOOL"),
            ("makita", "MAKITA"),
            ("зубр", "ЗУБР"),
        ):
            assert VOCAB.canonical_by_alias.get(alias) == canonical
