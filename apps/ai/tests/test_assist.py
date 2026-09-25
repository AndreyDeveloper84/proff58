"""Тесты контракта ai_assist (#74): AssistReply + assist() stub."""

import pytest

from apps.ai.services import AssistReply, assist


@pytest.mark.django_db
class TestAssistContract:
    def test_returns_assist_reply_instance(self):
        result = assist(message="Что посоветуете?")
        assert isinstance(result, AssistReply)

    def test_text_is_non_empty_string(self):
        result = assist(message="Привет")
        assert isinstance(result.text, str)
        assert len(result.text) > 0

    def test_is_stub_flag_true(self):
        result = assist(message="Тест")
        assert result.is_stub is True

    def test_suggestions_is_list(self):
        result = assist(message="Тест")
        assert isinstance(result.suggestions, list)

    def test_session_echoed_when_provided(self):
        result = assist(message="Тест", session="ses-123")
        assert result.session_id == "ses-123"

    def test_session_empty_when_not_provided(self):
        result = assist(message="Тест")
        assert result.session_id == ""

    def test_keyword_only_args(self):
        """message и session — keyword-only; позиционный вызов должен упасть."""
        with pytest.raises(TypeError):
            assist("Тест")  # type: ignore[call-arg]
