"""import_products должен быть атомарным (#4 код-ревью).

bulk_create/bulk_update шли батчами без внешней транзакции: сбой на середине
оставлял часть батчей закоммиченными → каталог в полу-импортированном
состоянии. Проверяем, что при сбое посреди импорта НИ один товар не остаётся,
а прогон ImportRun фиксируется как FAILED (вне отката — для аудита).
"""

from unittest import mock

import pytest
from django.core.management import call_command
from django.db import IntegrityError

from apps.catalog.models import ImportRun, ImportRunStatus, Product

CMD = "apps.catalog.management.commands.import_products"


@pytest.mark.django_db
def test_import_products_rolls_back_all_on_midway_failure():
    # 4 ноды, BATCH=2: первый батч (C,D) пишется, второй (дубль code_1c) падает.
    nodes = [
        ({"external_id": "c4-10", "name": "C"}, None),
        ({"external_id": "c4-11", "name": "D"}, None),
        ({"external_id": "c4-dup", "name": "A"}, None),
        ({"external_id": "c4-dup", "name": "B"}, None),  # дубль code_1c → IntegrityError
    ]

    with (
        mock.patch(f"{CMD}.BATCH", 2),
        mock.patch(f"{CMD}.load_group_mapping", return_value=[]),
        mock.patch(f"{CMD}.group_index", return_value={}),
        mock.patch(f"{CMD}.load_json", return_value=None),
        mock.patch(f"{CMD}.iter_products", return_value=nodes),
        mock.patch(f"{CMD}.stock_value", return_value=0.0),
    ):
        with pytest.raises(IntegrityError):
            call_command("import_products")

    # Полный откат: даже успешный первый батч (C,D) не остался.
    assert Product.objects.count() == 0
    # Аудит сохранён вне транзакции импорта.
    run = ImportRun.objects.latest("id")
    assert run.status == ImportRunStatus.FAILED
