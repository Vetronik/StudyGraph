import os

DATABASE_URL_ENV_VAR = "DATABASE_URL"
LOG_LEVEL_ENV_VAR = "STUDYGRAPH_LOG_LEVEL"
MAX_DOCUMENT_CHARACTERS_ENV_VAR = "STUDYGRAPH_MAX_DOCUMENT_CHARACTERS"
MAX_DOCUMENT_PAGES_ENV_VAR = "STUDYGRAPH_MAX_DOCUMENT_PAGES"
MAX_UPLOAD_BYTES_ENV_VAR = "STUDYGRAPH_MAX_UPLOAD_BYTES"
REQUIRE_USER_HEADER_ENV_VAR = "STUDYGRAPH_REQUIRE_USER_HEADER"

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_MAX_DOCUMENT_CHARACTERS = 1_000_000
DEFAULT_MAX_DOCUMENT_PAGES = 500
DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
VALID_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}


class ConfigurationError(RuntimeError):
    """Raised when required application configuration is missing or invalid."""


def get_database_url() -> str:
    database_url = os.environ.get(DATABASE_URL_ENV_VAR)

    if not database_url:
        raise ConfigurationError(
            f"{DATABASE_URL_ENV_VAR} environment variable is not set."
        )

    if not database_url.startswith(("postgresql://", "postgresql+")):
        raise ConfigurationError(
            f"{DATABASE_URL_ENV_VAR} must be a PostgreSQL connection URL."
        )

    return database_url


def is_database_configured() -> bool:
    try:
        get_database_url()
    except ConfigurationError:
        return False

    return True


def _get_positive_int_from_env(env_var_name: str, default: int) -> int:
    raw_value = os.environ.get(env_var_name)

    if raw_value is None:
        return default

    try:
        value = int(raw_value)
    except ValueError as error:
        raise ConfigurationError(
            f"{env_var_name} must be a positive integer."
        ) from error

    if value <= 0:
        raise ConfigurationError(f"{env_var_name} must be greater than 0.")

    return value


def get_max_upload_bytes() -> int:
    return _get_positive_int_from_env(
        MAX_UPLOAD_BYTES_ENV_VAR,
        DEFAULT_MAX_UPLOAD_BYTES,
    )


def get_max_document_pages() -> int:
    return _get_positive_int_from_env(
        MAX_DOCUMENT_PAGES_ENV_VAR,
        DEFAULT_MAX_DOCUMENT_PAGES,
    )


def get_max_document_characters() -> int:
    return _get_positive_int_from_env(
        MAX_DOCUMENT_CHARACTERS_ENV_VAR,
        DEFAULT_MAX_DOCUMENT_CHARACTERS,
    )


def get_require_user_header() -> bool:
    raw_value = os.environ.get(REQUIRE_USER_HEADER_ENV_VAR)

    if raw_value is None:
        return False

    normalized_value = raw_value.strip().lower()

    if normalized_value in {"1", "true", "yes", "on"}:
        return True

    if normalized_value in {"0", "false", "no", "off"}:
        return False

    raise ConfigurationError(
        f"{REQUIRE_USER_HEADER_ENV_VAR} must be a boolean value."
    )


def get_log_level() -> str:
    raw_value = os.environ.get(LOG_LEVEL_ENV_VAR, DEFAULT_LOG_LEVEL)
    log_level = raw_value.strip().upper()

    if log_level not in VALID_LOG_LEVELS:
        allowed_values = ", ".join(sorted(VALID_LOG_LEVELS))
        raise ConfigurationError(
            f"{LOG_LEVEL_ENV_VAR} must be one of: {allowed_values}."
        )

    return log_level
