"""Архитектурные инварианты (Фаза 1: развязка pricing ↔ sync_1c).

Домен ``pricing`` — владелец цены. Он НЕ должен импортировать интеграционный
слой ``sync_1c`` (Dependency Inversion: зависит sync_1c → pricing, не наоборот).
Модель ``PriceRecord`` принадлежит ``pricing``; в ``sync_1c.models`` её больше нет.
"""

import ast
from pathlib import Path

import apps.catalog
import apps.pricing
import apps.sync_1c

PRICING_DIR = Path(apps.pricing.__file__).resolve().parent
SYNC_1C_DIR = Path(apps.sync_1c.__file__).resolve().parent
CATALOG_DIR = Path(apps.catalog.__file__).resolve().parent
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


def test_pricerecord_owned_by_pricing():
    """PriceRecord живёт в pricing и удалён из sync_1c.models."""
    import apps.sync_1c.models as m
    from apps.pricing.models import PriceRecord  # noqa: F401

    assert not hasattr(
        m, "PriceRecord"
    ), "PriceRecord не должен быть в apps.sync_1c.models — он перенесён в apps.pricing"


def test_sync_1c_does_not_write_pricerecord_directly():
    """production-код sync_1c не пишет PriceRecord напрямую — только через repository.

    Запись истории цены принадлежит домену ``pricing`` (см. #152). Проходим по
    production-модулям ``apps/sync_1c/`` (исключая ``admin.py``, ``migrations/`` и
    тестовые файлы ``tests.py``/``test_*.py``) и ловим ОБА паттерна обхода контракта:
      * прямой импорт модели (``from apps.pricing.models import PriceRecord`` /
        ``import apps.pricing.models``) — через AST;
      * обращение к менеджеру ``PriceRecord.objects`` — grep по тексту.
    """
    offenders: list[str] = []
    for path in SYNC_1C_DIR.rglob("*.py"):
        if "migrations" in path.parts or _is_test_path(path):
            continue
        if path.name == "admin.py":
            continue
        source = path.read_text(encoding="utf-8")

        # 1) AST: импорт модели PriceRecord / apps.pricing.models в любой форме.
        tree = ast.parse(source, filename=str(path))
        for module in _iter_imported_modules(tree):
            if module == "apps.pricing.models" or module.startswith("apps.pricing.models."):
                offenders.append(f"{path}: импортирует {module}")
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "apps.pricing":
                if any(alias.name == "models" for alias in node.names):
                    offenders.append(f"{path}: from apps.pricing import models")

        # 2) grep: прямое обращение к менеджеру PriceRecord.objects.
        if "PriceRecord.objects" in source:
            offenders.append(f"{path}: использует PriceRecord.objects напрямую")

    assert not offenders, (
        "sync_1c не должен писать PriceRecord напрямую "
        "(используйте apps.pricing.repositories):\n" + "\n".join(offenders)
    )


def test_catalog_does_not_import_ai():
    """Каталог НЕ зависит от AI-слоя (направление зависимости: ai → catalog, #73).

    AI-слой (``apps.ai``) — потребитель каталога (рекомендации по характеристикам);
    обратная связь ``catalog → ai`` создала бы цикл и нарушила слоистость
    (ARCHITECTURE-AI §1, принцип 3). Проходим по всем production-модулям
    ``apps/catalog`` (исключая ``migrations/`` и тестовые файлы
    ``tests.py``/``test_*.py``; management-команды НЕ исключаем) и через AST
    (включая внутрифункциональные импорты) проверяем, что ни один не импортирует
    модуль, начинающийся с ``apps.ai``.
    """
    offenders = []
    for path in CATALOG_DIR.rglob("*.py"):
        if "migrations" in path.parts or _is_test_path(path):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module in _iter_imported_modules(tree):
            if module == "apps.ai" or module.startswith("apps.ai."):
                offenders.append(f"{path}: импортирует {module}")
    assert not offenders, "apps.catalog не должен зависеть от apps.ai:\n" + "\n".join(offenders)
