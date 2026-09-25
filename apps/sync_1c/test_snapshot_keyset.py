"""Тесты keyset-пагинации снимка (reliability PR-2), аддитивно к offset."""

from __future__ import annotations

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.catalog.models import Product

API_KEY = "test-key-123"


@pytest.fixture
def auth_client():
    c = APIClient()
    c.credentials(HTTP_X_API_KEY=API_KEY)
    return c


def _make(n):
    for i in range(n):
        Product.objects.create(name=f"Т{i}", code_1c=f"1c-k-{i:02d}", slug=f"k-{i:02d}")


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_keyset_traverses_all_in_order(auth_client):
    """Полный обход keyset-курсором даёт все позиции в порядке (code_1c, id)."""
    _make(5)
    seen: list[str] = []
    after_code, after_id = "", 0
    for _ in range(20):  # предохранитель от бесконечного цикла
        body = auth_client.get(
            f"/api/1c/snapshot/?limit=2&after_id={after_id}&after_code_1c={after_code}"
        ).json()
        assert body["count"] is None  # keyset не считает count
        assert body["offset"] is None and body["next_offset"] is None
        seen += [r["code_1c"] for r in body["results"]]
        if body["next_after_id"] is None:
            break
        after_code, after_id = body["next_after_code_1c"], body["next_after_id"]
    assert seen == [f"1c-k-{i:02d}" for i in range(5)]


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_keyset_last_page_has_null_cursor(auth_client):
    _make(3)
    body = auth_client.get("/api/1c/snapshot/?limit=100&after_id=0").json()
    assert len(body["results"]) == 3
    assert body["next_after_code_1c"] is None and body["next_after_id"] is None


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_keyset_first_page_returns_smallest(auth_client):
    _make(3)
    body = auth_client.get("/api/1c/snapshot/?limit=1&after_id=0").json()
    assert [r["code_1c"] for r in body["results"]] == ["1c-k-00"]
    assert body["next_after_code_1c"] == "1c-k-00"
    assert body["next_after_id"] is not None


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_keyset_invalid_after_id(auth_client):
    assert auth_client.get("/api/1c/snapshot/?after_id=abc").status_code == 400
    assert auth_client.get("/api/1c/snapshot/?after_id=-1").status_code == 400


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_offset_mode_unchanged_plus_cursor_fields(auth_client):
    """offset-режим работает как раньше (count/next_offset) + аддитивные курсор-поля."""
    _make(5)
    body = auth_client.get("/api/1c/snapshot/?limit=2&offset=0").json()
    assert body["count"] == 5
    assert body["offset"] == 0
    assert body["next_offset"] == 2
    assert len(body["results"]) == 2
    # курсор-поля присутствуют и указывают на последнюю позицию страницы
    assert "next_after_code_1c" in body and "next_after_id" in body
    assert body["next_after_code_1c"] == "1c-k-01"


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_keyset_matches_offset_full_set(auth_client):
    """Множество позиций через keyset совпадает с offset-обходом."""
    _make(7)
    via_offset = []
    offset = 0
    while True:
        b = auth_client.get(f"/api/1c/snapshot/?limit=3&offset={offset}").json()
        via_offset += [r["code_1c"] for r in b["results"]]
        if b["next_offset"] is None:
            break
        offset = b["next_offset"]

    via_keyset = []
    ac, ai = "", 0
    while True:
        b = auth_client.get(f"/api/1c/snapshot/?limit=3&after_id={ai}&after_code_1c={ac}").json()
        via_keyset += [r["code_1c"] for r in b["results"]]
        if b["next_after_id"] is None:
            break
        ac, ai = b["next_after_code_1c"], b["next_after_id"]

    assert via_offset == via_keyset
    assert len(via_keyset) == 7
