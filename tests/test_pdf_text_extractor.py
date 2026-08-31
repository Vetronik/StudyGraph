from collections.abc import Callable
from pathlib import Path

import pytest

from studygraph.pdf_text_extractor import (
    PdfTextExtractionError,
    extract_pdf_document,
    extract_text_from_pdf,
)


def test_extract_text_from_pdf_raises_for_missing_file(tmp_path: Path) -> None:
    missing_pdf = tmp_path / "missing.pdf"

    with pytest.raises(PdfTextExtractionError, match="File does not exist"):
        extract_text_from_pdf(missing_pdf)


def test_extract_text_from_pdf_raises_for_non_pdf_file(tmp_path: Path) -> None:
    text_file = tmp_path / "notes.txt"
    text_file.write_text("This is not a PDF.", encoding="utf-8")

    with pytest.raises(PdfTextExtractionError, match="File is not a PDF"):
        extract_text_from_pdf(text_file)


def test_extract_text_from_pdf_returns_text_from_valid_pdf(
    tmp_path: Path,
    write_pdf_with_text: Callable[[Path, str], None],
) -> None:
    pdf_path = tmp_path / "lecture.pdf"
    write_pdf_with_text(pdf_path, "StudyGraph extracts text")

    extracted_text = extract_text_from_pdf(pdf_path)

    assert extracted_text == "StudyGraph extracts text"


def test_extract_pdf_document_returns_page_count_from_valid_pdf(
    tmp_path: Path,
    write_pdf_with_text: Callable[[Path, str], None],
) -> None:
    pdf_path = tmp_path / "lecture.pdf"
    write_pdf_with_text(pdf_path, "StudyGraph extracts text")

    document = extract_pdf_document(pdf_path)

    assert document.text == "StudyGraph extracts text"
    assert document.page_count == 1
    assert len(document.pages) == 1
    assert document.pages[0].page_number == 1
    assert document.pages[0].text == "StudyGraph extracts text"


def test_extract_text_from_pdf_raises_when_pdf_has_no_text(
    tmp_path: Path,
    write_pdf_without_text: Callable[[Path], None],
) -> None:
    pdf_path = tmp_path / "scanned.pdf"
    write_pdf_without_text(pdf_path)

    with pytest.raises(PdfTextExtractionError, match="No text could be extracted"):
        extract_text_from_pdf(pdf_path)


def test_extract_text_from_pdf_raises_for_invalid_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "broken.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nThis is not a valid PDF structure.")

    with pytest.raises(PdfTextExtractionError, match="Could not read PDF"):
        extract_text_from_pdf(pdf_path)
