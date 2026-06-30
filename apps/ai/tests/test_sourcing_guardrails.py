from apps.ai.sourcing.guardrails import validate
from apps.ai.sourcing.ports import Finding, SourceQuery
from apps.ai.sourcing.sources.dummy import DummySource


def _f(**kw):
    base = dict(
        target_kind="description",
        attribute_slug="",
        value={"type": "text", "value": "Перфоратор для бетона"},
        canonical_url="https://makita.ru/x",
        confidence=0.8,
        source_name="web",
    )
    base.update(kw)
    return Finding(**base)


def test_web_without_url_rejected():
    assert validate(_f(canonical_url="")) is None


def test_forbidden_target_rejected():
    assert validate(_f(target_kind="price")) is None
    assert validate(_f(target_kind="attribute", attribute_slug="stock_quantity")) is None


def test_confidence_clamped():
    assert validate(_f(confidence=5.0)).confidence == 1.0
    assert validate(_f(confidence=-1.0)).confidence == 0.0


def test_marketplace_without_url_allowed():
    assert validate(_f(source_name="marketplace", canonical_url="")) is not None


def test_dummy_source_returns_reply():
    reply = DummySource().find(
        SourceQuery(
            article="HR2470",
            name="Перфоратор Makita HR2470",
            brand="Makita",
            category="perf",
            needed_targets=["description"],
        ),
        idempotency_key="k",
    )
    assert reply.provider == "dummy" and reply.findings
    assert all(f.canonical_url for f in reply.findings)
