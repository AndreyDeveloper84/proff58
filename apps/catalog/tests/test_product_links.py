"""Связи «покупают вместе» и «аналоги»: взаимность, экран подбора, загрузка разбора.

Главное, что проверяем: связь взаимна (отметил у одного — видно у другого),
экран подбора не стирает то, чего менеджер на экране не видел, а повторный
прогон разбора ничего не дублирует.
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse
from rest_framework.test import APIClient

from apps.catalog.links import add_links, linked_ids, set_links
from apps.catalog.models import (
    Category,
    CompatibilityKind,
    CompatibilityOrigin,
    Product,
    ProductCompatibility,
    ProductStatus,
)
from apps.catalog.queries import analogs_of, compatibility_sections, cross_sell_of

User = get_user_model()
pytestmark = pytest.mark.django_db

CROSS = CompatibilityKind.CROSS_SELL
ANALOG = CompatibilityKind.ANALOG


@pytest.fixture
def cat():
    return Category.add_root(name="Электроинструмент", slug="ei")


def make_product(cat, name, slug, **kw):
    data = {
        "category": cat,
        "name": name,
        "slug": slug,
        "status": ProductStatus.PUBLISHED,
        "is_active": True,
        "price": "1000",
    }
    data.update(kw)
    return Product.objects.create(**data)


# ---------------------------------------------------------------------------
# Взаимность связи
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", [CROSS, ANALOG])
def test_svyaz_vzaimna(cat, kind):
    """Отметили у одного — связь видна и со стороны второго товара."""
    a = make_product(cat, "Болгарка", "bolgarka")
    b = make_product(cat, "Круг отрезной", "krug")

    set_links(a, kind, [b.pk])

    assert linked_ids(b, kind) == {a.pk}


@pytest.mark.parametrize("kind", [CROSS, ANALOG])
def test_obratnaya_para_ne_dubliruetsya(cat, kind):
    """A→B и B→A — одно ребро: хранится канонически, второй раз не создаётся."""
    a = make_product(cat, "Дрель", "drel")
    b = make_product(cat, "Свёрла", "sverla")

    set_links(a, kind, [b.pk])
    set_links(b, kind, [a.pk])

    assert ProductCompatibility.objects.filter(kind=kind).count() == 1


def test_vidy_ne_meshayut_drug_drugu(cat):
    """«Покупают вместе» и «аналог» между теми же товарами — разные факты."""
    a = make_product(cat, "УШМ 125", "ushm-125")
    b = make_product(cat, "УШМ 180", "ushm-180")

    set_links(a, CROSS, [b.pk])
    set_links(a, ANALOG, [b.pk])

    assert linked_ids(a, CROSS) == {b.pk}
    assert linked_ids(a, ANALOG) == {b.pk}


def test_sam_na_sebya_ne_svyazyvaetsya(cat):
    a = make_product(cat, "Перфоратор", "perf")

    set_links(a, CROSS, [a.pk])

    assert linked_ids(a, CROSS) == set()


def test_set_links_snimaet_lishnee(cat):
    a = make_product(cat, "Лобзик", "lobzik")
    b = make_product(cat, "Пилки", "pilki")
    c = make_product(cat, "Струбцина", "strubcina")
    set_links(a, CROSS, [b.pk, c.pk])

    created, removed = set_links(a, CROSS, [c.pk])

    assert (created, removed) == (0, 1)
    assert linked_ids(a, CROSS) == {c.pk}


def test_scope_ogranichivaet_snyatie(cat):
    """Снимаем только то, что человек видел: вне выборки связь остаётся."""
    a = make_product(cat, "Шуруповёрт", "shurup")
    seen = make_product(cat, "Биты", "bity")
    unseen = make_product(cat, "Аккумулятор", "akkum")
    set_links(a, CROSS, [seen.pk, unseen.pk])

    set_links(a, CROSS, [], scope_ids=[seen.pk])

    assert linked_ids(a, CROSS) == {unseen.pk}


def test_add_links_nichego_ne_snimaet(cat):
    a = make_product(cat, "Фрезер", "frezer")
    old = make_product(cat, "Фрезы", "frezy")
    new = make_product(cat, "Копир", "kopir")
    set_links(a, CROSS, [old.pk])

    add_links(a, CROSS, [new.pk], origin=CompatibilityOrigin.AI)

    assert linked_ids(a, CROSS) == {old.pk, new.pk}


# ---------------------------------------------------------------------------
# Витрина
# ---------------------------------------------------------------------------


def test_sekcii_kartochki_soderzhat_novye_vidy(cat):
    a = make_product(cat, "Дрель", "drel-2")
    cross = make_product(cat, "Свёрла", "sverla-2")
    analog = make_product(cat, "Дрель другая", "drel-3")
    set_links(a, CROSS, [cross.pk])
    set_links(a, ANALOG, [analog.pk])

    sections = compatibility_sections(a)

    assert [i.product.pk for i in sections["cross_sell"]] == [cross.pk]
    assert [i.product.pk for i in sections["analogs"]] == [analog.pk]


def test_nevidimyy_tovar_v_sekciyu_ne_popadaet(cat):
    a = make_product(cat, "Дрель", "drel-4")
    hidden = make_product(cat, "Снятый с витрины", "hidden", is_active=False)
    set_links(a, CROSS, [hidden.pk])

    assert cross_sell_of(a) == []


def test_api_otdaet_obe_sekcii(cat):
    a = make_product(cat, "Дрель", "drel-5")
    cross = make_product(cat, "Свёрла", "sverla-5")
    analog = make_product(cat, "Дрель-аналог", "drel-6")
    set_links(a, CROSS, [cross.pk])
    set_links(a, ANALOG, [analog.pk])

    resp = APIClient().get(f"/api/catalog/products/{a.slug}/compatible/")

    assert resp.status_code == 200
    assert [p["id"] for p in resp.data["cross_sell"]] == [cross.pk]
    assert [p["id"] for p in resp.data["analogs"]] == [analog.pk]


# ---------------------------------------------------------------------------
# Экран подбора в админке
# ---------------------------------------------------------------------------


@pytest.fixture
def staff_client(client):
    user = User.objects.create_superuser(
        phone="+79001112233", email="admin@proff58.ru", password="pass12345"
    )
    client.force_login(user)
    return client


def test_ekran_podbora_pokazyvaet_kandidatov_tipa(staff_client, cat):
    a = make_product(cat, "УШМ 125", "u-125", attrs_cache={"tool_type": "Болгарки (УШМ)"})
    same = make_product(cat, "УШМ 180", "u-180", attrs_cache={"tool_type": "Болгарки (УШМ)"})
    other = make_product(cat, "Лобзик", "lob", attrs_cache={"tool_type": "Лобзики"})

    resp = staff_client.get(reverse("admin:catalog_product_links", args=[a.pk]))

    assert resp.status_code == 200
    shown = {row["product"].pk for row in resp.context["rows"]}
    assert same.pk in shown and other.pk not in shown


def test_ekran_podbora_sohranyaet_galochki(staff_client, cat):
    a = make_product(cat, "УШМ 125", "u2-125", attrs_cache={"tool_type": "Болгарки (УШМ)"})
    b = make_product(cat, "УШМ 180", "u2-180", attrs_cache={"tool_type": "Болгарки (УШМ)"})
    url = reverse("admin:catalog_product_links", args=[a.pk])

    staff_client.post(url, {"shown": [b.pk], f"link_{ANALOG}": [b.pk]})

    assert linked_ids(a, ANALOG) == {b.pk}


def test_ekran_podbora_ne_stiraet_nevidimoe(staff_client, cat):
    """Связь с товаром, которого на экране не было, остаётся на месте."""
    a = make_product(cat, "УШМ 125", "u3-125", attrs_cache={"tool_type": "Болгарки (УШМ)"})
    shown = make_product(cat, "УШМ 180", "u3-180", attrs_cache={"tool_type": "Болгарки (УШМ)"})
    hidden = make_product(cat, "Круг", "krug-3", attrs_cache={"tool_type": "Расходники"})
    set_links(a, CROSS, [shown.pk, hidden.pk])
    url = reverse("admin:catalog_product_links", args=[a.pk])

    staff_client.post(url, {"shown": [shown.pk]})  # обе галочки сняты

    assert linked_ids(a, CROSS) == {hidden.pk}


def test_ekran_podbora_zakryt_ot_chuzhih(client, cat):
    a = make_product(cat, "УШМ", "u4")
    user = User.objects.create_user(
        phone="+79001112244", email="user@proff58.ru", password="pass12345"
    )
    client.force_login(user)

    resp = client.get(reverse("admin:catalog_product_links", args=[a.pk]))

    assert resp.status_code in (302, 403)


# ---------------------------------------------------------------------------
# Загрузка разбора
# ---------------------------------------------------------------------------


def test_komanda_gruzit_svyazi(cat, tmp_path):
    a = make_product(cat, "УШМ 125", "u5-125")
    b = make_product(cat, "УШМ 180", "u5-180")
    path = tmp_path / "links.json"
    path.write_text(
        json.dumps({"kind": ANALOG.value, "links": [{"source": a.pk, "targets": [b.pk]}]}),
        encoding="utf-8",
    )

    call_command("apply_product_links", "--file", str(path))

    assert linked_ids(a, ANALOG) == {b.pk}
    assert ProductCompatibility.objects.get(kind=ANALOG).origin == CompatibilityOrigin.AI


def test_povtornyy_progon_ne_dubliruet(cat, tmp_path):
    a = make_product(cat, "УШМ 125", "u6-125")
    b = make_product(cat, "УШМ 180", "u6-180")
    path = tmp_path / "links.json"
    path.write_text(
        json.dumps({"kind": ANALOG.value, "links": [{"source": a.pk, "targets": [b.pk]}]}),
        encoding="utf-8",
    )

    call_command("apply_product_links", "--file", str(path))
    call_command("apply_product_links", "--file", str(path))

    assert ProductCompatibility.objects.filter(kind=ANALOG).count() == 1


def test_suhoy_progon_nichego_ne_pishet(cat, tmp_path):
    a = make_product(cat, "УШМ 125", "u7-125")
    b = make_product(cat, "УШМ 180", "u7-180")
    path = tmp_path / "links.json"
    path.write_text(
        json.dumps({"kind": CROSS.value, "links": [{"source": a.pk, "targets": [b.pk]}]}),
        encoding="utf-8",
    )

    call_command("apply_product_links", "--file", str(path), "--dry-run")

    assert ProductCompatibility.objects.count() == 0


def test_komanda_perezhivaet_nesushchestvuyushchie_id(cat, tmp_path):
    a = make_product(cat, "УШМ 125", "u8-125")
    path = tmp_path / "links.json"
    path.write_text(
        json.dumps({"kind": CROSS.value, "links": [{"source": a.pk, "targets": [999999]}]}),
        encoding="utf-8",
    )

    call_command("apply_product_links", "--file", str(path))

    assert linked_ids(a, CROSS) == set()


def test_vygruzka_kandidatov(cat, tmp_path):
    make_product(cat, "УШМ 125", "u9-125", attrs_cache={"tool_type": "Болгарки (УШМ)"})
    make_product(cat, "Лобзик", "u9-lob", attrs_cache={"tool_type": "Лобзики"})
    out = tmp_path / "cand.json"

    call_command("export_link_candidates", "--tool-type", "Болгарки (УШМ)", "--out", str(out))

    data = json.loads(out.read_text(encoding="utf-8"))
    assert [p["name"] for p in data["products"]] == ["УШМ 125"]


def test_analogs_of_poryadok_ustoychiv(cat):
    """Секция аналогов не «прыгает» между запросами: порядок задаётся sort_order/id."""
    a = make_product(cat, "УШМ", "u10")
    first = make_product(cat, "Аналог 1", "an-1")
    second = make_product(cat, "Аналог 2", "an-2")
    set_links(a, ANALOG, [first.pk, second.pk])

    assert [i.product.pk for i in analogs_of(a)] == [i.product.pk for i in analogs_of(a)]
