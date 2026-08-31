from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from studygraph.api import app, get_document_service
from studygraph.config import (
    DATABASE_URL_ENV_VAR,
    MAX_DOCUMENT_CHARACTERS_ENV_VAR,
    MAX_UPLOAD_BYTES_ENV_VAR,
)
from studygraph.document_model import Document, DocumentChunk
from studygraph.document_service import DocumentService


class InMemoryDocumentRepository:
    def __init__(self) -> None:
        self._documents: dict[int, Document] = {}
        self._next_id = 1
        self._next_chunk_id = 1

    def _assign_chunk_metadata(self, document: Document) -> None:
        for chunk in document.chunks:
            if chunk.id is None:
                chunk.id = self._next_chunk_id
                self._next_chunk_id += 1

            if chunk.document_id is None:
                chunk.document_id = document.id

            chunk.document = document

            if chunk.created_at is None:
                chunk.created_at = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)

    def add(self, document: Document) -> Document:
        document.id = self._next_id
        document.created_at = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
        self._assign_chunk_metadata(document)
        self._documents[document.id] = document
        self._next_id += 1
        return document

    def update(self, document: Document) -> Document:
        self._assign_chunk_metadata(document)
        return document

    def delete(self, document: Document) -> None:
        del self._documents[document.id]

    def get_by_id(self, document_id: int) -> Document | None:
        return self._documents.get(document_id)

    def list_chunks(self, document_id: int) -> list[DocumentChunk]:
        document = self._documents.get(document_id)

        if document is None:
            return []

        return sorted(document.chunks, key=lambda chunk: chunk.position)

    def list_documents(
        self,
        *,
        limit: int,
        offset: int,
        query: str | None = None,
    ) -> tuple[list[Document], int]:
        documents = sorted(
            self._documents.values(),
            key=lambda document: document.id,
            reverse=True,
        )

        if query:
            normalized_query = query.lower()
            documents = [
                document
                for document in documents
                if (
                    normalized_query in document.filename.lower()
                    or normalized_query in document.extracted_text.lower()
                )
            ]

        return documents[offset : offset + limit], len(documents)

    def search_chunks(
        self,
        *,
        query: str,
        limit: int,
        offset: int,
    ) -> tuple[list[DocumentChunk], int]:
        normalized_query = query.lower()
        chunks: list[DocumentChunk] = []

        documents = sorted(
            self._documents.values(),
            key=lambda document: document.id,
            reverse=True,
        )

        for document in documents:
            for chunk in sorted(document.chunks, key=lambda item: item.position):
                if (
                    normalized_query in document.filename.lower()
                    or normalized_query in chunk.text.lower()
                ):
                    chunks.append(chunk)

        return chunks[offset : offset + limit], len(chunks)

    def count(self) -> int:
        return len(self._documents)


@pytest.fixture
def document_repository() -> InMemoryDocumentRepository:
    return InMemoryDocumentRepository()


@pytest.fixture
def client(document_repository: InMemoryDocumentRepository) -> TestClient:
    def override_document_service() -> DocumentService:
        return DocumentService(document_repository)

    app.dependency_overrides[get_document_service] = override_document_service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_health_check_returns_api_status(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(DATABASE_URL_ENV_VAR, raising=False)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database_configured": False,
    }


def test_health_check_reports_configured_database(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        DATABASE_URL_ENV_VAR,
        "postgresql+psycopg://user:password@localhost:5432/studygraph",
    )

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database_configured": True,
    }


def test_create_document_returns_503_when_database_url_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_pdf_with_text: Callable[[Path, str], None],
) -> None:
    monkeypatch.delenv(DATABASE_URL_ENV_VAR, raising=False)
    app.dependency_overrides.clear()
    pdf_path = tmp_path / "lecture.pdf"
    write_pdf_with_text(pdf_path, "StudyGraph extracts text through the API")

    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.post(
            "/documents",
            files={
                "file": (
                    "lecture.pdf",
                    pdf_path.read_bytes(),
                    "application/pdf",
                )
            },
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Application configuration error.",
        "message": "DATABASE_URL environment variable is not set.",
    }


