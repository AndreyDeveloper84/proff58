"""Тесты классификации ошибок провайдера MAX и retry-политики (#521)."""

from __future__ import annotations

import email.message
import urllib.error
from unittest import mock

import pytest
from django.test import override_settings

from .channels import max as max_channel
from .channels.max import MaxPermanentError, MaxRetryableError

MAX_SETTINGS = {"MAX_BOT_TOKEN": "test-token", "MAX_BOT_API_URL": "https://test.max.ru"}


def _http_error(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    hdrs = email.message.Message()
    if retry_after is not None:
        hdrs["Retry-After"] = retry_after
    return urllib.error.HTTPError(
        url="https://test.max.ru/messages", code=code, msg="", hdrs=hdrs, fp=None
    )


# ═══════════════════════════════════════════════════════════════════════
# channels/max.py — классификация
# ═══════════════════════════════════════════════════════════════════════


@override_settings(**MAX_SETTINGS)
@mock.patch(
    "urllib.request.urlopen",
    side_effect=lambda *a, **kw: (_ for _ in ()).throw(_http_error(429, "7")),
)
def test_429_is_retryable_with_retry_after(mock_urlopen):
    with pytest.raises(MaxRetryableError) as exc_info:
        max_channel.send_message(123, "text")
    assert exc_info.value.retry_after == 7


@override_settings(**MAX_SETTINGS)
@mock.patch(
    "urllib.request.urlopen", side_effect=lambda *a, **kw: (_ for _ in ()).throw(_http_error(429))
)
def test_429_without_retry_after_header(mock_urlopen):
    with pytest.raises(MaxRetryableError) as exc_info:
        max_channel.send_message(123, "text")
    assert exc_info.value.retry_after is None


@override_settings(**MAX_SETTINGS)
@mock.patch(
    "urllib.request.urlopen", side_effect=lambda *a, **kw: (_ for _ in ()).throw(_http_error(503))
)
def test_5xx_is_retryable(mock_urlopen):
    with pytest.raises(MaxRetryableError):
        max_channel.send_message(123, "text")


@pytest.mark.parametrize("code", [400, 401, 403, 404])
@override_settings(**MAX_SETTINGS)
def test_4xx_other_than_429_is_permanent(code):
    with mock.patch(
        "urllib.request.urlopen",
        side_effect=lambda *a, **kw: (_ for _ in ()).throw(_http_error(code)),
    ):
        with pytest.raises(MaxPermanentError):
            max_channel.send_message(123, "text")


@override_settings(**MAX_SETTINGS)
@mock.patch("urllib.request.urlopen", side_effect=TimeoutError("timed out"))
def test_socket_timeout_is_retryable(mock_urlopen):
    with pytest.raises(MaxRetryableError):
        max_channel.send_message(123, "text")


@override_settings(**MAX_SETTINGS)
@mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused"))
def test_network_error_is_retryable(mock_urlopen):
    with pytest.raises(MaxRetryableError):
        max_channel.send_message(123, "text")


@override_settings(MAX_BOT_TOKEN="")
def test_missing_token_is_permanent():
    with pytest.raises(MaxPermanentError):
        max_channel.send_message(123, "text")


def test_classification_errors_do_not_log_chat_id(caplog):
    with override_settings(**MAX_SETTINGS):
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=lambda *a, **kw: (_ for _ in ()).throw(_http_error(500)),
        ):
            with pytest.raises(MaxRetryableError):
                max_channel.send_message(999888777, "секретный текст сообщения")

    for record in caplog.records:
        assert "999888777" not in record.getMessage()
        assert "секретный текст" not in record.getMessage()
