"""Sentry: секреты колбэка входа через VK ID / Яндекс ID не уходят в события."""

from config.sentry_scrub import FILTERED, scrub_oauth_event


def test_scrubs_oauth_callback_query_string():
    event = {
        "request": {
            "url": "https://proff58.ru/api/oauth/vkid/callback/",
            "query_string": "code=SECRET&state=ST&device_id=DEV&payload=%7B%7D&next=%2Fx",
        }
    }
    qs = scrub_oauth_event(event)["request"]["query_string"]
    for secret in ("SECRET", "ST&", "DEV", "%7B%7D"):
        assert secret not in qs
    assert qs.count(FILTERED.replace("[", "%5B").replace("]", "%5D")) == 4
    assert "next=%2Fx" in qs


def test_scrubs_url_with_query_and_dict_form():
    event = {
        "request": {
            "url": "https://proff58.ru/api/oauth/yandex/callback/?code=SECRET&state=ST",
            "query_string": {"code": "SECRET", "state": "ST", "x": "1"},
        },
        "breadcrumbs": {
            "values": [{"data": {"url": "https://proff58.ru/api/oauth/vkid/callback/?code=S2"}}]
        },
    }
    out = scrub_oauth_event(event)
    assert "SECRET" not in out["request"]["url"] and "ST" not in out["request"]["url"]
    assert out["request"]["query_string"] == {"code": FILTERED, "state": FILTERED, "x": "1"}
    assert "S2" not in out["breadcrumbs"]["values"][0]["data"]["url"]


def test_other_paths_untouched():
    event = {"request": {"url": "https://proff58.ru/api/catalog/", "query_string": "code=abc"}}
    assert scrub_oauth_event(event)["request"]["query_string"] == "code=abc"
