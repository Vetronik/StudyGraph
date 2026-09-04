import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from studygraph.collection_repository import CollectionRepository
from studygraph.document_model import Base, Document

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


@pytest.fixture
def repository(database_session: tuple[Session, object]) -> CollectionRepository:
    session, _engine = database_session
    return CollectionRepository(session)


@pytest.fixture
def session(database_session: tuple[Session, object]) -> Session:
    session, _engine = database_session
    return session


def test_collection_repository_manages_document_membership(
    repository: CollectionRepository,
    session: Session,
) -> None:
    collection = repository.create(owner_id="owner-a", name="Calculus")
    document = Document(
        filename="lecture.pdf",
        owner_id="owner-a",
        page_count=1,
        character_count=16,
        extracted_text="Calculus material",
    )
    session.add(document)
    session.commit()

    loaded = repository.add_document(
        collection.id,
        document.id,
        owner_id="owner-a",
    )
    assert loaded is not None
    assert [item.filename for item in loaded.documents] == ["lecture.pdf"]

    loaded = repository.remove_document(
        collection.id,
        document.id,
        owner_id="owner-a",
    )
    assert loaded is not None
    assert loaded.documents == []


def test_collection_repository_scopes_collections_by_owner(
    repository: CollectionRepository,
) -> None:
    collection = repository.create(owner_id="owner-a", name="Private")

    assert repository.get(collection.id, owner_id="owner-b") is None
    assert repository.list(owner_id="owner-b") == []
