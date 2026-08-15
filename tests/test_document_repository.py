import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from studygraph.document_model import Base, Document
from studygraph.document_repository import DocumentRepository

TEST_DATABASE_URL_ENV_VAR = "TEST_DATABASE_URL"

pytestmark = pytest.mark.postgresql


@pytest.fixture
def repository() -> DocumentRepository:
    database_url = os.environ.get(TEST_DATABASE_URL_ENV_VAR)

    if not database_url:
        pytest.skip(f"{TEST_DATABASE_URL_ENV_VAR} is not set.")

    url = make_url(database_url)

    if not url.database or "test" not in url.database.lower():
        pytest.skip(
            f"{TEST_DATABASE_URL_ENV_VAR} must point to a dedicated test database."
        )

    engine = create_engine(database_url, pool_pre_ping=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    with Session() as session:
        yield DocumentRepository(session)

    Base.metadata.drop_all(engine)
    engine.dispose()


def test_document_repository_saves_and_loads_document(
    repository: DocumentRepository,
) -> None:
    document = Document(
        filename="lecture.pdf",
        page_count=1,
        character_count=24,
        extracted_text="StudyGraph persisted text",
    )

    saved_document = repository.add(document)
    loaded_document = repository.get_by_id(saved_document.id)

    assert saved_document.id is not None
    assert saved_document.created_at is not None
    assert loaded_document is not None
    assert loaded_document.id == saved_document.id
    assert loaded_document.filename == "lecture.pdf"
    assert loaded_document.extracted_text == "StudyGraph persisted text"
