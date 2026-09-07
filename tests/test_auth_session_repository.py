import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from studygraph.auth_session_repository import AuthSessionRepository
from studygraph.document_model import Base

pytestmark = pytest.mark.postgresql


@pytest.fixture
def database_session() -> tuple[Session, object]:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not set.")
    url = make_url(database_url)
    if not url.database or "test" not in url.database.lower():
        pytest.skip("TEST_DATABASE_URL must point to a dedicated test database.")

    engine = create_engine(database_url, pool_pre_ping=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        yield session, engine
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_auth_session_can_be_revoked_and_is_owner_scoped(
    database_session: tuple[Session, object],
) -> None:
    session, _engine = database_session
    repository = AuthSessionRepository(session)
    expires_at = datetime.now(UTC) + timedelta(minutes=5)

    repository.create(
        token_id="token-a",
        owner_id="owner-a",
        expires_at=expires_at,
    )

    assert repository.is_active(token_id="token-a", owner_id="owner-a")
    assert not repository.is_active(token_id="token-a", owner_id="owner-b")
    assert repository.revoke(token_id="token-a", owner_id="owner-a")
    assert not repository.is_active(token_id="token-a", owner_id="owner-a")
    assert not repository.revoke(token_id="token-a", owner_id="owner-a")


def test_expired_auth_session_is_not_active(
    database_session: tuple[Session, object],
) -> None:
    session, _engine = database_session
    repository = AuthSessionRepository(session)

    repository.create(
        token_id="expired-token",
        owner_id="owner-a",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    assert not repository.is_active(
        token_id="expired-token",
        owner_id="owner-a",
    )


def test_purge_inactive_removes_expired_sessions(
    database_session: tuple[Session, object],
) -> None:
    session, _engine = database_session
    repository = AuthSessionRepository(session)

    repository.create(
        token_id="expired-token",
        owner_id="owner-a",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    repository.create(
        token_id="active-token",
        owner_id="owner-a",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )

    assert repository.purge_inactive() == 1
    assert not repository.is_active(token_id="expired-token", owner_id="owner-a")
    assert repository.is_active(token_id="active-token", owner_id="owner-a")
