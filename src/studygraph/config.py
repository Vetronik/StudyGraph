import os

DATABASE_URL_ENV_VAR = "DATABASE_URL"
AUTH_SECRET_ENV_VAR = "STUDYGRAPH_AUTH_SECRET"
REQUIRE_AUTH_TOKEN_ENV_VAR = "STUDYGRAPH_REQUIRE_AUTH_TOKEN"
DOCUMENT_STORAGE_DIR_ENV_VAR = "STUDYGRAPH_DOCUMENT_STORAGE_DIR"
LOG_LEVEL_ENV_VAR = "STUDYGRAPH_LOG_LEVEL"
MAX_DOCUMENT_CHARACTERS_ENV_VAR = "STUDYGRAPH_MAX_DOCUMENT_CHARACTERS"
MAX_DOCUMENT_PAGES_ENV_VAR = "STUDYGRAPH_MAX_DOCUMENT_PAGES"
MAX_UPLOAD_BYTES_ENV_VAR = "STUDYGRAPH_MAX_UPLOAD_BYTES"
MAX_PROCESSING_ATTEMPTS_ENV_VAR = "STUDYGRAPH_MAX_PROCESSING_ATTEMPTS"
PROCESS_UPLOADS_IN_API_ENV_VAR = "STUDYGRAPH_PROCESS_UPLOADS_IN_API"
AUTH_MAX_LOGIN_ATTEMPTS_ENV_VAR = "STUDYGRAPH_AUTH_MAX_LOGIN_ATTEMPTS"
AUTH_RATE_WINDOW_SECONDS_ENV_VAR = "STUDYGRAPH_AUTH_RATE_WINDOW_SECONDS"
ALLOWED_HOSTS_ENV_VAR = "STUDYGRAPH_ALLOWED_HOSTS"
REQUIRE_USER_HEADER_ENV_VAR = "STUDYGRAPH_REQUIRE_USER_HEADER"
OCR_ENABLED_ENV_VAR = "STUDYGRAPH_OCR_ENABLED"
OCR_LANGUAGE_ENV_VAR = "STUDYGRAPH_OCR_LANGUAGE"
EMBEDDING_PROVIDER_ENV_VAR = "STUDYGRAPH_EMBEDDING_PROVIDER"
EMBEDDING_MODEL_ENV_VAR = "STUDYGRAPH_EMBEDDING_MODEL"
EMBEDDING_API_KEY_ENV_VAR = "STUDYGRAPH_EMBEDDING_API_KEY"
EMBEDDING_API_URL_ENV_VAR = "STUDYGRAPH_EMBEDDING_API_URL"
ANSWER_PROVIDER_ENV_VAR = "STUDYGRAPH_ANSWER_PROVIDER"
ANSWER_MODEL_ENV_VAR = "STUDYGRAPH_ANSWER_MODEL"
ANSWER_API_KEY_ENV_VAR = "STUDYGRAPH_ANSWER_API_KEY"
ANSWER_API_URL_ENV_VAR = "STUDYGRAPH_ANSWER_API_URL"
ANSWER_TIMEOUT_SECONDS_ENV_VAR = "STUDYGRAPH_ANSWER_TIMEOUT_SECONDS"

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_DOCUMENT_STORAGE_DIR = "data/documents"
DEFAULT_AUTH_SECRET = "development-only-change-this-secret"
DEFAULT_MAX_DOCUMENT_CHARACTERS = 1_000_000
DEFAULT_MAX_DOCUMENT_PAGES = 500
DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_PROCESSING_ATTEMPTS = 3
DEFAULT_AUTH_MAX_LOGIN_ATTEMPTS = 10
DEFAULT_AUTH_RATE_WINDOW_SECONDS = 300
DEFAULT_ALLOWED_HOSTS = "*"
DEFAULT_OCR_LANGUAGE = "eng"
DEFAULT_EMBEDDING_PROVIDER = "deterministic"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EMBEDDING_API_URL = "https://api.openai.com/v1/embeddings"
DEFAULT_ANSWER_PROVIDER = "local"
DEFAULT_ANSWER_MODEL = "gpt-4o-mini"
DEFAULT_ANSWER_API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_ANSWER_TIMEOUT_SECONDS = 30
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


def get_document_storage_dir() -> str:
    value = os.environ.get(
        DOCUMENT_STORAGE_DIR_ENV_VAR,
        DEFAULT_DOCUMENT_STORAGE_DIR,
    ).strip()

    if not value:
        raise ConfigurationError(
            f"{DOCUMENT_STORAGE_DIR_ENV_VAR} must contain a directory path."
        )

    return value


def get_auth_secret() -> str:
    configured_value = os.environ.get(AUTH_SECRET_ENV_VAR)
    if get_require_auth_token() and not configured_value:
        raise ConfigurationError(
            f"{AUTH_SECRET_ENV_VAR} must be explicitly configured when "
            f"{REQUIRE_AUTH_TOKEN_ENV_VAR} is enabled."
        )

    value = configured_value or DEFAULT_AUTH_SECRET
    if len(value) < 32:
        raise ConfigurationError(
            f"{AUTH_SECRET_ENV_VAR} must contain at least 32 characters."
        )
    return value


def get_require_auth_token() -> bool:
    raw_value = os.environ.get(REQUIRE_AUTH_TOKEN_ENV_VAR)
    if raw_value is None:
        return False

    normalized_value = raw_value.strip().lower()
    if normalized_value in {"1", "true", "yes", "on"}:
        return True
    if normalized_value in {"0", "false", "no", "off"}:
        return False

    raise ConfigurationError(
        f"{REQUIRE_AUTH_TOKEN_ENV_VAR} must be a boolean value."
    )


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


