"""DRF-2733: у любого списка в API есть потолок размера страницы."""

import ast
from pathlib import Path

from rest_framework.settings import api_settings

import apps.core
from apps.core.pagination import MAX_PAGE_LIMIT, BoundedLimitOffsetPagination

APPS_DIR = Path(apps.core.__file__).resolve().parent.parent


def test_default_pagination_is_bounded():
    assert api_settings.DEFAULT_PAGINATION_CLASS is BoundedLimitOffsetPagination
    assert BoundedLimitOffsetPagination.max_limit == MAX_PAGE_LIMIT
    # Потолок — выше обычной страницы, иначе он резал бы штатные запросы.
    assert MAX_PAGE_LIMIT >= api_settings.PAGE_SIZE


def test_no_unbounded_drf_pagination_in_apps():
    """Классы пагинации DRF напрямую не используем: у них нет потолка limit.

    Вьюха, создавшая ``LimitOffsetPagination()`` сама, обошла бы дефолт из
    настроек — так было в списках заказов и счетов.
    """
    offenders = []
    for path in APPS_DIR.rglob("*.py"):
        if "migrations" in path.parts or path == APPS_DIR / "core" / "pagination.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "rest_framework.pagination":
                offenders.append(f"{path.relative_to(APPS_DIR)}:{node.lineno}")
    assert not offenders, "Берите apps.core.pagination.BoundedLimitOffsetPagination:\n" + "\n".join(
        offenders
    )
