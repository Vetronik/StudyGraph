from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from studygraph.database import get_session
from studygraph.document_model import Document
from studygraph.document_repository import DocumentRepository
from studygraph.document_service import (
    DocumentNotFoundError,
    DocumentService,
    DocumentStorageError,
)
from studygraph.pdf_text_extractor import PdfTextExtractionError, extract_pdf_document

TEXT_PREVIEW_MAX_CHARACTERS = 300

app = FastAPI(
    title="StudyGraph API",
    description="Minimal API for extracting text information from uploaded PDFs.",
    version="0.1.0",
)


class DocumentResponse(BaseModel):
    id: int
    filename: str
    page_count: int
    character_count: int
    text_preview: str
    created_at: datetime


def _build_text_preview(text: str) -> str:
    normalized_text = " ".join(text.split())
    return normalized_text[:TEXT_PREVIEW_MAX_CHARACTERS]


def _build_document_response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        filename=document.filename,
        page_count=document.page_count,
        character_count=document.character_count,
        text_preview=_build_text_preview(document.extracted_text),
        created_at=document.created_at,
    )


def get_document_service(
    session: Annotated[Session, Depends(get_session)],
) -> DocumentService:
    return DocumentService(DocumentRepository(session))


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
    document_service: Annotated[DocumentService, Depends(get_document_service)],
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
        extracted_document = extract_pdf_document(temporary_path)
        document = document_service.create_document(
            filename=filename,
            extracted_document=extracted_document,
        )
    except PdfTextExtractionError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Could not process PDF: {error}",
        ) from error
    except DocumentStorageError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save document.",
        ) from error
    finally:
        await file.close()

        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return _build_document_response(document)


@app.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
)
def get_document(
    document_id: int,
    document_service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentResponse:
    try:
        document = document_service.get_document(document_id)
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with id {document_id} was not found.",
        ) from error

    return _build_document_response(document)
