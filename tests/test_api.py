from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from studygraph.api import app, get_document_service
from studygraph.document_model import Document
from studygraph.document_service import DocumentService


class InMemoryDocumentRepository:
    def __init__(self) -> None:
        self._documents: dict[int, Document] = {}
        self._next_id = 1

    def add(self, document: Document) -> Document:
        document.id = self._next_id
        document.created_at = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
        self._documents[document.id] = document
        self._next_id += 1
        return document

    def get_by_id(self, document_id: int) -> Document | None:
        return self._documents.get(document_id)

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
        "page_count": 1,
        "character_count": 40,
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
    assert response.json()["detail"].startswith(
        "Could not process PDF: Could not read PDF:"
    )
    assert document_repository.count() == 0


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
    assert response.json() == {
        "detail": (
            "Could not process PDF: No text could be extracted. "
            "The PDF may contain scanned images only."
        )
    }
    assert document_repository.count() == 0
