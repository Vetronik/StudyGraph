import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from studygraph.document_model import Base, Document, DocumentChunk
from studygraph.document_repository import DocumentRepository
from studygraph.document_service import DEFAULT_OWNER_ID

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
    loaded_document = repository.get_by_id(
        saved_document.id,
        owner_id=DEFAULT_OWNER_ID,
    )

    assert saved_document.id is not None
    assert saved_document.created_at is not None
    assert loaded_document is not None
    assert loaded_document.id == saved_document.id
    assert loaded_document.filename == "lecture.pdf"
    assert loaded_document.extracted_text == "StudyGraph persisted text"


def test_document_repository_saves_and_lists_document_chunks(
    repository: DocumentRepository,
) -> None:
    document = Document(
        filename="lecture.pdf",
        page_count=1,
        character_count=36,
        extracted_text="First chunk text. Second chunk text.",
    )
    document.chunks = [
        DocumentChunk(position=0, text="First chunk text.", character_count=17),
        DocumentChunk(position=1, text="Second chunk text.", character_count=18),
    ]

    saved_document = repository.add(document)
    chunks = repository.list_chunks(
        saved_document.id,
        owner_id=DEFAULT_OWNER_ID,
    )

    assert [chunk.position for chunk in chunks] == [0, 1]
    assert [chunk.page_number for chunk in chunks] == [1, 1]
    assert [chunk.document_id for chunk in chunks] == [
        saved_document.id,
        saved_document.id,
    ]
    assert [chunk.text for chunk in chunks] == [
        "First chunk text.",
        "Second chunk text.",
    ]


def test_document_repository_lists_documents_with_search(
    repository: DocumentRepository,
) -> None:
    calculus_document = repository.add(
        Document(
            filename="calculus.pdf",
            page_count=2,
            character_count=26,
            extracted_text="Derivatives and chain rule",
        )
    )
    repository.add(
        Document(
            filename="history.pdf",
            page_count=3,
            character_count=21,
            extracted_text="Roman empire overview",
        )
    )

    documents, total = repository.list_documents(
        owner_id=DEFAULT_OWNER_ID,
        limit=10,
        offset=0,
        query="derivatives",
    )

    assert total == 1
    assert [document.id for document in documents] == [calculus_document.id]


def test_document_repository_searches_document_chunks(
    repository: DocumentRepository,
) -> None:
    calculus_document = Document(
        filename="calculus.pdf",
        page_count=1,
        character_count=26,
        extracted_text="Derivatives and chain rule",
    )
    calculus_document.chunks = [
        DocumentChunk(
            position=0,
            text="Derivatives and chain rule",
            character_count=26,
        )
    ]
    repository.add(calculus_document)
    history_document = Document(
        filename="history.pdf",
        page_count=1,
        character_count=21,
        extracted_text="Roman empire overview",
    )
    history_document.chunks = [
        DocumentChunk(
            position=0,
            text="Roman empire overview",
            character_count=21,
        )
    ]
    repository.add(history_document)

    chunks, total = repository.search_chunks(
        owner_id=DEFAULT_OWNER_ID,
        query="derivatives",
        limit=10,
        offset=0,
    )

    assert total == 1
    assert [chunk.text for chunk in chunks] == ["Derivatives and chain rule"]
    assert chunks[0].document.filename == "calculus.pdf"


def test_document_repository_scopes_documents_by_owner(
    repository: DocumentRepository,
) -> None:
    first_document = repository.add(
        Document(
            filename="first.pdf",
            owner_id="owner-a",
            page_count=1,
            character_count=16,
            extracted_text="Owner A material",
        )
    )
    repository.add(
        Document(
            filename="second.pdf",
            owner_id="owner-b",
            page_count=1,
            character_count=16,
            extracted_text="Owner B material",
        )
    )

    documents, total = repository.list_documents(
        owner_id="owner-a",
        limit=10,
        offset=0,
    )

    assert total == 1
    assert [document.id for document in documents] == [first_document.id]
    assert repository.get_by_id(first_document.id, owner_id="owner-b") is None


def test_document_repository_deletes_document(
    repository: DocumentRepository,
) -> None:
    document = Document(
        filename="lecture.pdf",
        page_count=1,
        character_count=22,
        extracted_text="Temporary lecture text",
    )
    document.chunks = [
        DocumentChunk(
            position=0,
            text="Temporary lecture text",
            character_count=22,
        ),
    ]
    saved_document = repository.add(document)

    repository.delete(saved_document)

    assert (
        repository.get_by_id(saved_document.id, owner_id=DEFAULT_OWNER_ID)
        is None
    )
    assert (
        repository.list_chunks(saved_document.id, owner_id=DEFAULT_OWNER_ID)
        == []
    )
