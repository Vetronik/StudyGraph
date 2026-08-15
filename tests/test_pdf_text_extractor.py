from pathlib import Path

import pytest
from pypdf import PdfWriter

from studygraph.pdf_text_extractor import PdfTextExtractionError, extract_text_from_pdf


def _write_pdf_with_text(pdf_path: Path) -> None:
    text = b"StudyGraph extracts text"
    content_stream = b"BT /F1 12 Tf 72 720 Td (" + text + b") Tj ET"

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        (
            b"<< /Length "
            + str(len(content_stream)).encode("ascii")
            + b" >>\nstream\n"
            + content_stream
            + b"\nendstream"
        ),
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = []

    for object_number, object_content in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{object_number} 0 obj\n".encode("ascii"))
        pdf.extend(object_content)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")

    for offset in offsets:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))

    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    pdf_path.write_bytes(pdf)


def _write_pdf_without_text(pdf_path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)

    with pdf_path.open("wb") as pdf_file:
        writer.write(pdf_file)


def test_extract_text_from_pdf_raises_for_missing_file(tmp_path: Path) -> None:
    missing_pdf = tmp_path / "missing.pdf"

    with pytest.raises(PdfTextExtractionError, match="File does not exist"):
        extract_text_from_pdf(missing_pdf)


def test_extract_text_from_pdf_raises_for_non_pdf_file(tmp_path: Path) -> None:
    text_file = tmp_path / "notes.txt"
    text_file.write_text("This is not a PDF.", encoding="utf-8")

    with pytest.raises(PdfTextExtractionError, match="File is not a PDF"):
        extract_text_from_pdf(text_file)


def test_extract_text_from_pdf_returns_text_from_valid_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "lecture.pdf"
    _write_pdf_with_text(pdf_path)

    extracted_text = extract_text_from_pdf(pdf_path)

    assert extracted_text == "StudyGraph extracts text"


def test_extract_text_from_pdf_raises_when_pdf_has_no_text(tmp_path: Path) -> None:
    pdf_path = tmp_path / "scanned.pdf"
    _write_pdf_without_text(pdf_path)

    with pytest.raises(PdfTextExtractionError, match="No text could be extracted"):
        extract_text_from_pdf(pdf_path)


def test_extract_text_from_pdf_raises_for_invalid_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "broken.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nThis is not a valid PDF structure.")

    with pytest.raises(PdfTextExtractionError, match="Could not read PDF"):
        extract_text_from_pdf(pdf_path)
