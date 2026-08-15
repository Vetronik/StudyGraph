from pathlib import Path

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from studygraph.api import app

client = TestClient(app)


def _write_pdf_with_text(pdf_path: Path) -> None:
    text = b"StudyGraph extracts text through the API"
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


def test_create_document_returns_summary_for_valid_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "lecture.pdf"
    _write_pdf_with_text(pdf_path)

    response = client.post(
        "/documents",
        files={
            "file": (
                "lecture.pdf",
                pdf_path.read_bytes(),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "filename": "lecture.pdf",
        "page_count": 1,
        "character_count": 40,
        "text_preview": "StudyGraph extracts text through the API",
    }


def test_create_document_rejects_non_pdf_file() -> None:
    response = client.post(
        "/documents",
        files={"file": ("notes.txt", b"This is not a PDF.", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Uploaded file must have a .pdf extension."
    }


def test_create_document_rejects_invalid_pdf() -> None:
    response = client.post(
        "/documents",
        files={
            "file": (
                "broken.pdf",
                b"%PDF-1.4\nThis is not a valid PDF structure.",
                "application/pdf",
            )
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"].startswith(
        "Could not process PDF: Could not read PDF:"
    )


def test_create_document_rejects_pdf_without_extractable_text(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "scanned.pdf"
    _write_pdf_without_text(pdf_path)

    response = client.post(
        "/documents",
        files={
            "file": (
                "scanned.pdf",
                pdf_path.read_bytes(),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": (
            "Could not process PDF: No text could be extracted. "
            "The PDF may contain scanned images only."
        )
    }
