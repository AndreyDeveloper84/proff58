from apps.ai.sourcing.safety import host_allowed
from apps.ai.sourcing.sources import get_sources

ALLOW = {"makita.ru", "market.yandex.ru"}


def test_allowlist_normalized_hostname():
    assert host_allowed("https://makita.ru/tool/x", ALLOW) is True
    assert host_allowed("https://www.makita.ru/x", ALLOW) is True  # субдомен www
    assert host_allowed("https://makita.ru.evil.com/x", ALLOW) is False  # не endswith-обман
    assert host_allowed("http://makita.ru/x", ALLOW) is False  # только https
    assert host_allowed("https://EVIL.com/makita.ru", ALLOW) is False


def test_get_sources_empty_without_keys(settings):
    settings.ANTHROPIC_API_KEY = ""
    settings.YANDEX_MARKET_API_KEY = ""
    assert get_sources(include_dummy=False) == []
