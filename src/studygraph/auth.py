import base64
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from dataclasses import dataclass, field

from studygraph.document_service import DEFAULT_OWNER_ID

OWNER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{0,119}$")
PASSWORD_HASH_ITERATIONS = 600_000
TOKEN_LIFETIME_SECONDS = 3_600
MAX_TRACKED_LOGIN_KEYS = 10_000


class AuthenticationError(Exception):
    """Raised when request user information is missing or invalid."""


@dataclass
class LoginRateLimiter:
    """Track failed logins per key for defense-in-depth throttling."""

    _failures: dict[str, list[float]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def is_blocked(self, key: str, *, max_attempts: int, window_seconds: int) -> bool:
        with self._lock:
            failures = self._active_failures(
                key,
                window_seconds=window_seconds,
                now=time.monotonic(),
            )
            return len(failures) >= max_attempts

    def record_failure(self, key: str, *, window_seconds: int) -> None:
        with self._lock:
            failures = self._active_failures(
                key,
                window_seconds=window_seconds,
                now=time.monotonic(),
            )
            if (
                key not in self._failures
                and len(self._failures) >= MAX_TRACKED_LOGIN_KEYS
            ):
                self._failures.pop(next(iter(self._failures)))
            failures.append(time.monotonic())
            self._failures[key] = failures

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def _active_failures(
        self,
        key: str,
        *,
        window_seconds: int,
        now: float,
    ) -> list[float]:
        cutoff = now - window_seconds
        failures = [
            timestamp
            for timestamp in self._failures.get(key, [])
            if timestamp > cutoff
        ]
        if failures:
            self._failures[key] = failures
        else:
            self._failures.pop(key, None)
        return failures


login_rate_limiter = LoginRateLimiter()
answer_rate_limiter = LoginRateLimiter()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    return (
        f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${_encode_bytes(salt)}"
        f"${_encode_bytes(digest)}"
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations, encoded_salt, encoded_digest = password_hash.split(
            "$",
            maxsplit=3,
        )
        if algorithm != "pbkdf2_sha256":
            return False
        salt = _decode_bytes(encoded_salt)
        expected_digest = _decode_bytes(encoded_digest)
        actual_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            int(iterations),
        )
    except (TypeError, ValueError):
        return False

    return hmac.compare_digest(actual_digest, expected_digest)


def create_access_token(
    owner_id: str,
    *,
    secret: str,
    lifetime_seconds: int = TOKEN_LIFETIME_SECONDS,
) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": owner_id, "iat": now, "exp": now + lifetime_seconds}
    encoded_header = _encode_json(header)
    encoded_payload = _encode_json(payload)
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256)
    return f"{encoded_header}.{encoded_payload}.{_encode_bytes(signature.digest())}"


def decode_access_token(token: str, *, secret: str) -> str:
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".")
        signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
        expected_signature = hmac.new(
            secret.encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).digest()
        signature = _decode_bytes(encoded_signature)
        if not hmac.compare_digest(signature, expected_signature):
            raise AuthenticationError("Invalid access token.")

        header = json.loads(_decode_bytes(encoded_header).decode("utf-8"))
        payload = json.loads(_decode_bytes(encoded_payload).decode("utf-8"))
        if header != {"alg": "HS256", "typ": "JWT"}:
            raise AuthenticationError("Invalid access token.")
        if not isinstance(payload.get("sub"), str) or not payload["sub"]:
            raise AuthenticationError("Invalid access token.")
        if int(payload.get("exp", 0)) <= int(time.time()):
            raise AuthenticationError("Access token has expired.")
        return resolve_owner_id(payload["sub"], require_header=True)
    except (AuthenticationError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise AuthenticationError("Invalid access token.") from None


def _encode_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _encode_json(value: dict[str, object]) -> str:
    return _encode_bytes(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )


def _decode_bytes(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@dataclass(frozen=True)
class CurrentUser:
    owner_id: str


def resolve_owner_id(
    raw_owner_id: str | None,
    *,
    require_header: bool,
) -> str:
    if raw_owner_id is None:
        if require_header:
            raise AuthenticationError("X-StudyGraph-User header is required.")

        return DEFAULT_OWNER_ID

    owner_id = raw_owner_id.strip()

    if not owner_id:
        raise AuthenticationError(
            "X-StudyGraph-User must contain non-whitespace text."
        )

    if not OWNER_ID_PATTERN.fullmatch(owner_id):
        raise AuthenticationError(
            "X-StudyGraph-User may only contain letters, numbers, dots, "
            "underscores, hyphens, and @."
        )

    return owner_id
