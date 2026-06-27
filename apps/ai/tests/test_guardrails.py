# apps/ai/tests/test_guardrails.py
from apps.ai.guardrails import parse_enrich_output


def test_parses_plain_json():
    text = (
        '{"name":"Дрель X","short_description":"кратко","description":"полно",'
        '"attributes":[{"slug":"power","value":780,"confidence":60}],"confidence":0.8}'
    )
    r = parse_enrich_output(text)
    assert r.name == "Дрель X" and r.confidence == 0.8
    assert r.attributes[0].slug == "power" and r.attributes[0].value == 780


def test_parses_json_code_fence():
    text = (
        '```json\n{"name":"X","short_description":"a","description":"b",'
        '"attributes":[],"confidence":0.5}\n```'
    )
    assert parse_enrich_output(text).name == "X"


def test_rejects_garbage_returns_none():
    assert parse_enrich_output("извините, не понял") is None


def test_rejects_missing_keys():
    assert parse_enrich_output('{"name":"X"}') is None


def test_clamps_global_confidence_to_0_1():
    """Глобальный confidence клампится в [0.0, 1.0]."""
    # Больше 1.0 → клампится до 1.0
    text = (
        '{"name":"X","short_description":"a","description":"b",' '"attributes":[],"confidence":5.5}'
    )
    r = parse_enrich_output(text)
    assert r is not None
    assert r.confidence == 1.0

    # Меньше 0.0 → клампится до 0.0
    text = (
        '{"name":"X","short_description":"a","description":"b",'
        '"attributes":[],"confidence":-10.3}'
    )
    r = parse_enrich_output(text)
    assert r is not None
    assert r.confidence == 0.0

    # В диапазоне → не меняется
    text = (
        '{"name":"X","short_description":"a","description":"b",'
        '"attributes":[],"confidence":0.42}'
    )
    r = parse_enrich_output(text)
    assert r is not None
    assert r.confidence == 0.42


def test_non_numeric_global_confidence_returns_none():
    """Нечисловой глобальный confidence → возвращается None (вся строка невалидна)."""
    # Строка вместо числа
    text = (
        '{"name":"X","short_description":"a","description":"b",'
        '"attributes":[],"confidence":"high"}'
    )
    r = parse_enrich_output(text)
    assert r is None

    # null вместо числа
    text = (
        '{"name":"X","short_description":"a","description":"b",'
        '"attributes":[],"confidence":null}'
    )
    r = parse_enrich_output(text)
    assert r is None


def test_clamps_attr_confidence_to_0_100():
    """Атрибут confidence клампится в [0, 100]."""
    # Больше 100 → клампится до 100
    text = (
        '{"name":"X","short_description":"a","description":"b",'
        '"attributes":[{"slug":"power","value":500,"confidence":999}],"confidence":0.5}'
    )
    r = parse_enrich_output(text)
    assert r is not None
    assert len(r.attributes) == 1
    assert r.attributes[0].confidence == 100

    # Меньше 0 → клампится до 0
    text = (
        '{"name":"X","short_description":"a","description":"b",'
        '"attributes":[{"slug":"power","value":500,"confidence":-50}],"confidence":0.5}'
    )
    r = parse_enrich_output(text)
    assert r is not None
    assert r.attributes[0].confidence == 0

    # В диапазоне → не меняется
    text = (
        '{"name":"X","short_description":"a","description":"b",'
        '"attributes":[{"slug":"power","value":500,"confidence":75}],"confidence":0.5}'
    )
    r = parse_enrich_output(text)
    assert r is not None
    assert r.attributes[0].confidence == 75


def test_non_numeric_attr_confidence_defaults_60():
    """Нечисловой confidence в атрибуте → дефолтится на 60."""
    # Строка вместо числа
    text = (
        '{"name":"X","short_description":"a","description":"b",'
        '"attributes":[{"slug":"power","value":500,"confidence":"unknown"}],"confidence":0.5}'
    )
    r = parse_enrich_output(text)
    assert r is not None
    assert r.attributes[0].confidence == 60

    # null вместо числа
    text = (
        '{"name":"X","short_description":"a","description":"b",'
        '"attributes":[{"slug":"power","value":500,"confidence":null}],"confidence":0.5}'
    )
    r = parse_enrich_output(text)
    assert r is not None
    assert r.attributes[0].confidence == 60

    # Отсутствует поле → дефолтится на 60
    text = (
        '{"name":"X","short_description":"a","description":"b",'
        '"attributes":[{"slug":"power","value":500}],"confidence":0.5}'
    )
    r = parse_enrich_output(text)
    assert r is not None
    assert r.attributes[0].confidence == 60


def test_empty_text_fields_become_none():
    """Пустые/whitespace текстовые поля → None."""
    # Все поля пусты
    text = '{"name":"","short_description":"","description":"",' '"attributes":[],"confidence":0.5}'
    r = parse_enrich_output(text)
    assert r is not None
    assert r.name is None
    assert r.short_description is None
    assert r.description is None

    # Все поля — только пробелы
    text = (
        '{"name":"   ","short_description":"  \\t  ","description":"\\n",'
        '"attributes":[],"confidence":0.5}'
    )
    r = parse_enrich_output(text)
    assert r is not None
    assert r.name is None
    assert r.short_description is None
    assert r.description is None

    # Смешанный: name валидный, остальные пусты
    text = (
        '{"name":"Дрель","short_description":"","description":null,'
        '"attributes":[],"confidence":0.5}'
    )
    r = parse_enrich_output(text)
    assert r is not None
    assert r.name == "Дрель"
    assert r.short_description is None
    assert r.description is None


def test_skips_invalid_attributes():
    """Невалидные элементы attributes пропускаются, валидные остаются."""
    text = (
        '{"name":"X","short_description":"a","description":"b",'
        '"attributes":['
        '{"slug":"power","value":500},'
        '{"slug":"speed"},'
        '{"value":100},'
        '{"slug":"type","value":"electric"},'
        '"not_a_dict",'
        '{"slug":"rpm","value":3000}'
        '],"confidence":0.5}'
    )
    r = parse_enrich_output(text)
    assert r is not None
    assert len(r.attributes) == 3
    assert r.attributes[0].slug == "power" and r.attributes[0].value == 500
    assert r.attributes[1].slug == "type" and r.attributes[1].value == "electric"
    assert r.attributes[2].slug == "rpm" and r.attributes[2].value == 3000
