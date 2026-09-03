import pytest

from studygraph.config import (
    LOG_LEVEL_ENV_VAR,
    ConfigurationError,
    get_log_level,
    get_max_processing_attempts,
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
