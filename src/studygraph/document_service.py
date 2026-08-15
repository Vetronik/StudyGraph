from typing import Protocol

from studygraph.document_model import Document
from studygraph.document_repository import DocumentRepositoryError
from studygraph.pdf_text_extractor import ExtractedPdfDocument


class DocumentNotFoundError(Exception):
    """Raised when a document does not exist."""


class DocumentStorageError(Exception):
    """Raised when a document cannot be stored."""


class DocumentRepositoryProtocol(Protocol):
    def add(self, document: Document) -> Document: ...

    def get_by_id(self, document_id: int) -> Document | None: ...


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
