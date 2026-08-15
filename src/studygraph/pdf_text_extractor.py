from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class PdfTextExtractionError(Exception):
    """Raised when text cannot be extracted from a PDF file."""


def extract_text_from_pdf(pdf_path: Path) -> str:
    if not pdf_path.exists():
        raise PdfTextExtractionError(f"File does not exist: {pdf_path}")

    if not pdf_path.is_file():
        raise PdfTextExtractionError(f"Path is not a file: {pdf_path}")

    if pdf_path.suffix.lower() != ".pdf":
        raise PdfTextExtractionError(f"File is not a PDF: {pdf_path}")

    try:
        reader = PdfReader(pdf_path)
    except (PdfReadError, OSError) as error:
        raise PdfTextExtractionError(f"Could not read PDF: {error}") from error

    page_texts: list[str] = []

    for page_number, page in enumerate(reader.pages, start=1):
        try:
            page_text = page.extract_text() or ""
        except Exception as error:
            raise PdfTextExtractionError(
                f"Could not extract text from page {page_number}: {error}"
            ) from error

        if page_text.strip():
            page_texts.append(page_text.strip())

    extracted_text = "\n\n".join(page_texts)

    if not extracted_text:
        raise PdfTextExtractionError(
            "No text could be extracted. The PDF may contain scanned images only."
        )

    return extracted_text

