import argparse
from pathlib import Path

from studygraph.config import (
    get_max_document_characters,
    get_max_document_pages,
)
from studygraph.database import get_session_factory
from studygraph.document_processing import (
    DocumentProcessingLimits,
    process_pending_document,
)
from studygraph.document_repository import DocumentRepository
from studygraph.document_service import DocumentService
from studygraph.pdf_text_extractor import PdfTextExtractionError, extract_text_from_pdf


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="studygraph",
        description="Extract text from a PDF file and print it to the terminal.",
    )
    parser.add_argument("pdf_path", nargs="?", help="Path to the PDF file")
    parser.add_argument(
        "--process-pending",
        action="store_true",
        help="Process pending documents from the configured storage directory",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.process_pending:
        return process_pending_documents()

    if not args.pdf_path:
        parser.error("pdf_path is required unless --process-pending is used")

    pdf_path = Path(args.pdf_path)

    try:
        text = extract_text_from_pdf(pdf_path)
    except PdfTextExtractionError as error:
        parser.exit(status=1, message=f"Error: {error}\n")

    print(text)
    return 0


def process_pending_documents() -> int:
    with get_session_factory() as session:
        repository = DocumentRepository(session)
        pending_documents = repository.list_pending()

        for document in pending_documents:
            if not document.source_path:
                continue

            service = DocumentService(repository, owner_id=document.owner_id)
            process_pending_document(
                service,
                document_id=document.id,
                pdf_path=Path(document.source_path),
                limits=DocumentProcessingLimits(
                    max_pages=get_max_document_pages(),
                    max_characters=get_max_document_characters(),
                ),
            )

    return 0
