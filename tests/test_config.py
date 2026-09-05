import pytest

from studygraph.config import (
    AUTH_SECRET_ENV_VAR,
    LOG_LEVEL_ENV_VAR,
    REQUIRE_AUTH_TOKEN_ENV_VAR,
    ConfigurationError,
    get_auth_secret,
    get_log_level,
    get_max_processing_attempts,
    get_process_uploads_in_api,
)


def test_get_log_level_defaults_to_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(LOG_LEVEL_ENV_VAR, raising=False)

    assert get_log_level() == "INFO"


def test_get_log_level_normalizes_configured_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LOG_LEVEL_ENV_VAR, " debug ")

    assert get_log_level() == "DEBUG"


def test_get_log_level_rejects_invalid_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LOG_LEVEL_ENV_VAR, "verbose")

    with pytest.raises(ConfigurationError, match=LOG_LEVEL_ENV_VAR):
        get_log_level()


def test_max_processing_attempts_can_be_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STUDYGRAPH_MAX_PROCESSING_ATTEMPTS", "4")

    assert get_max_processing_attempts() == 4


def test_auth_secret_is_required_when_bearer_auth_is_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(AUTH_SECRET_ENV_VAR, raising=False)
    monkeypatch.setenv(REQUIRE_AUTH_TOKEN_ENV_VAR, "true")

    with pytest.raises(ConfigurationError, match=AUTH_SECRET_ENV_VAR):
        get_auth_secret()


def test_auth_secret_defaults_for_local_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(AUTH_SECRET_ENV_VAR, raising=False)
    monkeypatch.setenv(REQUIRE_AUTH_TOKEN_ENV_VAR, "false")

    assert len(get_auth_secret()) >= 32


def test_api_upload_processing_defaults_to_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STUDYGRAPH_PROCESS_UPLOADS_IN_API", raising=False)

    assert get_process_uploads_in_api() is True


def test_api_upload_processing_can_be_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STUDYGRAPH_PROCESS_UPLOADS_IN_API", "false")

    assert get_process_uploads_in_api() is False
