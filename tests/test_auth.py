import pytest

from studygraph.auth import AuthenticationError, resolve_owner_id
from studygraph.document_service import DEFAULT_OWNER_ID


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