def test_create_document_stores_valid_pdf(
    client: TestClient,
    document_repository: InMemoryDocumentRepository,
    tmp_path: Path,
    write_pdf_with_text: Callable[[Path, str], None],
) -> None:
    pdf_path = tmp_path / "lecture.pdf"
    write_pdf_with_text(pdf_path, "StudyGraph extracts text through the API")

    response = client.post(
        "/documents",
        files={
            "file": (
                "lecture.pdf",
                pdf_path.read_bytes(),
                "application/pdf",
            )
        },
    )

    response_data = response.json()

    assert response.status_code == 200
    assert response_data == {
        "id": 1,
        "filename": "lecture.pdf",
        "file_size_bytes": pdf_path.stat().st_size,
        "page_count": 1,
        "character_count": 40,
        "status": "processed",
        "processing_error": None,
        "text_preview": "StudyGraph extracts text through the API",
        "created_at": "2026-08-15T12:00:00Z",
    }
    assert document_repository.count() == 1


def test_create_document_returns_generated_id(
    client: TestClient,
    tmp_path: Path,
    write_pdf_with_text: Callable[[Path, str], None],
) -> None:
    pdf_path = tmp_path / "lecture.pdf"
    write_pdf_with_text(pdf_path, "StudyGraph extracts text through the API")

    response = client.post(
        "/documents",
        files={
            "file": (
                "lecture.pdf",
                pdf_path.read_bytes(),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 200
    assert isinstance(response.json()["id"], int)
    assert response.json()["id"] > 0


def test_get_document_returns_existing_document(
    client: TestClient,
    tmp_path: Path,
    write_pdf_with_text: Callable[[Path, str], None],
) -> None:
    pdf_path = tmp_path / "lecture.pdf"
    write_pdf_with_text(pdf_path, "StudyGraph extracts text through the API")

    create_response = client.post(
        "/documents",
        files={
            "file": (
                "lecture.pdf",
                pdf_path.read_bytes(),
                "application/pdf",
            )
        },
    )
    document_id = create_response.json()["id"]

    response = client.get(f"/documents/{document_id}")

    assert response.status_code == 200
    assert response.json() == create_response.json()


def test_get_document_returns_404_for_unknown_id(client: TestClient) -> None:
    response = client.get("/documents/999")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Document with id 999 was not found."
    }


def test_list_document_chunks_returns_chunks_for_existing_document(
    client: TestClient,
    tmp_path: Path,
    write_pdf_with_text: Callable[[Path, str], None],
) -> None:
    text = "StudyGraph creates chunks for retrieval"
    pdf_path = tmp_path / "lecture.pdf"
    write_pdf_with_text(pdf_path, text)
    create_response = client.post(
        "/documents",
        files={
            "file": (
                "lecture.pdf",
                pdf_path.read_bytes(),
                "application/pdf",
            )
        },
    )
    document_id = create_response.json()["id"]

    response = client.get(f"/documents/{document_id}/chunks")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": 1,
                "document_id": document_id,
                "position": 0,
                "text": text,
                "character_count": len(text),
                "created_at": "2026-08-15T12:00:00Z",
            }
        ]
    }


def test_list_document_chunks_returns_404_for_unknown_id(
    client: TestClient,
) -> None:
    response = client.get("/documents/999/chunks")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Document with id 999 was not found."
    }


def test_delete_document_removes_existing_document(
    client: TestClient,
    document_repository: InMemoryDocumentRepository,
    tmp_path: Path,
    write_pdf_with_text: Callable[[Path, str], None],
) -> None:
    pdf_path = tmp_path / "lecture.pdf"
    write_pdf_with_text(pdf_path, "StudyGraph deletes documents")
    create_response = client.post(
        "/documents",
        files={
            "file": (
                "lecture.pdf",
                pdf_path.read_bytes(),
                "application/pdf",
            )
        },
    )
    document_id = create_response.json()["id"]

    delete_response = client.delete(f"/documents/{document_id}")
    get_response = client.get(f"/documents/{document_id}")

    assert delete_response.status_code == 204
    assert delete_response.content == b""
    assert get_response.status_code == 404
    assert document_repository.count() == 0


def test_delete_document_returns_404_for_unknown_id(
    client: TestClient,
) -> None:
    response = client.delete("/documents/999")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Document with id 999 was not found."
    }


