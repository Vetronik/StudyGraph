import pytest

from studygraph.auth import (
    AuthenticationError,
    LoginRateLimiter,
    create_access_token,
    decode_access_token,
    hash_password,
    resolve_owner_id,
    verify_password,
)
from studygraph.auth_service import AuthService, InvalidCredentialsError
from studygraph.document_service import DEFAULT_OWNER_ID


class InMemoryUserRepository:
    def __init__(self) -> None:
        self.users: dict[str, object] = {}

    def add(self, username: str, password_hash: str) -> object:
        if username in self.users:
            raise ValueError("Username already exists.")

        user = type(
            "UserRecord",
            (),
            {"username": username, "password_hash": password_hash},
        )()
        self.users[username] = user
        return user

    def get_by_username(self, username: str) -> object | None:
        return self.users.get(username)


def test_resolve_owner_id_defaults_to_local_user_when_header_is_optional() -> None:
    assert resolve_owner_id(None, require_header=False) == DEFAULT_OWNER_ID


def test_resolve_owner_id_requires_header_when_configured() -> None:
    with pytest.raises(AuthenticationError, match="header is required"):
        resolve_owner_id(None, require_header=True)


def test_resolve_owner_id_trims_valid_header_value() -> None:
    assert resolve_owner_id(" alice@example.com ", require_header=True) == (
        "alice@example.com"
    )


def test_resolve_owner_id_rejects_invalid_characters() -> None:
    with pytest.raises(AuthenticationError, match="may only contain"):
        resolve_owner_id("owner/a", require_header=True)


def test_password_hash_can_be_verified_without_exposing_password() -> None:
    password_hash = hash_password("correct horse battery staple")

    assert password_hash != "correct horse battery staple"
    assert verify_password("correct horse battery staple", password_hash)
    assert not verify_password("wrong password", password_hash)


def test_access_token_round_trip() -> None:
    token = create_access_token("alice", secret="s" * 32)

    assert decode_access_token(token, secret="s" * 32) == "alice"


def test_access_token_rejects_wrong_secret() -> None:
    token = create_access_token("alice", secret="s" * 32)

    with pytest.raises(AuthenticationError, match="Invalid access token"):
        decode_access_token(token, secret="t" * 32)


def test_auth_service_registers_and_authenticates_user() -> None:
    repository = InMemoryUserRepository()
    service = AuthService(repository)

    registered_user = service.register("alice", "correct horse battery staple")

    assert registered_user.username == "alice"
    assert service.authenticate("alice", "correct horse battery staple")


def test_auth_service_rejects_invalid_credentials() -> None:
    repository = InMemoryUserRepository()
    service = AuthService(repository)
    service.register("alice", "correct horse battery staple")

    with pytest.raises(InvalidCredentialsError):
        service.authenticate("alice", "wrong password")


def test_login_rate_limiter_blocks_after_failed_attempt_limit() -> None:
    limiter = LoginRateLimiter()

    limiter.record_failure("client-a", window_seconds=300)
    limiter.record_failure("client-a", window_seconds=300)

    assert limiter.is_blocked(
        "client-a",
        max_attempts=2,
        window_seconds=300,
    )
    assert not limiter.is_blocked(
        "client-b",
        max_attempts=2,
        window_seconds=300,
    )


def test_login_rate_limiter_reset_allows_login_again() -> None:
    limiter = LoginRateLimiter()
    limiter.record_failure("client-a", window_seconds=300)

    limiter.reset("client-a")

    assert not limiter.is_blocked(
        "client-a",
        max_attempts=1,
        window_seconds=300,
    )
