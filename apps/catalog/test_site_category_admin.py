"""Тест раздела админки «Категории (сайт)» — показывает только v2-дерево.

SiteCategoryAdmin фильтрует на поддеревья корней-разделов (slug из SECTION_RULES),
исключая легаси-категории (зеркала групп 1С). Нужен PostgreSQL.
"""

from __future__ import annotations

import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from apps.catalog.admin import SiteCategoryAdmin
from apps.catalog.models import Category, SiteCategory


@pytest.mark.django_db
def test_site_admin_shows_only_v2_subtrees():
    # v2-корень (slug из SECTION_RULES) + дочерний узел
    v2 = Category.add_root(name="Оснастка v2", slug="osnastka")
    v2 = Category.objects.get(pk=v2.pk)
    sverla = v2.add_child(name="Свёрла", slug="osnastka-sverla")
    # легаси-зеркало 1С (другой slug, с кодом)
    legacy = Category.add_root(
        name="Запчасти Hitachi", slug="zapchasti-hitachi", external_id_1c="00002969"
    )
    # просто чужой корень (не v2-раздел)
    other = Category.add_root(name="Случайная", slug="random-root")

    admin = SiteCategoryAdmin(SiteCategory, AdminSite())
    request = RequestFactory().get("/admin/catalog/sitecategory/")
    ids = set(admin.get_queryset(request).values_list("id", flat=True))

    assert v2.pk in ids and sverla.pk in ids  # v2-поддерево видно
    assert legacy.pk not in ids  # легаси-1С скрыто
    assert other.pk not in ids  # не-v2 корень скрыт


@pytest.mark.django_db
def test_site_admin_empty_when_no_v2_roots():
    Category.add_root(name="Запчасти Hitachi", slug="zapchasti-hitachi", external_id_1c="00002969")
    admin = SiteCategoryAdmin(SiteCategory, AdminSite())
    request = RequestFactory().get("/admin/catalog/sitecategory/")
    assert admin.get_queryset(request).count() == 0