def test_list_documents_returns_stored_documents(
    client: TestClient,
    tmp_path: Path,
    write_pdf_with_text: Callable[[Path, str], None],
) -> None:
    first_pdf_path = tmp_path / "lecture-one.pdf"
    second_pdf_path = tmp_path / "lecture-two.pdf"
    write_pdf_with_text(first_pdf_path, "First lecture notes")
    write_pdf_with_text(second_pdf_path, "Second lecture notes")

    client.post(
        "/documents",
        files={
            "file": (
                "lecture-one.pdf",
                first_pdf_path.read_bytes(),
                "application/pdf",
            )
        },
    )
    client.post(
        "/documents",
        files={
            "file": (
                "lecture-two.pdf",
                second_pdf_path.read_bytes(),
                "application/pdf",
            )
        },
    )

    response = client.get("/documents")

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert response.json()["limit"] == 20
    assert response.json()["offset"] == 0
    assert [
        item["filename"] for item in response.json()["items"]
    ] == [
        "lecture-two.pdf",
        "lecture-one.pdf",
    ]


def test_list_documents_supports_pagination(
    client: TestClient,
    tmp_path: Path,
    write_pdf_with_text: Callable[[Path, str], None],
) -> None:
    for filename in ["first.pdf", "second.pdf", "third.pdf"]:
        pdf_path = tmp_path / filename
        write_pdf_with_text(pdf_path, f"Notes from {filename}")
        client.post(
            "/documents",
            files={
                "file": (
                    filename,
                    pdf_path.read_bytes(),
                    "application/pdf",
                )
            },
        )

    response = client.get("/documents?limit=1&offset=1")

    assert response.status_code == 200
    assert response.json()["total"] == 3
    assert response.json()["limit"] == 1
    assert response.json()["offset"] == 1
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["filename"] == "second.pdf"


def test_list_documents_supports_search_query(
    client: TestClient,
    tmp_path: Path,
    write_pdf_with_text: Callable[[Path, str], None],
) -> None:
    calculus_pdf_path = tmp_path / "calculus.pdf"
    history_pdf_path = tmp_path / "history.pdf"
    write_pdf_with_text(calculus_pdf_path, "Chain rule and derivatives")
    write_pdf_with_text(history_pdf_path, "Roman empire overview")

    client.post(
        "/documents",
        files={
            "file": (
                "calculus.pdf",
                calculus_pdf_path.read_bytes(),
                "application/pdf",
            )
        },
    )
    client.post(
        "/documents",
        files={
            "file": (
                "history.pdf",
                history_pdf_path.read_bytes(),
                "application/pdf",
            )
        },
    )

    response = client.get("/documents?query=derivatives")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert [
        item["filename"] for item in response.json()["items"]
    ] == ["calculus.pdf"]


def test_list_documents_rejects_invalid_limit(client: TestClient) -> None:
    response = client.get("/documents?limit=0")

    assert response.status_code == 422


def test_search_document_chunks_returns_matching_chunks(
    client: TestClient,
    tmp_path: Path,
    write_pdf_with_text: Callable[[Path, str], None],
) -> None:
    calculus_pdf_path = tmp_path / "calculus.pdf"
    history_pdf_path = tmp_path / "history.pdf"
    write_pdf_with_text(calculus_pdf_path, "Chain rule and derivatives")
    write_pdf_with_text(history_pdf_path, "Roman empire overview")

    client.post(
        "/documents",
        files={
            "file": (
                "calculus.pdf",
                calculus_pdf_path.read_bytes(),
                "application/pdf",
            )
        },
    )
    client.post(
        "/documents",
        files={
            "file": (
                "history.pdf",
                history_pdf_path.read_bytes(),
                "application/pdf",
            )
        },
    )

    response = client.get("/search?query=derivatives")

    assert response.status_code == 200
    response_data = response.json()
    assert response_data["total"] == 1
    assert response_data["limit"] == 20
    assert response_data["offset"] == 0
    assert response_data["query"] == "derivatives"
    assert response_data["items"][0]["document_filename"] == "calculus.pdf"
    assert response_data["items"][0]["chunk_position"] == 0
    assert response_data["items"][0]["text"] == "Chain rule and derivatives"
    assert response_data["items"][0]["snippet"] == "Chain rule and derivatives"


def test_search_document_chunks_supports_pagination(
    client: TestClient,
    tmp_path: Path,
    write_pdf_with_text: Callable[[Path, str], None],
) -> None:
    for filename in ["first.pdf", "second.pdf", "third.pdf"]:
        pdf_path = tmp_path / filename
        write_pdf_with_text(pdf_path, f"Shared query text from {filename}")
        client.post(
            "/documents",
            files={
                "file": (
                    filename,
                    pdf_path.read_bytes(),
                    "application/pdf",
                )
            },
        )

    response = client.get("/search?query=shared&limit=1&offset=1")

    assert response.status_code == 200
    response_data = response.json()
    assert response_data["total"] == 3
    assert response_data["limit"] == 1
    assert response_data["offset"] == 1
    assert len(response_data["items"]) == 1
    assert response_data["items"][0]["document_filename"] == "second.pdf"


