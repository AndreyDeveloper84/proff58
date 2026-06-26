"""Тест раздела админки «Категории (сайт)» — показывает только v2-узлы (is_site_v2).

SiteCategoryAdmin фильтрует на is_site_v2=True, исключая легаси-категории (зеркала
групп 1С), даже при совпадении slug. Нужен PostgreSQL.
"""

from __future__ import annotations

import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from apps.catalog.admin import SiteCategoryAdmin
from apps.catalog.models import Category, SiteCategory


@pytest.mark.django_db
def test_site_admin_shows_only_is_site_v2():
    v2 = Category.add_root(name="Оснастка", slug="osnastka", is_site_v2=True)
    v2 = Category.objects.get(pk=v2.pk)
    sverla = v2.add_child(name="Свёрла", slug="osnastka-sverla", is_site_v2=True)
    # легаси-зеркало 1С (is_site_v2=False, с кодом)
    legacy = Category.add_root(
        name="Запчасти Hitachi", slug="zapchasti-hitachi", external_id_1c="00002969"
    )

    admin = SiteCategoryAdmin(SiteCategory, AdminSite())
    request = RequestFactory().get("/admin/catalog/sitecategory/")
    ids = set(admin.get_queryset(request).values_list("id", flat=True))

    assert v2.pk in ids and sverla.pk in ids  # v2-узлы видны
    assert legacy.pk not in ids  # легаси-1С скрыто


@pytest.mark.django_db
def test_site_admin_empty_without_v2():
    Category.add_root(name="Запчасти Hitachi", slug="zapchasti-hitachi", external_id_1c="00002969")
    admin = SiteCategoryAdmin(SiteCategory, AdminSite())
    request = RequestFactory().get("/admin/catalog/sitecategory/")
    assert admin.get_queryset(request).count() == 0
