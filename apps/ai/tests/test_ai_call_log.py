import pytest
from apps.ai.models import AiCallLog


@pytest.mark.django_db
def test_ai_call_log_minimal():
    log = AiCallLog.objects.create(
        capability=AiCallLog.Capability.ENRICH,
        provider="dummy",
        model="dummy-1",
        status=AiCallLog.Status.OK,
        entity_ref=123,
    )
    assert log.pk and log.created_at is not None
    assert log.tokens_in == 0 and log.tokens_out == 0
