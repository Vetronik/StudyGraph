from dataclasses import dataclass
from typing import Protocol

from studygraph.document_model import Document, DocumentChunk
from studygraph.document_repository import (
    DocumentDuplicateError,
    DocumentRepositoryError,
)
from studygraph.embedding_service import DeterministicHashEmbeddingProvider
from studygraph.pdf_text_extractor import ExtractedPdfDocument, ExtractedPdfPage
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


class DocumentSearchQueryError(Exception):
    """Raised when a search query is empty after normalization."""


DOCUMENT_STATUS_FAILED = "failed"
DOCUMENT_STATUS_PENDING = "pending"
DOCUMENT_STATUS_PROCESSING = "processing"
DOCUMENT_STATUS_PROCESSED = "processed"
DEFAULT_OWNER_ID = "local-user"


@dataclass(frozen=True)
class DocumentList:
    documents: list[Document]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class DocumentChunkList:
    chunks: list[DocumentChunk]


@dataclass(frozen=True)
class DocumentSearchResultList:
    chunks: list[DocumentChunk]
    total: int
    limit: int
    offset: int
    query: str


@dataclass(frozen=True)
class SemanticSearchResultList:
    chunks: list[DocumentChunk]
    total: int
    limit: int
    offset: int
    query: str


class DocumentRepositoryProtocol(Protocol):
    def add(self, document: Document) -> Document: ...

    def update(self, document: Document) -> Document: ...

    def delete(self, document: Document) -> None: ...

    def claim_for_processing(
        self,
        document_id: int,
        *,
        owner_id: str,
    ) -> Document | None: ...

    def get_by_id(self, document_id: int, *, owner_id: str) -> Document | None: ...

    def list_chunks(
        self,
        document_id: int,
        *,
        owner_id: str,
    ) -> list[DocumentChunk]: ...

    def list_documents(
        self,
        *,
        owner_id: str,
        limit: int,
        offset: int,
        query: str | None = None,
    ) -> tuple[list[Document], int]: ...

    def search_chunks(
        self,
        *,
        owner_id: str,
        query: str,
        limit: int,
        offset: int,
    ) -> tuple[list[DocumentChunk], int]: ...

    def semantic_search_chunks(
        self,
        *,
        owner_id: str,
        query: str,
        limit: int,
        offset: int,
    ) -> tuple[list[DocumentChunk], int]: ...


def _iter_extractable_pages(
    extracted_document: ExtractedPdfDocument,
) -> tuple[ExtractedPdfPage, ...]:
    if extracted_document.pages:
        return extracted_document.pages

    return (
        ExtractedPdfPage(
            page_number=1,
            text=extracted_document.text,
        ),
    )


def _build_document_chunks(
    extracted_document: ExtractedPdfDocument,
) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    embedding_provider = DeterministicHashEmbeddingProvider()

    for page in _iter_extractable_pages(extracted_document):
        page_chunks = chunk_text(page.text)
        embeddings = embedding_provider.embed_texts(
            [chunk.text for chunk in page_chunks]
        )
        for chunk, embedding in zip(page_chunks, embeddings, strict=True):
            chunks.append(
                DocumentChunk(
                    position=len(chunks),
                    page_number=page.page_number,
                    text=chunk.text,
                    character_count=chunk.character_count,
                    embedding=list(embedding.vector),
                )
            )

    return chunks


