"""API статей: витрина получает готовую структуру, а не сырую разметку.

Разбор делает сервер — так правило разметки одно на всю систему, и витрине не
нужен собственный парсер.
"""

from __future__ import annotations

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import Category
from apps.content.models import Article, ArticleFigure, PublishStatus


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def статья(db):
    категория = Category.add_root(name="Перфораторы", slug="perforatory-art")
    return Article.objects.create(
        slug="sds-plus-ili-sds-max",
        title="SDS-plus или SDS-max",
        excerpt="Два стандарта хвостовика.",
        tag="Перфораторы",
        figure=ArticleFigure.SDS_SHANK,
        catalog_category=категория,
        summary="Первый пункт\nВторой пункт",
        body="## Что это\nАбзац про стандарт.\n\n- пункт\n\n> врезка",
        status=PublishStatus.PUBLISHED,
        published_at=timezone.now(),
    )


def test_лента_отдаёт_опубликованные(api, статья):
    Article.objects.create(slug="draft", title="Черновик", status=PublishStatus.DRAFT)

    data = api.get("/api/content/articles/").json()

    assert [a["slug"] for a in data] == ["sds-plus-ili-sds-max"]


def test_карточка_ленты_несёт_поля_витрины(api, статья):
    item = api.get("/api/content/articles/").json()[0]

    assert item["tag"] == "Перфораторы"
    assert item["figure"] == "sds-shank"
    assert item["readingMinutes"] >= 1
    assert item["date"]


def test_статья_отдаётся_разобранной_на_секции(api, статья):
    data = api.get("/api/content/articles/sds-plus-ili-sds-max/").json()

    assert data["sections"][0]["heading"] == "Что это"
    assert [b["kind"] for b in data["sections"][0]["blocks"]] == ["text", "list", "note"]


def test_коротко_приходит_списком(api, статья):
    data = api.get("/api/content/articles/sds-plus-ili-sds-max/").json()

    assert data["summary"] == ["Первый пункт", "Второй пункт"]


def test_раздел_каталога_отдаётся_ссылкой(api, статья):
    data = api.get("/api/content/articles/sds-plus-ili-sds-max/").json()

    assert data["catalog"] == {"slug": "perforatory-art", "label": "Перфораторы"}


def test_без_раздела_каталога_приходит_null(api, db):
    Article.objects.create(
        slug="bez-razdela",
        title="Без раздела",
        body="Текст",
        status=PublishStatus.PUBLISHED,
        published_at=timezone.now(),
    )

    data = api.get("/api/content/articles/bez-razdela/").json()

    assert data["catalog"] is None


def test_черновик_не_виден_по_прямой_ссылке(api, db):
    Article.objects.create(slug="tayna", title="Тайна", status=PublishStatus.DRAFT)

    assert api.get("/api/content/articles/tayna/").status_code == 404


def test_время_чтения_можно_задать_вручную(api, db):
    Article.objects.create(
        slug="ruchnoe",
        title="Ручное",
        body="Короткий текст",
        reading_minutes=7,
        status=PublishStatus.PUBLISHED,
        published_at=timezone.now(),
    )

    assert api.get("/api/content/articles/ruchnoe/").json()["readingMinutes"] == 7
