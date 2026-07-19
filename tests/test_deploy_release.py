"""Регрессия release-шага прод-деплоя (#441/m-07).

Инвариант: миграции применяются ОТДЕЛЬНЫМ release-шагом (docker/release.sh), а web
на старте их не применяет (только migrate --check). Иначе тяжёлый DDL/гонки на каждом
рестарте контейнера. Тест ловит случайный возврат `migrate` в entrypoint или обрыв
цепочки deploy → release.sh.
"""

import re
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "docker" / "entrypoint.prod.sh"
RELEASE = ROOT / "docker" / "release.sh"
DEPLOY = ROOT / ".github" / "workflows" / "deploy.yml"


def test_web_entrypoint_does_not_apply_migrations():
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert (
        "migrate --noinput" not in text
    ), "web не должен применять миграции на старте (#441): DDL — в release-шаге"
    assert (
        "migrate --check" in text
    ), "web на старте обязан проверять применённость миграций (migrate --check)"


def test_release_script_backs_up_and_migrates():
    assert RELEASE.is_file(), "нет docker/release.sh — release-шаг не выделен"
    text = RELEASE.read_text(encoding="utf-8")
    assert "pg_dump" in text, "release.sh должен снимать бэкап БД до миграций (для отката)"
    assert "migrate --noinput" in text, "release.sh должен применять миграции"
    # порядок: бэкап строго ДО миграций.
    assert text.index("pg_dump") < text.index(
        "migrate --noinput"
    ), "бэкап БД должен идти ДО применения миграций"


def test_release_script_is_executable():
    mode = RELEASE.stat().st_mode
    assert mode & stat.S_IXUSR, "docker/release.sh должен быть исполняемым"


def test_deploy_invokes_release_step():
    text = DEPLOY.read_text(encoding="utf-8")
    assert re.search(
        r"bash\s+docker/release\.sh", text
    ), "deploy.yml должен вызывать release-шаг (docker/release.sh) перед подъёмом"
