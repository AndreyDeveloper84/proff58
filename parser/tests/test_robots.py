"""ИЗО-05: сопоставление путей robots.txt по RFC 9309.

Прежняя реализация (`urllib.robotparser`) сравнивала путь через `startswith`:
`*` в середине правила и `$` на конце не значили ничего, а выигрывало первое
подошедшее правило, а не самое длинное. Медиа-запреты resanta.ru и vihr.su
записаны именно через wildcard — гейт формально «проходил», реально пропуская
запрещённое. Здесь — таблица кейсов на все ветки нового matcher'а.

Сеть не задействована: robots подаётся фетчером-заглушкой.
"""

from __future__ import annotations

import pytest

from parser._fetch_common import RobotsGate, RobotsUnavailableError

# UA режима A (см. parser/client.py); токен продукта — до первого «/»
UA = (
    "proff58-catalog-parser/0.2 (+https://proff58.ru; contact: sktajem95@gmail.com) "
    "characteristics and product images, 1 req/3s"
)


def gate(text: str, *, user_agent: str = UA) -> RobotsGate:
    return RobotsGate(user_agent=user_agent, fetcher=lambda _robots_url: text)


# --- wildcard `*` -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/wa-data/public/site/2/vihr-1000.jpg", False),  # `*` в середине
        ("/wa-data/public/site/2/utake-1000.jpg", False),
        ("/wa-data/public/site/2/resanta-1000.jpg", True),
        ("/wa-data/public/shop/products/1/vihr.jpg", True),  # другой префикс — не правило
    ],
)
def test_star_in_the_middle(path: str, expected: bool):
    text = (
        "User-agent: *\n"
        "Disallow: /wa-data/public/site/*vihr*\n"
        "Disallow: /wa-data/public/site/*utake*\n"
    )
    assert gate(text).can_fetch("https://resanta.ru" + path) is expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://resanta.ru/category/dreli/filter/moshchnost-500/", False),
        ("https://resanta.ru/category/dreli/", True),
        ("https://resanta.ru/product/drel-vihr-500/", False),  # `*-vihr*`
        ("https://resanta.ru/product/drel-resanta-500/", True),
        ("https://resanta.ru/category/dreli/?page=2", False),  # `*?page=*`
        ("https://resanta.ru/category/dreli/?sort=price", False),  # `*/?sort=`
    ],
)
def test_real_resanta_lines(url: str, expected: bool):
    """Реальные строки robots resanta.ru — те самые, что игнорировались."""
    text = (
        "User-agent: *\n"
        "Disallow: /compare/\n"
        "Disallow: */?sort=\n"
        "Disallow: *&sort=\n"
        "Disallow: /search\n"
        "Disallow: *?page=*\n"
        "Disallow: */filter/*\n"
        "Disallow: *-vihr*\n"
        "Disallow: /wa-data/public/site/*vihr*\n"
        "Host: https://resanta.ru/\n"
    )
    assert gate(text).can_fetch(url) is expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://vihr.su/wa-data/public/site/1/resanta-logo.png", False),
        ("https://vihr.su/wa-data/public/site/1/vihr-logo.png", True),
        ("https://vihr.su/category/nasosy/market/", False),  # `*/market/`
        ("https://vihr.su/wa-data/public/shop/themes/vihr/product.js?v=3", False),
        ("https://vihr.su/wa-data/public/shop/themes/vihr/product.js", True),
        ("https://vihr.su/product/nasos-vihr-100/", True),  # у vihr.su нет `*-vihr*`
    ],
)
def test_real_vihr_lines(url: str, expected: bool):
    text = (
        "User-agent: *\n"
        "\n"
        "Disallow: /compare/\n"
        "Disallow: *&sort=\n"
        "Disallow: */filter/*\n"
        "Disallow: */market/\n"
        "Disallow: /wa-data/public/site/*utake*\n"
        "Disallow: /wa-data/public/site/*resanta*\n"
        "Disallow: /wa-data/public/shop/themes/vihr/product.js?\n"
        "Sitemap: https://vihr.su/sitemap-shop.xml\n"
    )
    assert gate(text).can_fetch(url) is expected


# --- якорь `$` ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://e.test/docs/a.pdf", False),
        ("https://e.test/docs/a.pdf?v=2", True),  # `$` — строго конец строки
        ("https://e.test/docs/a.pdfx", True),
    ],
)
def test_dollar_anchors_end(url: str, expected: bool):
    assert gate("User-agent: *\nDisallow: /*.pdf$\n").can_fetch(url) is expected


def test_dollar_in_the_middle_is_literal():
    """`$` — якорь только в самом конце шаблона; в середине это обычный символ."""
    g = gate("User-agent: *\nDisallow: /a$b\n")
    assert g.can_fetch("https://e.test/a$b/c") is False
    assert g.can_fetch("https://e.test/ab") is True


def test_bare_dollar_disallow_blocks_only_root():
    assert gate("User-agent: *\nDisallow: /$\n").can_fetch("https://e.test/") is False
    assert gate("User-agent: *\nDisallow: /$\n").can_fetch("https://e.test/x") is True


