import json

from apps.ai.ports import ModelCall, get_provider
from apps.ai.providers.dummy import DummyProvider


def test_dummy_returns_valid_enrich_json():
    prov = DummyProvider()
    reply = prov.complete(ModelCall(system="s", user="Перфоратор HR2470 Makita 780Вт"))
    data = json.loads(reply.text)
    assert {"name", "short_description", "description", "attributes", "confidence"} <= data.keys()
    assert reply.provider == "dummy"


def test_get_provider_defaults_to_dummy(settings):
    settings.ANTHROPIC_API_KEY = ""
    assert get_provider().__class__.__name__ == "DummyProvider"
