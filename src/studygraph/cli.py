import argparse
from pathlib import Path

from studygraph.database import get_session_factory
from studygraph.document_repository import DocumentRepository
from studygraph.document_worker import process_document_job
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
        pending_documents = [
            (document.id, Path(document.source_path))
            for document in repository.list_pending()
            if document.source_path
        ]

    for document_id, pdf_path in pending_documents:
        process_document_job(document_id, pdf_path)

    return 0
