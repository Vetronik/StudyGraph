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


class DocumentProcessingLimitError(Exception):
    """Raised when extracted document content exceeds configured limits."""


DOCUMENT_STATUS_FAILED = "failed"
DOCUMENT_STATUS_PENDING = "pending"
DOCUMENT_STATUS_PROCESSED = "processed"


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

    def update(self, document: Document) -> Document: ...

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

    def create_pending_document(
        self,
        *,
        filename: str,
        file_size_bytes: int,
    ) -> Document:
        document = Document(
            filename=filename,
            file_size_bytes=file_size_bytes,
            page_count=0,
            character_count=0,
            extracted_text="",
            status=DOCUMENT_STATUS_PENDING,
            processing_error=None,
        )

        try:
            return self._repository.add(document)
        except DocumentRepositoryError as error:
            raise DocumentStorageError("Could not create document.") from error

    def create_document(
        self,
        *,
        filename: str,
        extracted_document: ExtractedPdfDocument,
    ) -> Document:
        document = Document(
            filename=filename,
            file_size_bytes=0,
            page_count=extracted_document.page_count,
            character_count=len(extracted_document.text),
            extracted_text=extracted_document.text,
            status=DOCUMENT_STATUS_PROCESSED,
            processing_error=None,
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

    def process_document(
        self,
        document_id: int,
        *,
        extracted_document: ExtractedPdfDocument,
        max_pages: int,
        max_characters: int,
    ) -> Document:
        document = self.get_document(document_id)

        if extracted_document.page_count > max_pages:
            raise DocumentProcessingLimitError(
                "Document exceeds maximum page count "
                f"({extracted_document.page_count} > {max_pages})."
            )

        character_count = len(extracted_document.text)

        if character_count > max_characters:
            raise DocumentProcessingLimitError(
                "Document exceeds maximum character count "
                f"({character_count} > {max_characters})."
            )

        document.page_count = extracted_document.page_count
        document.character_count = character_count
        document.extracted_text = extracted_document.text
        document.status = DOCUMENT_STATUS_PROCESSED
        document.processing_error = None
        document.chunks = [
            DocumentChunk(
                position=chunk.position,
                text=chunk.text,
                character_count=chunk.character_count,
            )
            for chunk in chunk_text(extracted_document.text)
        ]

        try:
            return self._repository.update(document)
        except DocumentRepositoryError as error:
            raise DocumentStorageError("Could not save document.") from error

    def mark_document_failed(
        self,
        document_id: int,
        *,
        error_message: str,
    ) -> Document:
        document = self.get_document(document_id)
        document.status = DOCUMENT_STATUS_FAILED
        document.processing_error = error_message
        document.chunks = []

        try:
            return self._repository.update(document)
        except DocumentRepositoryError as error:
            raise DocumentStorageError(
                "Could not save document failure state."
            ) from error

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
