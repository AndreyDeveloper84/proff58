import pytest

from apps.catalog.models import Category


@pytest.mark.django_db
def test_category_hero_fields_default_blank():
    cat = Category.add_root(name="Перфораторы", slug="perforatory")
    assert cat.hero_eyebrow == ""
    assert cat.hero_cta_label == ""
    assert cat.hero_cta_href == ""
    assert not cat.hero_image


@pytest.mark.django_db
def test_category_hero_fields_persist():
    cat = Category.add_root(
        name="Перфораторы",
        slug="perforatory",
        hero_eyebrow="Надёжность, результат",
        hero_cta_label="Подобрать модель",
        hero_cta_href="/catalog/perforatory?tool_type=sds",
    )
    cat.refresh_from_db()
    assert cat.hero_eyebrow == "Надёжность, результат"
    assert cat.hero_cta_label == "Подобрать модель"
    assert cat.hero_cta_href == "/catalog/perforatory?tool_type=sds"


@pytest.mark.django_db
def test_facets_endpoint_returns_hero_block(client):
    cat = Category.add_root(
        name="Перфораторы",
        slug="perforatory",
        hero_eyebrow="Надёжность, результат",
        hero_cta_label="Подобрать модель",
        hero_cta_href="/catalog/perforatory?tool_type=sds",
    )
    resp = client.get(f"/api/catalog/categories/{cat.slug}/facets/")
    assert resp.status_code == 200
    hero = resp.json()["category"]["hero"]
    assert hero["eyebrow"] == "Надёжность, результат"
    assert hero["ctaLabel"] == "Подобрать модель"
    assert hero["ctaHref"] == "/catalog/perforatory?tool_type=sds"
    assert hero["image"] is None


@pytest.mark.django_db
def test_facets_endpoint_hero_empty_by_default(client):
    cat = Category.add_root(name="Дрели", slug="dreli")
    resp = client.get(f"/api/catalog/categories/{cat.slug}/facets/")
    assert resp.status_code == 200
    hero = resp.json()["category"]["hero"]
    assert hero == {"image": None, "eyebrow": "", "ctaLabel": "", "ctaHref": ""}
