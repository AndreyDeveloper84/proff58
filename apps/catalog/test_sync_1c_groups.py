"""Тесты catalog_sync_1c_groups — реестр групп 1С (OneCGroup).

Проверяет статусы (active/stale/discovered), счётчики по source_group, привязку
категории по external_id_1c, dry-run и идемпотентность. Использует реальный
data/group_mapping.json (там есть «Биты», «Буры»). Нужен PostgreSQL.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from apps.catalog.models import (
    Category,
    OneCGroup,
    OneCGroupStatus,
    Product,
    ProductStatus,
)


def _p(name, slug, group):
    return Product.objects.create(
        name=name, slug=slug, source_group=group, status=ProductStatus.IMPORTED
    )


@pytest.mark.django_db
def test_dry_run_writes_nothing():
    _p("Бита PH2", "p-bit", "Биты")
    out = StringIO()
    call_command("catalog_sync_1c_groups", stdout=out)
    assert "DRY-RUN" in out.getvalue()
    assert OneCGroup.objects.count() == 0


@pytest.mark.django_db
def test_active_stale_discovered():
    _p("Бита PH2 50мм", "p-bit", "Биты")  # есть в маппинге + товар → active
    _p("Нечто странное", "p-x", "ВымышленнаяГруппаXYZ")  # нет в маппинге → discovered
    call_command("catalog_sync_1c_groups", "--commit", stdout=StringIO())

    bity = OneCGroup.objects.get(name="Биты")
    assert bity.status == OneCGroupStatus.ACTIVE
    assert bity.product_count == 1
    assert bity.code  # external_id подтянулся из маппинга
    assert bity.site_path  # путь на сайте из маппинга

    bury = OneCGroup.objects.get(name="Буры")  # в маппинге, товаров нет
    assert bury.status == OneCGroupStatus.STALE
    assert bury.product_count == 0

    disc = OneCGroup.objects.get(name="ВымышленнаяГруппаXYZ")
    assert disc.status == OneCGroupStatus.DISCOVERED
    assert disc.product_count == 1
    assert disc.code == ""


@pytest.mark.django_db
def test_hierarchy_parent_set():
    # «Биты» в дереве 1С лежит под «Буры, коронки, биты, пилки и полотна».
    call_command("catalog_sync_1c_groups", "--commit", stdout=StringIO())
    bity = OneCGroup.objects.get(name="Биты")
    assert bity.parent is not None
    assert bity.parent.name == "Буры, коронки, биты, пилки и полотна"
    # у корневой группы родителя нет
    root = OneCGroup.objects.get(name="Буры, коронки, биты, пилки и полотна")
    assert root.parent is None
    # tree_path: дочерний путь начинается с родительского (pre-order сортировка админки)
    assert bity.tree_path.startswith(root.tree_path)
    assert bity.tree_path.endswith("Биты")


@pytest.mark.django_db
def test_tree_path_preorder_separates_prefix_siblings():
    # Регрессия скрина: «Запасные части» (корень) с ребёнком «ЗУБР» и отдельный корень
    # «Запасные части Хитачи». При db_collation="C" разделитель \x1f сортируется раньше
    # пробела, поэтому ребёнок ЗУБР идёт ВНУТРИ своего родителя, а не уезжает к чужому
    # корню с тем же префиксом имени.
    call_command("catalog_sync_1c_groups", "--commit", stdout=StringIO())
    names = list(
        OneCGroup.objects.filter(name__in=["Запасные части", "ЗУБР", "Запасные части Хитачи"])
        .order_by("tree_path", "name")
        .values_list("name", flat=True)
    )
    assert names == ["Запасные части", "ЗУБР", "Запасные части Хитачи"]


@pytest.mark.django_db
def test_mapping_not_auto_set_and_preserved():
    # Синк НЕ авто-ставит mapped_category (чистое состояние «только из 1С»).
    _p("Бита", "p-bit", "Биты")
    call_command("catalog_sync_1c_groups", "--commit", stdout=StringIO())
    bity = OneCGroup.objects.get(name="Биты")
    assert bity.mapped_category_id is None

    # Куратор задал категорию — повторный синк её НЕ затирает.
    cat = Category.add_root(name="Биты v2", slug="bity-v2")
    bity.mapped_category = cat
    bity.save(update_fields=["mapped_category"])
    call_command("catalog_sync_1c_groups", "--commit", stdout=StringIO())
    bity.refresh_from_db()
    assert bity.mapped_category_id == cat.id  # выбор куратора сохранён

    # --reset-mapping обнуляет.
    call_command("catalog_sync_1c_groups", "--commit", "--reset-mapping", stdout=StringIO())
    bity.refresh_from_db()
    assert bity.mapped_category_id is None


@pytest.mark.django_db
def test_idempotent():
    _p("Бита", "p-bit", "Биты")
    call_command("catalog_sync_1c_groups", "--commit", stdout=StringIO())
    n1 = OneCGroup.objects.count()
    call_command("catalog_sync_1c_groups", "--commit", stdout=StringIO())
    assert OneCGroup.objects.count() == n1  # дублей нет (upsert по имени)
