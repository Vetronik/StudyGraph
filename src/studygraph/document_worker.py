import logging
from pathlib import Path

from studygraph.config import get_max_document_characters, get_max_document_pages
from studygraph.database import get_session_factory
from studygraph.document_processing import (
    DocumentProcessingFailed,
    DocumentProcessingLimits,
    DocumentProcessingStateError,
    process_pending_document,
)
from studygraph.document_repository import DocumentRepository
from studygraph.document_service import DocumentService

logger = logging.getLogger(__name__)


def process_document_job(document_id: int, pdf_path: Path) -> None:
    with get_session_factory() as session:
        repository = DocumentRepository(session)
        document = repository.get_for_processing(document_id)

        if document is None:
            logger.info("document_processing_skipped document_id=%s", document_id)
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
