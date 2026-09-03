import logging
from dataclasses import dataclass
from pathlib import Path

from studygraph.document_model import Document
from studygraph.document_service import (
    DocumentProcessingLimitError,
    DocumentReadError,
    DocumentService,
    DocumentStorageError,
)
from studygraph.pdf_text_extractor import PdfTextExtractionError, extract_pdf_document

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DocumentProcessingLimits:
    max_pages: int
    max_characters: int


class DocumentProcessingFailed(Exception):
    """Raised when a pending document was processed but could not succeed."""

    def __init__(self, document_id: int, message: str) -> None:
        super().__init__(message)
        self.document_id = document_id
        self.message = message


class DocumentProcessingStateError(Exception):
    """Raised when document processing state cannot be persisted."""


def process_pending_document(
    document_service: DocumentService,
    *,
    document_id: int,
    pdf_path: Path,
    limits: DocumentProcessingLimits,
) -> Document:
    logger.info("document_processing_started document_id=%s", document_id)

    try:
        claimed_document = document_service.claim_document_for_processing(document_id)
        if claimed_document is None:
            existing_document = document_service.get_document(document_id)
            if existing_document.status == "processing":
                logger.info(
                    "document_processing_already_claimed document_id=%s",
                    document_id,
                )
                return existing_document
        else:
            logger.info("document_processing_claimed document_id=%s", document_id)

        extracted_document = extract_pdf_document(pdf_path)
        document = document_service.process_document(
            document_id,
            extracted_document=extracted_document,
            max_pages=limits.max_pages,
            max_characters=limits.max_characters,
        )
        logger.info(
            "document_processing_completed document_id=%s page_count=%s "
            "character_count=%s",
            document.id,
            document.page_count,
            document.character_count,
        )
        return document
    except (PdfTextExtractionError, DocumentProcessingLimitError) as error:
        _mark_document_failed(
            document_service,
            document_id=document_id,
            error_message=str(error),
        )
        logger.warning(
            "document_processing_failed document_id=%s reason=%s",
            document_id,
            type(error).__name__,
        )
        raise DocumentProcessingFailed(document_id, str(error)) from error
    except (DocumentReadError, DocumentStorageError) as error:
        raise DocumentProcessingStateError(
            "Could not persist document processing state."
        ) from error


def _mark_document_failed(
    document_service: DocumentService,
    *,
    document_id: int,
    error_message: str,
) -> None:
    try:
        document_service.mark_document_failed(
            document_id,
            error_message=error_message,
        )
    except (DocumentReadError, DocumentStorageError) as error:
        raise DocumentProcessingStateError(
            "Could not persist document failure state."
        ) from error
