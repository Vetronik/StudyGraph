import logging
import signal
from pathlib import Path
from threading import Event

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
from studygraph.document_storage import (
    InvalidDocumentStoragePath,
    resolve_stored_document_path,
)

logger = logging.getLogger(__name__)
DEFAULT_POLL_INTERVAL_SECONDS = 2
DEFAULT_BATCH_SIZE = 10


def has_reached_retry_limit(document: Document, *, max_attempts: int) -> bool:
    return document.processing_attempts >= max_attempts


def process_document_job(document_id: int, pdf_path: Path) -> None:
    try:
        pdf_path = resolve_stored_document_path(str(pdf_path))
    except InvalidDocumentStoragePath:
        logger.error(
            "document_processing_path_invalid document_id=%s",
            document_id,
        )
        return

    with get_session_factory()() as session:
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


def run_worker(
    *,
    stop_event: Event | None = None,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    """Continuously process queued documents until a termination signal arrives."""
    stop_event = stop_event or Event()
    _install_signal_handlers(stop_event)

    with get_session_factory()() as session:
        repository = DocumentRepository(session)
        requeued_count = repository.requeue_processing_documents()
        if requeued_count:
            logger.warning(
                "document_processing_jobs_requeued count=%s", requeued_count
            )

    logger.info(
        "document_worker_started poll_interval_seconds=%s",
        poll_interval_seconds,
    )

    while not stop_event.is_set():
        processed_count = _process_pending_batch(batch_size=batch_size)
        if processed_count == 0:
            stop_event.wait(poll_interval_seconds)

    logger.info("document_worker_stopped")


def _process_pending_batch(*, batch_size: int) -> int:
    with get_session_factory()() as session:
        repository = DocumentRepository(session)
        pending_documents = [
            (document.id, document.source_path)
            for document in repository.list_pending(limit=batch_size)
            if document.source_path
        ]

    for document_id, source_path in pending_documents:
        try:
            pdf_path = resolve_stored_document_path(source_path)
        except InvalidDocumentStoragePath:
            logger.error(
                "document_processing_path_invalid document_id=%s",
                document_id,
            )
            continue
        if pdf_path.exists():
            process_document_job(document_id, pdf_path)
        else:
            logger.error(
                "document_processing_source_missing document_id=%s path=%s",
                document_id,
                pdf_path,
            )

    return len(pending_documents)


def _install_signal_handlers(stop_event: Event) -> None:
    def request_shutdown(signum: int, _frame: object) -> None:
        logger.info("document_worker_shutdown_requested signal=%s", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)


def main() -> int:
    run_worker()
    return 0
