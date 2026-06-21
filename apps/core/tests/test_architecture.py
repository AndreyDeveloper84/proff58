"""Архитектурные инварианты (Фаза 1: развязка pricing ↔ sync_1c).

Домен ``pricing`` — владелец цены. Он НЕ должен импортировать интеграционный
слой ``sync_1c`` (Dependency Inversion: зависит sync_1c → pricing, не наоборот).
Модель ``PriceRecord`` принадлежит ``pricing``; в ``sync_1c.models`` её больше нет.
"""

import ast
from pathlib import Path

import apps.pricing
import apps.sync_1c

PRICING_DIR = Path(apps.pricing.__file__).resolve().parent
SYNC_1C_DIR = Path(apps.sync_1c.__file__).resolve().parent
APPS_DIR = SYNC_1C_DIR.parent


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


def _is_test_path(path: Path) -> bool:
    """Тестовый файл/каталог: tests.py, test_*.py или каталог tests/."""
    if "tests" in path.parts:  # каталог tests/
        return True
    name = path.name
    return name == "tests.py" or name.startswith("test_")


def test_importer_not_used_in_production():
    """Никто из production-кода не импортирует deprecated ``apps.sync_1c.importer``.

    Модуль ``apps/sync_1c/importer.py`` — compatibility shim, допустимый только в
    compat-тестах (``apps/sync_1c/tests.py``). Чтобы production-код снова на него не
    подсел, проходим по production-путям (исключая сам shim, тестовые файлы вида
    ``tests.py``/``test_*.py``/каталоги ``tests/`` и ``migrations/``) и через AST
    (включая внутрифункциональные импорты) проверяем, что ни один не импортирует
    ``apps.sync_1c.importer`` ни в одной из форм.
    """
    # Production-пути: отдельные файлы и каталоги (в каталогах берём все .py рекурсивно).
    targets = [
        SYNC_1C_DIR / "api",
        SYNC_1C_DIR / "tasks.py",
        SYNC_1C_DIR / "use_cases.py",
        SYNC_1C_DIR / "bulk_import.py",
        SYNC_1C_DIR / "product_writer.py",
        SYNC_1C_DIR / "pricing.py",
        SYNC_1C_DIR / "stock.py",
        SYNC_1C_DIR / "normalizers.py",
        SYNC_1C_DIR / "matching.py",
        SYNC_1C_DIR / "management",
        APPS_DIR / "catalog",
        APPS_DIR / "pricing",
        APPS_DIR / "orders",
    ]

    files: list[Path] = []
    for target in targets:
        if target.is_dir():
            files.extend(target.rglob("*.py"))
        elif target.is_file():
            files.append(target)

    importer_path = (SYNC_1C_DIR / "importer.py").resolve()
    offenders = []
    for path in files:
        rpath = path.resolve()
        if rpath == importer_path:  # сам shim из проверки исключаем
            continue
        if "migrations" in path.parts or _is_test_path(path):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module in _iter_imported_modules(tree):
            # покрывает `import apps.sync_1c.importer`,
            # `from apps.sync_1c.importer import ...`,
            # `from apps.sync_1c import importer` (модуль == apps.sync_1c, имя importer).
            if module == "apps.sync_1c.importer" or module.startswith("apps.sync_1c.importer."):
                offenders.append(f"{path}: импортирует {module}")
        # отдельно: `from apps.sync_1c import importer`
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "apps.sync_1c":
                if any(alias.name == "importer" for alias in node.names):
                    offenders.append(f"{path}: from apps.sync_1c import importer")

    assert (
        not offenders
    ), "production-код не должен импортировать deprecated apps.sync_1c.importer:\n" + "\n".join(
        offenders
    )


def test_pricerecord_owned_by_pricing():
    """PriceRecord живёт в pricing и удалён из sync_1c.models."""
    import apps.sync_1c.models as m
    from apps.pricing.models import PriceRecord  # noqa: F401

    assert not hasattr(
        m, "PriceRecord"
    ), "PriceRecord не должен быть в apps.sync_1c.models — он перенесён в apps.pricing"