def get_max_processing_attempts() -> int:
    return _get_positive_int_from_env(
        MAX_PROCESSING_ATTEMPTS_ENV_VAR,
        DEFAULT_MAX_PROCESSING_ATTEMPTS,
    )


def get_process_uploads_in_api() -> bool:
    raw_value = os.environ.get(PROCESS_UPLOADS_IN_API_ENV_VAR, "true")
    normalized_value = raw_value.strip().lower()
    if normalized_value in {"1", "true", "yes", "on"}:
        return True
    if normalized_value in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(
        f"{PROCESS_UPLOADS_IN_API_ENV_VAR} must be a boolean value."
    )


def get_auth_max_login_attempts() -> int:
    return _get_positive_int_from_env(
        AUTH_MAX_LOGIN_ATTEMPTS_ENV_VAR,
        DEFAULT_AUTH_MAX_LOGIN_ATTEMPTS,
    )


def get_auth_rate_window_seconds() -> int:
    return _get_positive_int_from_env(
        AUTH_RATE_WINDOW_SECONDS_ENV_VAR,
        DEFAULT_AUTH_RATE_WINDOW_SECONDS,
    )


def get_allowed_hosts() -> list[str]:
    raw_value = os.environ.get(ALLOWED_HOSTS_ENV_VAR, DEFAULT_ALLOWED_HOSTS)
    hosts = [host.strip() for host in raw_value.split(",") if host.strip()]
    if not hosts:
        raise ConfigurationError(
            f"{ALLOWED_HOSTS_ENV_VAR} must contain at least one host."
        )
    return hosts


def get_answer_provider_name() -> str:
    value = os.environ.get(ANSWER_PROVIDER_ENV_VAR, DEFAULT_ANSWER_PROVIDER)
    normalized_value = value.strip().lower()
    if normalized_value not in {"local", "openai-compatible"}:
        raise ConfigurationError(
            f"{ANSWER_PROVIDER_ENV_VAR} must be local or openai-compatible."
        )
    return normalized_value


def get_answer_model() -> str:
    value = os.environ.get(ANSWER_MODEL_ENV_VAR, DEFAULT_ANSWER_MODEL).strip()
    if not value:
        raise ConfigurationError(f"{ANSWER_MODEL_ENV_VAR} must not be empty.")
    return value


def get_answer_api_key() -> str:
    return os.environ.get(ANSWER_API_KEY_ENV_VAR, "").strip()


def get_answer_api_url() -> str:
    value = os.environ.get(ANSWER_API_URL_ENV_VAR, DEFAULT_ANSWER_API_URL).strip()
    if not value.startswith(("https://", "http://")):
        raise ConfigurationError(f"{ANSWER_API_URL_ENV_VAR} must be an HTTP(S) URL.")
    return value


def get_answer_timeout_seconds() -> int:
    return _get_positive_int_from_env(
        ANSWER_TIMEOUT_SECONDS_ENV_VAR,
        DEFAULT_ANSWER_TIMEOUT_SECONDS,
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


def get_ocr_enabled() -> bool:
    raw_value = os.environ.get(OCR_ENABLED_ENV_VAR, "false").strip().lower()
    if raw_value in {"1", "true", "yes", "on"}:
        return True
    if raw_value in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{OCR_ENABLED_ENV_VAR} must be a boolean value.")


def get_ocr_language() -> str:
    value = os.environ.get(OCR_LANGUAGE_ENV_VAR, DEFAULT_OCR_LANGUAGE).strip()
    allowed_characters = "abcdefghijklmnopqrstuvwxyz+_-"
    if not value or any(
        character not in allowed_characters for character in value.lower()
    ):
        raise ConfigurationError(
            f"{OCR_LANGUAGE_ENV_VAR} must contain valid Tesseract language codes."
        )
    return value


def get_embedding_provider_name() -> str:
    value = os.environ.get(
        EMBEDDING_PROVIDER_ENV_VAR,
        DEFAULT_EMBEDDING_PROVIDER,
    ).strip().lower()
    if value not in {"deterministic", "openai-compatible"}:
        raise ConfigurationError(
            f"{EMBEDDING_PROVIDER_ENV_VAR} must be deterministic or "
            "openai-compatible."
        )
    return value


def get_embedding_model() -> str:
    value = os.environ.get(EMBEDDING_MODEL_ENV_VAR, DEFAULT_EMBEDDING_MODEL).strip()
    if not value:
        raise ConfigurationError(f"{EMBEDDING_MODEL_ENV_VAR} must not be empty.")
    return value


def get_embedding_api_key() -> str:
    return os.environ.get(EMBEDDING_API_KEY_ENV_VAR, "").strip()


def get_embedding_api_url() -> str:
    value = os.environ.get(
        EMBEDDING_API_URL_ENV_VAR,
        DEFAULT_EMBEDDING_API_URL,
    ).strip()
    if not value.startswith(("https://", "http://")):
        raise ConfigurationError(
            f"{EMBEDDING_API_URL_ENV_VAR} must be an HTTP(S) URL."
        )
    return value




def get_log_level() -> str:
    raw_value = os.environ.get(LOG_LEVEL_ENV_VAR, DEFAULT_LOG_LEVEL)
    log_level = raw_value.strip().upper()

    if log_level not in VALID_LOG_LEVELS:
        allowed_values = ", ".join(sorted(VALID_LOG_LEVELS))
        raise ConfigurationError(
            f"{LOG_LEVEL_ENV_VAR} must be one of: {allowed_values}."
        )

    return log_level