def test_search_document_chunks_rejects_blank_query(
    client: TestClient,
) -> None:
    response = client.get("/search?query=%20%20")

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Search query must contain non-whitespace text."
    }


def test_create_document_rejects_non_pdf_file(
    client: TestClient,
    document_repository: InMemoryDocumentRepository,
) -> None:
    response = client.post(
        "/documents",
        files={"file": ("notes.txt", b"This is not a PDF.", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Uploaded file must have a .pdf extension."
    }
    assert document_repository.count() == 0


def test_create_document_rejects_file_without_pdf_header(
    client: TestClient,
    document_repository: InMemoryDocumentRepository,
) -> None:
    response = client.post(
        "/documents",
        files={
            "file": (
                "notes.pdf",
                b"This file has a PDF extension but no PDF header.",
                "application/pdf",
            )
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Uploaded file content is not a PDF."
    }
    assert document_repository.count() == 0


def test_create_document_rejects_upload_larger_than_configured_limit(
    client: TestClient,
    document_repository: InMemoryDocumentRepository,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_pdf_with_text: Callable[[Path, str], None],
) -> None:
    monkeypatch.setenv(MAX_UPLOAD_BYTES_ENV_VAR, "10")
    pdf_path = tmp_path / "lecture.pdf"
    write_pdf_with_text(pdf_path, "StudyGraph extracts text through the API")

    response = client.post(
        "/documents",
        files={
            "file": (
                "lecture.pdf",
                pdf_path.read_bytes(),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 413
    assert response.json() == {
        "detail": "Uploaded file is too large. Maximum size is 10 bytes."
    }
    assert document_repository.count() == 0


def test_create_document_rejects_invalid_pdf(
    client: TestClient,
    document_repository: InMemoryDocumentRepository,
) -> None:
    response = client.post(
        "/documents",
        files={
            "file": (
                "broken.pdf",
                b"%PDF-1.4\nThis is not a valid PDF structure.",
                "application/pdf",
            )
        },
    )

    assert response.status_code == 422
    response_detail = response.json()["detail"]
    assert response_detail["document_id"] == 1
    assert response_detail["message"].startswith(
        "Could not process PDF: Could not read PDF:"
    )
    failed_document = document_repository.get_by_id(response_detail["document_id"])
    assert failed_document is not None
    assert failed_document.status == "failed"
    assert failed_document.processing_error is not None
    assert failed_document.processing_error.startswith("Could not read PDF:")
    assert document_repository.count() == 1


def test_create_document_rejects_pdf_without_extractable_text(
    client: TestClient,
    document_repository: InMemoryDocumentRepository,
    tmp_path: Path,
    write_pdf_without_text: Callable[[Path], None],
) -> None:
    pdf_path = tmp_path / "scanned.pdf"
    write_pdf_without_text(pdf_path)

    response = client.post(
        "/documents",
        files={
            "file": (
                "scanned.pdf",
                pdf_path.read_bytes(),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "message": (
            "Could not process PDF: No text could be extracted. "
            "The PDF may contain scanned images only."
        ),
        "document_id": 1,
    }
    failed_document = document_repository.get_by_id(1)
    assert failed_document is not None
    assert failed_document.status == "failed"
    assert failed_document.processing_error == (
        "No text could be extracted. The PDF may contain scanned images only."
    )
    assert document_repository.count() == 1


def test_create_document_marks_document_failed_when_text_limit_is_exceeded(
    client: TestClient,
    document_repository: InMemoryDocumentRepository,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_pdf_with_text: Callable[[Path, str], None],
) -> None:
    monkeypatch.setenv(MAX_DOCUMENT_CHARACTERS_ENV_VAR, "10")
    pdf_path = tmp_path / "lecture.pdf"
    write_pdf_with_text(pdf_path, "StudyGraph extracts text through the API")

    response = client.post(
        "/documents",
        files={
            "file": (
                "lecture.pdf",
                pdf_path.read_bytes(),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "message": (
            "Could not process PDF: Document exceeds maximum character count "
            "(40 > 10)."
        ),
        "document_id": 1,
    }
    failed_document = document_repository.get_by_id(1)
    assert failed_document is not None
    assert failed_document.status == "failed"
    assert failed_document.processing_error == (
        "Document exceeds maximum character count (40 > 10)."
    )
