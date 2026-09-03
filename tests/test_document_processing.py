import logging
from collections.abc import Callable
from pathlib import Path

import pytest

from studygraph.document_model import Document
from studygraph.document_processing import (
    DocumentProcessingFailed,
    DocumentProcessingLimits,
    process_pending_document,
)
from studygraph.document_worker import has_reached_retry_limit


class RecordingDocumentService:
    def __init__(self) -> None:
        self.failed_document_id: int | None = None
        self.failure_message: str | None = None
        self.processed_document_id: int | None = None
        self.claimed_document_id: int | None = None
        self.already_claimed = False

    def process_document(
        self,
        document_id: int,
        *,
        extracted_document,
        max_pages: int,
        max_characters: int,
    ) -> Document:
        self.processed_document_id = document_id
        return Document(
            id=document_id,
            filename="lecture.pdf",
            owner_id="local-user",
            file_size_bytes=100,
            page_count=extracted_document.page_count,
            character_count=len(extracted_document.text),
            extracted_text=extracted_document.text,
            status="processed",
            processing_error=None,
        )

    def claim_document_for_processing(
        self,
        document_id: int,
    ) -> Document | None:
        if self.already_claimed:
            return None
        self.claimed_document_id = document_id
        return Document(
            id=document_id,
            filename="lecture.pdf",
            owner_id="local-user",
            file_size_bytes=100,
            page_count=0,
            character_count=0,
            extracted_text="",
            status="processing",
            processing_error=None,
            processing_attempts=1,
        )

    def get_document(self, document_id: int) -> Document:
        return Document(
            id=document_id,
            filename="lecture.pdf",
            owner_id="local-user",
            file_size_bytes=100,
            page_count=0,
            character_count=0,
            extracted_text="",
            status="processing",
            processing_error=None,
            processing_attempts=1,
        )

    def mark_document_failed(
        self,
        document_id: int,
        *,
        error_message: str,
    ) -> Document:
        self.failed_document_id = document_id
        self.failure_message = error_message
        return Document(
            id=document_id,
            filename="lecture.pdf",
            owner_id="local-user",
            file_size_bytes=100,
            page_count=0,
            character_count=0,
            extracted_text="",
            status="failed",
            processing_error=error_message,
        )


def test_process_pending_document_processes_valid_pdf(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
    write_pdf_with_text: Callable[[Path, str], None],
) -> None:
    service = RecordingDocumentService()
    pdf_path = tmp_path / "lecture.pdf"
    write_pdf_with_text(pdf_path, "StudyGraph extracts text")
    caplog.set_level(logging.INFO, logger="studygraph.document_processing")

    document = process_pending_document(
        service,
        document_id=7,
        pdf_path=pdf_path,
        limits=DocumentProcessingLimits(
            max_pages=10,
            max_characters=1000,
        ),
    )

    assert document.id == 7
    assert document.status == "processed"
    assert service.processed_document_id == 7
    assert service.claimed_document_id == 7
    assert service.failed_document_id is None
    assert "document_processing_started document_id=7" in caplog.text
    assert "document_processing_completed document_id=7" in caplog.text


def test_process_pending_document_skips_already_claimed_document(
    tmp_path: Path,
) -> None:
    service = RecordingDocumentService()
    service.already_claimed = True
    pdf_path = tmp_path / "lecture.pdf"

    document = process_pending_document(
        service,
        document_id=7,
        pdf_path=pdf_path,
        limits=DocumentProcessingLimits(
            max_pages=10,
            max_characters=1000,
        ),
    )

    assert document.status == "processing"
    assert service.processed_document_id is None


def test_process_pending_document_marks_failed_pdf(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    service = RecordingDocumentService()
    pdf_path = tmp_path / "broken.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nThis is not a valid PDF structure.")
    caplog.set_level(logging.WARNING, logger="studygraph.document_processing")

    with pytest.raises(DocumentProcessingFailed) as error:
        process_pending_document(
            service,
            document_id=8,
            pdf_path=pdf_path,
            limits=DocumentProcessingLimits(
                max_pages=10,
                max_characters=1000,
            ),
        )

    assert error.value.document_id == 8
    assert service.failed_document_id == 8
    assert service.failure_message is not None
    assert service.failure_message.startswith("Could not read PDF:")
    assert "document_processing_failed document_id=8" in caplog.text


def test_worker_retry_limit_is_reached_at_configured_attempt_count() -> None:
    document = Document(
        id=9,
        filename="lecture.pdf",
        owner_id="local-user",
        file_size_bytes=100,
        page_count=0,
        character_count=0,
        extracted_text="",
        status="failed",
        processing_error="broken",
        processing_attempts=3,
    )

    assert has_reached_retry_limit(document, max_attempts=3)
    assert not has_reached_retry_limit(document, max_attempts=4)
