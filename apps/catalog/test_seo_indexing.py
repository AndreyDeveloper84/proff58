"""PF-SH-RELEASE-01: политика индексации на уровне товара.

Индексируются только товары из замороженного allowlist (74 INDEXABLE_CANDIDATE из
release-gate manifest). Всё остальное — noindex на витрине и вне sitemap. Позиция
allowlist не делает товар видимым: снятый с публикации товар не индексируется.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from django.conf import settings
from django.test import override_settings
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, ProductStatus
from apps.catalog.seo_index import indexable_product_ids

ALLOWLIST = Path(settings.BASE_DIR) / "data" / "seo" / "indexable_products.json"
BASE = Path(settings.BASE_DIR)


@pytest.fixture
def cat(db):
    return Category.add_root(name="Электроинструмент", slug="ei", on_site=True, is_active=True)


def _product(cat, slug, *, status=ProductStatus.PUBLISHED, is_active=True):
    return Product.objects.create(
        category=cat, name=slug, slug=slug, status=status, is_active=is_active
    )


@pytest.fixture
def allowlist(tmp_path):
    """Подменяет allowlist файлом из теста; кэш загрузчика сбрасывается."""

    def _write(ids):
        path = tmp_path / "indexable_products.json"
        path.write_text(json.dumps({"product_ids": ids}), encoding="utf-8")
        indexable_product_ids.cache_clear()
        return override_settings(SEO_INDEXABLE_PRODUCTS_PATH=str(path))

    yield _write
    indexable_product_ids.cache_clear()


@pytest.mark.django_db
def test_detail_marks_allowlisted_product_indexable(cat, allowlist):
    p = _product(cat, "perf-1")
    with allowlist([p.id]):
        data = APIClient().get(f"/api/catalog/products/{p.slug}/").json()
    assert data["seo_indexable"] is True


@pytest.mark.django_db
def test_detail_marks_other_product_not_indexable(cat, allowlist):
    listed = _product(cat, "perf-1")
    other = _product(cat, "perf-2")
    with allowlist([listed.id]):
        data = APIClient().get(f"/api/catalog/products/{other.slug}/").json()
    assert data["seo_indexable"] is False


@pytest.mark.django_db
def test_sitemap_lists_only_allowlisted_visible_products(cat, allowlist):
    listed = _product(cat, "perf-1")
    draft = _product(cat, "perf-2", status=ProductStatus.DRAFT)
    inactive = _product(cat, "perf-3", is_active=False)
    _product(cat, "perf-4")  # видим, но не в allowlist
    with allowlist([listed.id, draft.id, inactive.id]):
        resp = APIClient().get("/api/catalog/seo/sitemap-products/")
    assert resp.status_code == 200
    rows = resp.json()
    assert [r["slug"] for r in rows] == ["perf-1"]
    assert rows[0]["updated_at"]


@pytest.mark.django_db
def test_missing_allowlist_file_means_nothing_indexable(cat, tmp_path):
    p = _product(cat, "perf-1")
    indexable_product_ids.cache_clear()
    with override_settings(SEO_INDEXABLE_PRODUCTS_PATH=str(tmp_path / "absent.json")):
        data = APIClient().get(f"/api/catalog/products/{p.slug}/").json()
        rows = APIClient().get("/api/catalog/seo/sitemap-products/").json()
    indexable_product_ids.cache_clear()
    assert data["seo_indexable"] is False
    assert rows == []


def test_allowlist_matches_frozen_release_manifests():
    """Allowlist = объединение INDEXABLE_CANDIDATE всех партий; sha каждой совпадает.

    Партий больше одной (SEO-BATCH-02): id добавляются только новым гейтом, его manifest
    замораживается вместе с sha, а заблокированные SKU не могут попасть в список ни из одной партии.
    """
    allow = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    union: set[int] = set()
    for batch in allow["batches"]:
        # sha заморожен от LF-блоба (git, Linux); checkout на Windows с autocrlf даёт CRLF.
        raw = (BASE / batch["manifest"]).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(raw).hexdigest() == batch["manifest_sha256"], batch["id"]
        manifest = json.loads(raw)
        candidates = {s["product_id"] for s in manifest["skus"] if s["indexable_candidate"]}
        blocked = {s["product_id"] for s in manifest["skus"] if not s["indexable_candidate"]}
        assert len(candidates) == batch["count"], batch["id"]
        assert blocked.isdisjoint(allow["product_ids"]), batch["id"]
        assert candidates.isdisjoint(union), batch["id"]
        union |= candidates
    assert sorted(allow["product_ids"]) == sorted(union)
    assert allow["count"] == len(union) == 147
