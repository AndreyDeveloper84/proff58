"""CSP витрины пускает Яндекс.Метрику ровно настолько, насколько нужно (DRF-2795).

tag.js грузится с mc.yandex.ru, хиты и цели уходят на mc.yandex.ru / mc.yandex.com —
значит, оба хоста должны быть в script-src и connect-src ветки витрины. Вебвизор
выключен, поэтому frame-src для Метрики не расширяется, а ветка JSON API остаётся
`default-src 'none'`. Тест читает реальный docker/nginx/default.conf: правка CSP,
которая молча сломает Метрику (или, наоборот, откроет лишнее), упадёт здесь.
"""

import re
from pathlib import Path

CONF = Path(__file__).resolve().parents[1] / "docker" / "nginx" / "default.conf"
METRIKA_HOSTS = ("https://mc.yandex.ru", "https://mc.yandex.com")


def _storefront_csp() -> str:
    text = CONF.read_text(encoding="utf-8")
    match = re.search(r'map \$uri \$content_csp \{\s*default\s+"([^"]+)"', text)
    assert match, "ветка default в map $content_csp не найдена"
    return match.group(1)


def _directive(csp: str, name: str) -> str:
    for part in csp.split(";"):
        part = part.strip()
        if part.startswith(name + " "):
            return part
    raise AssertionError(f"директива {name} отсутствует в CSP витрины")


def test_metrika_hosts_allowed_for_script_and_connect():
    csp = _storefront_csp()
    for directive in ("script-src", "connect-src"):
        value = _directive(csp, directive)
        for host in METRIKA_HOSTS:
            assert host in value, f"{host} нет в {directive}: {value}"


def test_frame_src_not_widened_for_metrika():
    frame_src = _directive(_storefront_csp(), "frame-src")
    assert "mc.yandex" not in frame_src and "webvisor" not in frame_src


def test_api_branch_stays_closed():
    text = CONF.read_text(encoding="utf-8")
    assert re.search(r'"~\^/\(api\|healthz\)\(/\|\$\)"\s+"default-src \'none\'', text)
