"""Регрессия release-шага прод-деплоя (#441/m-07).

Инвариант: миграции применяются ОТДЕЛЬНЫМ release-шагом (docker/release.sh), а web
на старте их не применяет (только migrate --check). Иначе тяжёлый DDL/гонки на каждом
рестарте контейнера. Тест ловит случайный возврат `migrate` в entrypoint или обрыв
цепочки deploy → release.sh.

Сюда же — exec-бит `scripts/backup.sh` (ИНФР-02): скрипт в git лежал режимом 100644,
cron звал его как `./scripts/backup.sh`, и ночной бэкап staging молча не работал ~2
месяца. `chmod +x` на сервере не лечит: `deploy.yml` делает `git reset --hard`, и бит
слетает на следующем push. Лечится только режимом в индексе.
"""

import re
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "docker" / "entrypoint.prod.sh"
RELEASE = ROOT / "docker" / "release.sh"
BACKUP = ROOT / "scripts" / "backup.sh"
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


def test_backup_script_is_executable():
    assert BACKUP.is_file(), "нет scripts/backup.sh — бэкап БД/media не выделен"
    mode = BACKUP.stat().st_mode
    assert mode & stat.S_IXUSR, "scripts/backup.sh должен быть исполняемым (cron зовёт ./)"


def test_deploy_invokes_release_step():
    text = DEPLOY.read_text(encoding="utf-8")
    assert re.search(
        r"bash\s+docker/release\.sh", text
    ), "deploy.yml должен вызывать release-шаг (docker/release.sh) перед подъёмом"


def test_deploy_facet_binding_check_is_fatal():
    """ДРФ-1524 п.4: проверка привязок фасетов обязана ВАЛИТЬ выкат.

    Раньше шаг ловил провал `load_attributes --strict-bindings`, печатал
    ``::warning::`` и ехал дальше — шесть выдуманных имён категорий прожили в
    ``data/attribute_rules.json`` месяцами: значения писались, фасеты молча не
    привязывались. Тест ловит откат к мягкому режиму и потерю обязательных
    флагов строгости.
    """
    text = DEPLOY.read_text(encoding="utf-8")
    calls = [
        ln.strip()
        for ln in text.splitlines()
        if "manage.py load_attributes" in ln and not ln.lstrip().startswith("#")
    ]
    assert (
        len(calls) == 1
    ), f"ожидался ровно один вызов load_attributes в deploy.yml, найдено {calls}"
    call = calls[0]
    assert "--strict-bindings" in call, "not_found обязан быть фатальным (--strict-bindings)"
    assert "--dry-run" in call, "проверка привязок обязана быть read-only (--dry-run)"
    assert (
        "--allow-ambiguous" not in call
    ), "неоднозначные привязки (ambiguous) не должны прощаться на выкате"
    tail = text.split(call, 1)[1]
    assert (
        'exit "$la_rc"' in tail
    ), "провал проверки привязок обязан останавливать выкат, а не печатать ::warning::"


def test_deploy_binding_check_reports_unresolved_names():
    """Падение без разбора бесполезно: в логе шага должны быть имя и ось.

    Команда падает ДО печати плана, весь разбор (``[not_found] «Имя» → ось``,
    ``[ambiguous:tree] …`` и текст CommandError со списком имён) уходит в
    stderr — значит stderr обязан попасть в лог шага целиком.
    """
    text = DEPLOY.read_text(encoding="utf-8")
    assert "2>/tmp/la-bindings.err" in text, "stderr проверки привязок должен писаться в файл"
    assert (
        "cat /tmp/la-bindings.err" in text
    ), "при падении stderr обязан печататься в лог шага — иначе непонятно, что не разрешилось"