class DocumentService:
    def __init__(
        self,
        repository: DocumentRepositoryProtocol,
        *,
        owner_id: str = DEFAULT_OWNER_ID,
    ) -> None:
        self._repository = repository
        self._owner_id = owner_id

    def create_pending_document(
        self,
        *,
        filename: str,
        file_size_bytes: int,
        content_hash: str,
        source_path: str | None = None,
    ) -> Document:
        document = Document(
            filename=filename,
            owner_id=self._owner_id,
            content_hash=content_hash,
            file_size_bytes=file_size_bytes,
            page_count=0,
            character_count=0,
            extracted_text="",
            status=DOCUMENT_STATUS_PENDING,
            processing_error=None,
            source_path=source_path,
        )

        try:
            return self._repository.add(document)
        except DocumentRepositoryError as error:
            if isinstance(error, DocumentDuplicateError):
                raise error
            raise DocumentStorageError("Could not create document.") from error

    def create_document(
        self,
        *,
        filename: str,
        extracted_document: ExtractedPdfDocument,
        source_path: str | None = None,
    ) -> Document:
        document = Document(
            filename=filename,
            owner_id=self._owner_id,
            file_size_bytes=0,
            page_count=extracted_document.page_count,
            character_count=len(extracted_document.text),
            extracted_text=extracted_document.text,
            status=DOCUMENT_STATUS_PROCESSED,
            processing_error=None,
            source_path=source_path,
        )
        document.chunks = _build_document_chunks(extracted_document)

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
        document.chunks = _build_document_chunks(extracted_document)

        try:
            return self._repository.update(document)
        except DocumentRepositoryError as error:
            raise DocumentStorageError("Could not save document.") from error

    def claim_document_for_processing(self, document_id: int) -> Document | None:
        try:
            return self._repository.claim_for_processing(
                document_id,
                owner_id=self._owner_id,
            )
        except DocumentRepositoryError as error:
            raise DocumentStorageError(
                "Could not claim document for processing."
            ) from error

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

    def retry_document(self, document_id: int) -> Document:
        document = self.get_document(document_id)
        document.status = DOCUMENT_STATUS_PENDING
        document.processing_error = None
        document.processing_attempts = 0
        document.chunks = []

        try:
            return self._repository.update(document)
        except DocumentRepositoryError as error:
            raise DocumentStorageError(
                "Could not retry document processing."
            ) from error

    def get_document(self, document_id: int) -> Document:
        try:
            document = self._repository.get_by_id(
                document_id,
                owner_id=self._owner_id,
            )
        except DocumentRepositoryError as error:
            raise DocumentReadError("Could not load document.") from error

        if document is None:
            raise DocumentNotFoundError(
                f"Document with id {document_id} was not found."
            )

        return document

    def list_document_chunks(self, document_id: int) -> DocumentChunkList:
        try:
            document = self._repository.get_by_id(
                document_id,
                owner_id=self._owner_id,
            )
        except DocumentRepositoryError as error:
            raise DocumentReadError("Could not load document.") from error

        if document is None:
            raise DocumentNotFoundError(
                f"Document with id {document_id} was not found."
            )

        try:
            chunks = self._repository.list_chunks(
                document_id,
                owner_id=self._owner_id,
            )
        except DocumentRepositoryError as error:
            raise DocumentReadError("Could not load document chunks.") from error

        return DocumentChunkList(chunks=chunks)

    def delete_document(self, document_id: int) -> None:
        try:
            document = self._repository.get_by_id(
                document_id,
                owner_id=self._owner_id,
            )
        except DocumentRepositoryError as error:
            raise DocumentDeletionError("Could not delete document.") from error

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
                owner_id=self._owner_id,
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

    def search_chunks(
        self,
        *,
        query: str,
        limit: int,
        offset: int,
    ) -> DocumentSearchResultList:
        normalized_query = query.strip()

        if not normalized_query:
            raise DocumentSearchQueryError(
                "Search query must contain non-whitespace text."
            )

        try:
            chunks, total = self._repository.search_chunks(
                owner_id=self._owner_id,
                query=normalized_query,
                limit=limit,
                offset=offset,
            )
        except DocumentRepositoryError as error:
            raise DocumentReadError("Could not search document chunks.") from error

        return DocumentSearchResultList(
            chunks=chunks,
            total=total,
            limit=limit,
            offset=offset,
            query=normalized_query,
        )

    def semantic_search_chunks(
        self,
        *,
        query: str,
        limit: int,
        offset: int,
    ) -> SemanticSearchResultList:
        normalized_query = query.strip()
        if not normalized_query:
            raise DocumentSearchQueryError(
                "Search query must contain non-whitespace text."
            )

        try:
            chunks, total = self._repository.semantic_search_chunks(
                owner_id=self._owner_id,
                query=normalized_query,
                limit=limit,
                offset=offset,
            )
        except DocumentRepositoryError as error:
            raise DocumentReadError("Could not search document embeddings.") from error

        return SemanticSearchResultList(
            chunks=chunks,
            total=total,
            limit=limit,
            offset=offset,
            query=normalized_query,
        )

    def hybrid_search_chunks(
        self,
        *,
        query: str,
        limit: int,
        offset: int,
    ) -> DocumentSearchResultList:
        candidate_limit = min(100, limit + offset + 20)
        full_text_results = self.search_chunks(
            query=query,
            limit=candidate_limit,
            offset=0,
        )
        semantic_results = self.semantic_search_chunks(
            query=query,
            limit=candidate_limit,
            offset=0,
        )

        scores: dict[int, float] = {}
        chunks: dict[int, DocumentChunk] = {}
        for rank, chunk in enumerate(full_text_results.chunks, start=1):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1 / (60 + rank)
            chunks[chunk.id] = chunk
        for rank, chunk in enumerate(semantic_results.chunks, start=1):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1 / (60 + rank)
            chunks[chunk.id] = chunk

        ranked_chunks = sorted(
            chunks.values(),
            key=lambda chunk: (-scores[chunk.id], chunk.id),
        )
        return DocumentSearchResultList(
            chunks=ranked_chunks[offset : offset + limit],
            total=len(ranked_chunks),
            limit=limit,
            offset=offset,
            query=full_text_results.query,
        )
