import os

DATABASE_URL_ENV_VAR = "DATABASE_URL"


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
