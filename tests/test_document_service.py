import pytest

from studygraph.document_model import Document, DocumentChunk
from studygraph.document_repository import DocumentRepositoryError
from studygraph.document_service import (
    DEFAULT_OWNER_ID,
    DocumentDeletionError,
    DocumentReadError,
    DocumentService,
)
from studygraph.pdf_text_extractor import ExtractedPdfDocument, ExtractedPdfPage


class RecordingDocumentRepository:
    def add(self, document: Document) -> Document:
        document.id = 1
        return document


class FailingDocumentRepository:
    def add(self, document: Document) -> Document:
        return document

    def update(self, document: Document) -> Document:
        return document

    def delete(self, document: Document) -> None:
        pass

    def get_by_id(self, document_id: int, *, owner_id: str) -> Document | None:
        raise DocumentRepositoryError("Database read failed.")

    def list_chunks(self, document_id: int, *, owner_id: str) -> list[DocumentChunk]:
        return []

    def list_documents(
        self,
        *,
        owner_id: str,
        limit: int,
        offset: int,
        query: str | None = None,
    ) -> tuple[list[Document], int]:
        return [], 0

    def search_chunks(
        self,
        *,
        owner_id: str,
        query: str,
        limit: int,
        offset: int,
    ) -> tuple[list[DocumentChunk], int]:
        return [], 0


def test_get_document_wraps_repository_read_errors() -> None:
    service = DocumentService(
        FailingDocumentRepository(),
        owner_id=DEFAULT_OWNER_ID,
    )

    with pytest.raises(DocumentReadError, match="Could not load document"):
        service.get_document(1)


def test_list_document_chunks_wraps_document_lookup_errors() -> None:
    service = DocumentService(
        FailingDocumentRepository(),
        owner_id=DEFAULT_OWNER_ID,
    )

    with pytest.raises(DocumentReadError, match="Could not load document"):
        service.list_document_chunks(1)


def test_delete_document_wraps_document_lookup_errors() -> None:
    service = DocumentService(
        FailingDocumentRepository(),
        owner_id=DEFAULT_OWNER_ID,
    )

    with pytest.raises(DocumentDeletionError, match="Could not delete document"):
        service.delete_document(1)


def test_create_document_preserves_chunk_page_numbers() -> None:
    service = DocumentService(RecordingDocumentRepository())

    document = service.create_document(
        filename="lecture.pdf",
        extracted_document=ExtractedPdfDocument(
            text="First page text\n\nSecond page text",
            page_count=2,
            pages=(
                ExtractedPdfPage(page_number=1, text="First page text"),
                ExtractedPdfPage(page_number=2, text="Second page text"),
            ),
        ),
    )

    assert [chunk.position for chunk in document.chunks] == [0, 1]
    assert [chunk.page_number for chunk in document.chunks] == [1, 2]
    assert [chunk.text for chunk in document.chunks] == [
        "First page text",
        "Second page text",
    ]
