from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from studygraph.pdf_text_extractor import PdfTextExtractionError, extract_pdf_document

TEXT_PREVIEW_MAX_CHARACTERS = 300

app = FastAPI(
    title="StudyGraph API",
    description="Minimal API for extracting text information from uploaded PDFs.",
    version="0.1.0",
)


class DocumentResponse(BaseModel):
    filename: str
    page_count: int
    character_count: int
    text_preview: str


def _build_text_preview(text: str) -> str:
    normalized_text = " ".join(text.split())
    return normalized_text[:TEXT_PREVIEW_MAX_CHARACTERS]


async def _save_upload_to_temporary_pdf(upload: UploadFile) -> Path:
    with NamedTemporaryFile(delete=False, suffix=".pdf") as temporary_file:
        temporary_path = Path(temporary_file.name)

        while chunk := await upload.read(1024 * 1024):
            temporary_file.write(chunk)

    return temporary_path


@app.post(
    "/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
)
async def create_document(
    file: Annotated[UploadFile, File(description="PDF file to process")],
) -> DocumentResponse:
    filename = file.filename or ""

    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must include a filename.",
        )

    if Path(filename).suffix.lower() != ".pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a .pdf extension.",
        )

    temporary_path: Path | None = None

    try:
        temporary_path = await _save_upload_to_temporary_pdf(file)
        document = extract_pdf_document(temporary_path)
    except PdfTextExtractionError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Could not process PDF: {error}",
        ) from error
    finally:
        await file.close()

        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return DocumentResponse(
        filename=filename,
        page_count=document.page_count,
        character_count=len(document.text),
        text_preview=_build_text_preview(document.text),
    )
