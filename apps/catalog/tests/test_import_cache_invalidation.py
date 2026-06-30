"""import_products должен явно сбрасывать кэши после bulk-импорта (#10).

bulk_create/bulk_update не шлют post_save/post_delete, поэтому сигнальная
инвалидация кэша дерева и фасетов не срабатывает — витрина держит старые
счётчики in_stock/диапазон цен до истечения TTL. Проверяем явный сброс.
"""

from unittest import mock

import pytest
from django.core.management import call_command

CMD = "apps.catalog.management.commands.import_products"


@pytest.mark.django_db
def test_import_products_invalidates_caches_on_success():
    with (
        mock.patch(f"{CMD}.load_group_mapping", return_value=[]),
        mock.patch(f"{CMD}.group_index", return_value={}),
        mock.patch(f"{CMD}.load_json", return_value=None),
        mock.patch(f"{CMD}.iter_products", return_value=[]),
        mock.patch(f"{CMD}.stock_value", return_value=0.0),
        mock.patch(f"{CMD}.invalidate_category_tree_cache") as inv_tree,
        mock.patch(f"{CMD}.invalidate_facets_cache") as inv_facets,
    ):
        call_command("import_products")

    inv_tree.assert_called_once()
    inv_facets.assert_called_once()
