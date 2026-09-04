from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from studygraph.config import get_ocr_enabled, get_ocr_language


class PdfTextExtractionError(Exception):
    """Raised when text cannot be extracted from a PDF file."""


@dataclass(frozen=True)
class ExtractedPdfPage:
    page_number: int
    text: str


@dataclass(frozen=True)
class ExtractedPdfDocument:
    text: str
    page_count: int
    pages: tuple[ExtractedPdfPage, ...] = ()


def extract_pdf_document(pdf_path: Path) -> ExtractedPdfDocument:
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

    pages: list[ExtractedPdfPage] = []
    page_count = len(reader.pages)

    for page_number, page in enumerate(reader.pages, start=1):
        try:
            page_text = page.extract_text() or ""
        except Exception as error:
            raise PdfTextExtractionError(
                f"Could not extract text from page {page_number}: {error}"
            ) from error

        if page_text.strip():
            pages.append(
                ExtractedPdfPage(
                    page_number=page_number,
                    text=page_text.strip(),
                )
            )

    extracted_text = "\n\n".join(page.text for page in pages)

    if not extracted_text and get_ocr_enabled():
        extracted_text, pages = _extract_text_with_ocr(
            pdf_path,
            page_count=page_count,
        )

    if not extracted_text:
        raise PdfTextExtractionError(
            "No text could be extracted. The PDF may contain scanned images only."
        )

    return ExtractedPdfDocument(
        text=extracted_text,
        page_count=page_count,
        pages=tuple(pages),
    )


def _extract_text_with_ocr(
    pdf_path: Path,
    *,
    page_count: int,
) -> tuple[str, list[ExtractedPdfPage]]:
    try:
        import fitz
        import pytesseract
        from PIL import Image
    except ImportError as error:
        raise PdfTextExtractionError(
            "OCR is enabled but its dependencies are not installed."
        ) from error

    ocr_pages: list[ExtractedPdfPage] = []
    try:
        with fitz.open(pdf_path) as pdf:
            for page_index, page in enumerate(pdf, start=1):
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image = Image.frombytes(
                    "RGB",
                    (pixmap.width, pixmap.height),
                    pixmap.samples,
                )
                page_text = pytesseract.image_to_string(
                    image,
                    lang=get_ocr_language(),
                ).strip()
                if page_text:
                    ocr_pages.append(
                        ExtractedPdfPage(page_number=page_index, text=page_text)
                    )
    except Exception as error:
        raise PdfTextExtractionError(
            f"Could not extract text with OCR: {error}"
        ) from error

    return "\n\n".join(page.text for page in ocr_pages), ocr_pages


def extract_text_from_pdf(pdf_path: Path) -> str:
    return extract_pdf_document(pdf_path).text
