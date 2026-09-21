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
MANIFEST_DIR = (
    Path(settings.BASE_DIR) / "docs" / "catalog" / "appendix" / "2026-09-21-pf-sh-release-gate-01"
)


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


def test_allowlist_matches_frozen_release_manifest():
    """Allowlist = ровно INDEXABLE_CANDIDATE из замороженного manifest, sha совпадает."""
    allow = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    manifest_path = MANIFEST_DIR / "pf-sh-release-gate-01.json"
    # sha заморожен от LF-блоба (git, Linux); checkout на Windows с autocrlf даёт CRLF.
    raw = manifest_path.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(raw).hexdigest() == allow["manifest_sha256"]
    manifest = json.loads(raw)
    candidates = sorted(s["product_id"] for s in manifest["skus"] if s["indexable_candidate"])
    assert sorted(allow["product_ids"]) == candidates
    assert len(candidates) == 74
    blocked = {s["product_id"] for s in manifest["skus"] if not s["indexable_candidate"]}
    assert blocked.isdisjoint(allow["product_ids"])
