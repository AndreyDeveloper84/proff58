# apps/ai/tests/test_boundaries.py
import pathlib
import re

AI_DIR = pathlib.Path(__file__).resolve().parents[1]
_BANNED = re.compile(r"\b(Product|ProductAttributeValue|Category)\.objects\b")


def test_no_direct_catalog_objects_in_ai_core():
    """Ядро apps/ai (services/tasks/receivers/ports/guardrails/providers) не лезет
    в objects каталога. Исключения: tests/ и management/ (CLI уровня каталога)."""
    offenders = []
    for path in AI_DIR.rglob("*.py"):
        parts = path.parts
        if "tests" in parts or "management" in parts or "migrations" in parts:
            continue
        if _BANNED.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path))
    assert not offenders, f"Прямой доступ к objects каталога: {offenders}"
