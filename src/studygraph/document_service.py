from dataclasses import dataclass
from typing import Protocol

from studygraph.document_model import Document, DocumentChunk
from studygraph.document_repository import DocumentRepositoryError
from studygraph.pdf_text_extractor import ExtractedPdfDocument
from studygraph.text_chunker import chunk_text


class DocumentNotFoundError(Exception):
    """Raised when a document does not exist."""


class DocumentStorageError(Exception):
    """Raised when a document cannot be stored."""


class DocumentDeletionError(Exception):
    """Raised when a document cannot be deleted."""


class DocumentReadError(Exception):
    """Raised when documents cannot be loaded."""


@dataclass(frozen=True)
class DocumentList:
    documents: list[Document]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class DocumentChunkList:
    chunks: list[DocumentChunk]


class DocumentRepositoryProtocol(Protocol):
    def add(self, document: Document) -> Document: ...

    def delete(self, document: Document) -> None: ...

    def get_by_id(self, document_id: int) -> Document | None: ...

    def list_chunks(self, document_id: int) -> list[DocumentChunk]: ...

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
        document.chunks = [
            DocumentChunk(
                position=chunk.position,
                text=chunk.text,
                character_count=chunk.character_count,
            )
            for chunk in chunk_text(extracted_document.text)
        ]

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

    def list_document_chunks(self, document_id: int) -> DocumentChunkList:
        document = self._repository.get_by_id(document_id)

        if document is None:
            raise DocumentNotFoundError(
                f"Document with id {document_id} was not found."
            )

        try:
            chunks = self._repository.list_chunks(document_id)
        except DocumentRepositoryError as error:
            raise DocumentReadError("Could not load document chunks.") from error

        return DocumentChunkList(chunks=chunks)

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

        try:
            documents, total = self._repository.list_documents(
                limit=limit,
                offset=offset,
                query=normalized_query,
            )
        except DocumentRepositoryError as error:
            raise DocumentReadError("Could not load documents.") from error

        return DocumentList(
            documents=documents,
            total=total,
            limit=limit,
            offset=offset,
        )
