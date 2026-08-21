from dataclasses import dataclass
from typing import Protocol

from studygraph.document_model import Document
from studygraph.document_repository import DocumentRepositoryError
from studygraph.pdf_text_extractor import ExtractedPdfDocument


class DocumentNotFoundError(Exception):
    """Raised when a document does not exist."""


class DocumentStorageError(Exception):
    """Raised when a document cannot be stored."""


class DocumentDeletionError(Exception):
    """Raised when a document cannot be deleted."""


@dataclass(frozen=True)
class DocumentList:
    documents: list[Document]
    total: int
    limit: int
    offset: int


class DocumentRepositoryProtocol(Protocol):
    def add(self, document: Document) -> Document: ...

    def delete(self, document: Document) -> None: ...

    def get_by_id(self, document_id: int) -> Document | None: ...

    def list_documents(
        self,
        *,
        limit: int,
        offset: int,
        query: str | None = None,
    ) -> tuple[list[Document], int]: ...


class DocumentService:
    def __init__(self, repository: DocumentRepositoryProtocol) -> None:
        self._repository = repository

    def create_document(
        self,
        *,
        filename: str,
        extracted_document: ExtractedPdfDocument,
    ) -> Document:
        document = Document(
            filename=filename,
            page_count=extracted_document.page_count,
            character_count=len(extracted_document.text),
            extracted_text=extracted_document.text,
        )

        try:
            return self._repository.add(document)
        except DocumentRepositoryError as error:
            raise DocumentStorageError("Could not save document.") from error

    def get_document(self, document_id: int) -> Document:
        document = self._repository.get_by_id(document_id)

        if document is None:
            raise DocumentNotFoundError(
                f"Document with id {document_id} was not found."
            )

        return document

    def delete_document(self, document_id: int) -> None:
        document = self._repository.get_by_id(document_id)

        if document is None:
            raise DocumentNotFoundError(
                f"Document with id {document_id} was not found."
            )

        try:
            self._repository.delete(document)
        except DocumentRepositoryError as error:
            raise DocumentDeletionError("Could not delete document.") from error

    def list_documents(
        self,
        *,
        limit: int,
        offset: int,
        query: str | None = None,
    ) -> DocumentList:
        normalized_query = query.strip() if query else None
        documents, total = self._repository.list_documents(
            limit=limit,
            offset=offset,
            query=normalized_query,
        )

        return DocumentList(
            documents=documents,
            total=total,
            limit=limit,
            offset=offset,
        )
