"""API информационных страниц.

Главное правило — как в каталоге: витрина видит только опубликованное.
Черновик не должен утекать даже по прямой ссылке.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.content.models import PublishStatus, SEOPage


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def страница(db):
    return SEOPage.objects.create(
        slug="dostavka",
        title="Доставка",
        body="Доставляем по Пензе и области.",
        status=PublishStatus.PUBLISHED,
    )


def test_список_отдаёт_опубликованные(api, страница):
    SEOPage.objects.create(slug="chernovik", title="Черновик", status=PublishStatus.DRAFT)

    data = api.get("/api/content/pages/").json()

    assert [p["slug"] for p in data] == ["dostavka"]


def test_список_даёт_только_ссылочные_поля(api, страница):
    item = api.get("/api/content/pages/").json()[0]

    assert set(item) == {"slug", "title"}


def test_страница_отдаётся_целиком(api, страница):
    data = api.get("/api/content/pages/dostavka/").json()

    assert data["title"] == "Доставка"
    assert data["body"] == "Доставляем по Пензе и области."
    assert "meta_description" in data


def test_черновик_не_виден_по_прямой_ссылке(api, db):
    SEOPage.objects.create(slug="tayna", title="Тайна", status=PublishStatus.DRAFT)

    assert api.get("/api/content/pages/tayna/").status_code == 404


def test_несуществующая_страница_404(api, db):
    assert api.get("/api/content/pages/net-takoy/").status_code == 404


def test_доступно_без_авторизации(api, страница):
    """Инфо-страницы — публичные, витрина ходит анонимно."""
    assert api.get("/api/content/pages/dostavka/").status_code == 200


def test_кириллический_slug_работает(api, db):
    SEOPage.objects.create(slug="о-компании", title="О компании", status=PublishStatus.PUBLISHED)

    assert api.get("/api/content/pages/о-компании/").status_code == 200
