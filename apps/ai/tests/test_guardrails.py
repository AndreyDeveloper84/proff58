# apps/ai/tests/test_guardrails.py
from apps.ai.guardrails import parse_enrich_output


def test_parses_plain_json():
    text = '{"name":"Дрель X","short_description":"кратко","description":"полно",' \
           '"attributes":[{"slug":"power","value":780,"confidence":60}],"confidence":0.8}'
    r = parse_enrich_output(text)
    assert r.name == "Дрель X" and r.confidence == 0.8
    assert r.attributes[0].slug == "power" and r.attributes[0].value == 780


def test_parses_json_code_fence():
    text = '```json\n{"name":"X","short_description":"a","description":"b",' \
           '"attributes":[],"confidence":0.5}\n```'
    assert parse_enrich_output(text).name == "X"


def test_rejects_garbage_returns_none():
    assert parse_enrich_output("извините, не понял") is None


def test_rejects_missing_keys():
    assert parse_enrich_output('{"name":"X"}') is None
