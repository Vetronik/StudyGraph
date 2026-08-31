import re
from dataclasses import dataclass

from studygraph.document_service import DEFAULT_OWNER_ID

OWNER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{0,119}$")


class AuthenticationError(Exception):
    """Raised when request user information is missing or invalid."""


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
