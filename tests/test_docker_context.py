"""Регрессия build-context образа web (#442/TD-05).

Dockerfile делает `COPY . .`, поэтому `.dockerignore` — единственный барьер против
попадания непродуктового балласта (frontend ~1 ГБ, .claude ~140 МБ, docs, tests, CI)
в образ web. Тест фиксирует, что балласт исключён, а нужное рантайму/прод-командам
(код, scripts, docker, data с дампом 1С) — нет.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERIGNORE = ROOT / ".dockerignore"

# Непродуктовое — не нужно образу web (dev монтирует исходники томом, CI — из checkout).
BALLAST = [".claude", "frontend", "docs", ".github", "tests", "node_modules"]
# Нужно рантайму/прод-командам каталога (prod web НЕ монтирует исходники).
KEEP = ["apps", "config", "scripts", "docker", "requirements", "data"]


def _patterns():
    return [
        line.strip()
        for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_ballast_excluded_from_image():
    patterns = set(_patterns())
    for path in BALLAST:
        assert path in patterns, f"{path} должен исключаться из build context web (#442/TD-05)"
        assert f"!{path}" not in patterns, f"{path} не должен ре-включаться отрицанием"


def test_runtime_paths_not_excluded():
    patterns = set(_patterns())
    for path in KEEP:
        assert (
            path not in patterns
        ), f"{path} нужен образу web (prod-команды/рантайм) — не исключать целиком"


def test_dockerfile_copies_whole_context():
    # Инвариант держится только пока Dockerfile копирует весь контекст (COPY . .).
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert (
        "COPY . ." in dockerfile
    ), "если COPY . . заменили точечным копированием — этот тест и .dockerignore пересмотреть"
