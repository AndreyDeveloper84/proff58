"""Секреты из query не попадают в access-логи nginx и gunicorn (DRF-2482)."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from gunicorn.config import Config

from config.gunicorn_logging import ScrubbedLogger

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = [ROOT / "docker" / "nginx" / "default.conf", ROOT / "docs" / "nginx" / "proff58.ru.conf"]

SECRET_URIS = [
    "/api/oauth/vkid/callback/?code=SECRET&state=S&device_id=D",
    "/api/oauth/yandex/callback?code=SECRET",
    "/api/payments/webhook/atolpay/?t=SECRET",
]
PLAIN_URIS = ["/api/catalog/products/?search=drel", "/api/oauth/vkid/start/?next=/cart"]


def _map_rules(text: str, variable: str):
    body = re.search(r"map \$request_uri \$" + variable + r" \{(.*?)\n\}", text, re.S).group(1)
    return [
        (re.compile(m.group(1).replace("(?<", "(?P<")), m.group(2))
        for m in re.finditer(r'"~(.+?)"\s+"(.+?)";', body)
    ]


def _log_uri(rules, uri: str) -> str:
    for pattern, value in rules:
        m = pattern.search(uri)
        if m:
            return re.sub(r"\$(\w+)", lambda v, m=m: m.group(v.group(1)), value)
    return uri


@pytest.mark.parametrize("conf", CONFIGS, ids=lambda p: p.name)
def test_nginx_лог_без_request_и_с_маской(conf):
    text = re.sub(r"(?m)^\s*#.*$", "", conf.read_text(encoding="utf-8"))
    variable = re.search(r"map \$request_uri \$(\w+)", text).group(1)
    formats = re.findall(r"log_format\s+\w+\s+(.*?);", text, re.S)
    assert formats, "в конфиге нет своего log_format"
    for fmt in formats:
        assert '"$request"' not in fmt and "$" + variable in fmt

    rules = _map_rules(text, variable)
    for uri in SECRET_URIS:
        logged = _log_uri(rules, uri)
        assert "SECRET" not in logged and logged.endswith("?[hidden]"), logged
    for uri in PLAIN_URIS:
        assert _log_uri(rules, uri) == uri


def _atoms(path: str, query: str) -> dict:
    logger = ScrubbedLogger(Config())
    environ = {
        "REQUEST_METHOD": "GET",
        "RAW_URI": f"{path}?{query}" if query else path,
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "SERVER_PROTOCOL": "HTTP/1.1",
        "REMOTE_ADDR": "10.0.0.1",
    }
    resp = SimpleNamespace(status="302 Found", sent=0, headers=[])
    req = SimpleNamespace(headers=[])
    return logger.atoms(resp, req, environ, dt.timedelta(microseconds=1500))


@pytest.mark.parametrize(
    "path,query",
    [
        ("/api/oauth/vkid/callback/", "code=SECRET&state=S"),
        ("/api/payments/webhook/atolpay/", "t=SECRET"),
    ],
)
def test_gunicorn_прячет_query_колбэков_и_вебхуков(path, query):
    atoms = _atoms(path, query)
    assert atoms["r"] == f"GET {path}?[hidden] HTTP/1.1"
    assert atoms["q"] == "[hidden]"
    assert "SECRET" not in str(atoms)


def test_gunicorn_остальные_запросы_как_есть():
    atoms = _atoms("/api/catalog/products/", "search=drel")
    assert atoms["r"] == "GET /api/catalog/products/?search=drel HTTP/1.1"
    assert _atoms("/api/oauth/vkid/callback/", "")["r"] == "GET /api/oauth/vkid/callback/ HTTP/1.1"