# --- приоритет самого длинного правила ------------------------------------------------


def test_longest_rule_wins_allow_after_disallow():
    text = "User-agent: *\nDisallow: /catalog/\nAllow: /catalog/tovar/\n"
    g = gate(text)
    assert g.can_fetch("https://e.test/catalog/tovar/1") is True
    assert g.can_fetch("https://e.test/catalog/prochee/1") is False


def test_longest_rule_wins_regardless_of_order():
    """Порядок строк не решает: `startswith`-реализация тут ошибалась."""
    text = "User-agent: *\nAllow: /p/a/\nDisallow: /p/\n"
    g = gate(text)
    assert g.can_fetch("https://e.test/p/a/1") is True
    assert g.can_fetch("https://e.test/p/b/1") is False


def test_allow_wins_on_equal_length():
    text = "User-agent: *\nDisallow: /x/y\nAllow: /x/y\n"
    assert gate(text).can_fetch("https://e.test/x/y") is True


def test_longest_match_counts_wildcard_rule_too():
    text = "User-agent: *\nDisallow: /images/\nAllow: /images/*/thumb/\n"
    g = gate(text)
    assert g.can_fetch("https://e.test/images/12/thumb/a.jpg") is True
    assert g.can_fetch("https://e.test/images/12/full/a.jpg") is False


# --- пустые значения и мусор ---------------------------------------------------------


def test_empty_disallow_allows_everything():
    assert gate("User-agent: *\nDisallow:\n").can_fetch("https://e.test/any/path") is True


def test_empty_allow_is_ignored_and_does_not_open_everything():
    text = "User-agent: *\nAllow:\nDisallow: /private/\n"
    g = gate(text)
    assert g.can_fetch("https://e.test/private/x") is False
    assert g.can_fetch("https://e.test/public/x") is True


def test_no_robots_rules_at_all_allows():
    assert gate("").can_fetch("https://e.test/anything") is True


def test_comments_and_case_are_ignored():
    text = "USER-AGENT: *   # все\nDISALLOW: /private/  # служебное\n"
    g = gate(text)
    assert g.can_fetch("https://e.test/private/x") is False
    assert g.can_fetch("https://e.test/open/x") is True


def test_rules_before_any_user_agent_are_ignored():
    text = "Disallow: /a/\nUser-agent: *\nDisallow: /b/\n"
    g = gate(text)
    assert g.can_fetch("https://e.test/a/1") is True
    assert g.can_fetch("https://e.test/b/1") is False


# --- группы User-agent ----------------------------------------------------------------


def test_named_group_does_not_apply_to_us():
    """zubr.ru: у Yandex своя группа; нам достаётся `*`."""
    text = (
        "User-agent: Yandex\n"
        "Disallow: /bitrix/\n"
        "Disallow: /catalog/\n"
        "\n"
        "User-Agent: *\n"
        "Disallow: /bitrix/\n"
        "Disallow: *utm*=\n"
    )
    g = gate(text)
    assert g.can_fetch("https://zubr.ru/catalog/dreli/") is True  # запрет только для Yandex
    assert g.can_fetch("https://zubr.ru/bitrix/x") is False
    assert g.can_fetch("https://zubr.ru/catalog/?utm_source=x") is False


def test_named_group_wins_for_matching_agent():
    text = "User-agent: *\nDisallow: /\n\nUser-agent: proff58-catalog-parser\nDisallow: /private/\n"
    g = gate(text)
    assert g.can_fetch("https://e.test/public/x") is True
    assert g.can_fetch("https://e.test/private/x") is False


def test_consecutive_user_agents_share_one_group():
    text = "User-agent: alpha\nUser-agent: proff58-catalog-parser\nDisallow: /shared/\n"
    g = gate(text)
    assert g.can_fetch("https://e.test/shared/x") is False


# --- контур гейта ---------------------------------------------------------------------


def test_robots_unavailable_raises():
    g = RobotsGate(user_agent=UA, fetcher=lambda _url: None)
    with pytest.raises(RobotsUnavailableError):
        g.can_fetch("https://e.test/x")


def test_robots_fetched_once_per_host():
    calls: list[str] = []

    def fetcher(url: str) -> str:
        calls.append(url)
        return "User-agent: *\nDisallow: /private/\n"

    g = RobotsGate(user_agent=UA, fetcher=fetcher)
    assert g.can_fetch("https://e.test/a") is True
    assert g.can_fetch("https://www.e.test/private/b") is False  # www нормализуется
    assert calls == ["https://e.test/robots.txt"]


def test_percent_encoding_matches_on_both_sides():
    """Кириллица в правиле и в URL приводится к одному виду, иначе совпадений нет."""
    g = gate("User-agent: *\nDisallow: /каталог/\n")
    assert g.can_fetch("https://e.test/%D0%BA%D0%B0%D1%82%D0%B0%D0%BB%D0%BE%D0%B3/1") is False
    assert g.can_fetch("https://e.test/catalog/1") is True
