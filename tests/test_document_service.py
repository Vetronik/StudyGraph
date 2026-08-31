import pytest

from studygraph.document_model import Document, DocumentChunk
from studygraph.document_repository import DocumentRepositoryError
from studygraph.document_service import (
    DEFAULT_OWNER_ID,
    DocumentDeletionError,
    DocumentReadError,
    DocumentService,
)


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
