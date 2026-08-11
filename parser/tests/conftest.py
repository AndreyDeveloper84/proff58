"""Общая конфигурация тестов парсера.

Гарантирует, что корень репозитория есть в sys.path (нужно для импорта
пакета `parser`), даже если pytest запущен не через `python -m pytest`.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
