"""Архитектурные инварианты (Фаза 1: развязка pricing ↔ sync_1c).

Домен ``pricing`` — владелец цены. Он НЕ должен импортировать интеграционный
слой ``sync_1c`` (Dependency Inversion: зависит sync_1c → pricing, не наоборот).
Модель ``PriceRecord`` принадлежит ``pricing``; в ``sync_1c.models`` её больше нет.
"""

import ast
from pathlib import Path

import apps.pricing

PRICING_DIR = Path(apps.pricing.__file__).resolve().parent


def _iter_imported_modules(tree: ast.AST):
    """Все импортируемые модули, включая вложенные внутрифункциональные."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            # node.module is None для относительных импортов вида `from . import x`
            if node.module:
                yield node.module


def test_pricing_does_not_import_sync_1c():
    """Ни один модуль apps.pricing (кроме миграций) не импортирует apps.sync_1c."""
    offenders = []
    for path in PRICING_DIR.rglob("*.py"):
        if "migrations" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module in _iter_imported_modules(tree):
            if module == "apps.sync_1c" or module.startswith("apps.sync_1c."):
                offenders.append(f"{path}: импортирует {module}")
    assert not offenders, "apps.pricing не должен зависеть от apps.sync_1c:\n" + "\n".join(
        offenders
    )


def test_pricerecord_owned_by_pricing():
    """PriceRecord живёт в pricing и удалён из sync_1c.models."""
    import apps.sync_1c.models as m
    from apps.pricing.models import PriceRecord  # noqa: F401

    assert not hasattr(
        m, "PriceRecord"
    ), "PriceRecord не должен быть в apps.sync_1c.models — он перенесён в apps.pricing"
