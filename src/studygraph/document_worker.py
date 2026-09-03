import logging
from pathlib import Path

from studygraph.config import (
    get_max_document_characters,
    get_max_document_pages,
    get_max_processing_attempts,
)
from studygraph.database import get_session_factory
from studygraph.document_model import Document
from studygraph.document_processing import (
    DocumentProcessingFailed,
    DocumentProcessingLimits,
    DocumentProcessingStateError,
    process_pending_document,
)
from studygraph.document_repository import DocumentRepository
from studygraph.document_service import DocumentService

logger = logging.getLogger(__name__)


def has_reached_retry_limit(document: Document, *, max_attempts: int) -> bool:
    return document.processing_attempts >= max_attempts


def process_document_job(document_id: int, pdf_path: Path) -> None:
    with get_session_factory() as session:
        repository = DocumentRepository(session)
        document = repository.get_for_processing(document_id)

        if document is None:
            logger.info("document_processing_skipped document_id=%s", document_id)
            return

        max_attempts = get_max_processing_attempts()
        if has_reached_retry_limit(document, max_attempts=max_attempts):
            logger.warning(
                "document_processing_retry_limit_reached document_id=%s attempts=%s",
                document_id,
                document.processing_attempts,
            )
            return

        service = DocumentService(repository, owner_id=document.owner_id)

        try:
            process_pending_document(
                service,
                document_id=document_id,
                pdf_path=pdf_path,
                limits=DocumentProcessingLimits(
                    max_pages=get_max_document_pages(),
                    max_characters=get_max_document_characters(),
                ),
            )
        except DocumentProcessingFailed:
            logger.info(
                "document_processing_failed_in_worker document_id=%s",
                document_id,
            )
        except DocumentProcessingStateError:
            logger.exception(
                "document_processing_state_error_in_worker document_id=%s",
                document_id,
            )
