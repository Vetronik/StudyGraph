from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated

from fastapi import (
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from studygraph.auth import AuthenticationError, CurrentUser, resolve_owner_id
from studygraph.config import (
    ConfigurationError,
    get_max_document_characters,
    get_max_document_pages,
    get_max_upload_bytes,
    get_require_user_header,
    is_database_configured,
)
from studygraph.database import get_session
from studygraph.document_model import Document, DocumentChunk
from studygraph.document_processing import (
    DocumentProcessingFailed,
    DocumentProcessingLimits,
    DocumentProcessingStateError,
    process_pending_document,
)
from studygraph.document_repository import DocumentRepository
from studygraph.document_service import (
    DocumentDeletionError,
    DocumentNotFoundError,
    DocumentReadError,
    DocumentSearchQueryError,
    DocumentService,
    DocumentStorageError,
)
from studygraph.retrieval_service import RetrievalService

TEXT_PREVIEW_MAX_CHARACTERS = 300
SEARCH_SNIPPET_CONTEXT_CHARACTERS = 80
UPLOAD_CHUNK_SIZE_BYTES = 1024 * 1024
PDF_HEADER = b"%PDF-"
PDF_CONTENT_TYPES = {
    "application/octet-stream",
    "application/pdf",
    "application/x-pdf",
}
WEB_DIR = Path(__file__).resolve().parent / "web"

app = FastAPI(
    title="StudyGraph API",
    description="Minimal API for extracting text information from uploaded PDFs.",
    version="0.1.0",
)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


class DocumentResponse(BaseModel):
    id: int
    filename: str
    owner_id: str
    file_size_bytes: int
    page_count: int
    character_count: int
    status: str
    processing_error: str | None
    text_preview: str
    created_at: datetime


class DocumentChunkResponse(BaseModel):
    id: int
    document_id: int
    position: int
    page_number: int
    text: str
    character_count: int
    created_at: datetime


class HealthResponse(BaseModel):
    status: str
    database_configured: bool


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    limit: int
    offset: int


class DocumentChunkListResponse(BaseModel):
    items: list[DocumentChunkResponse]


class SearchResultResponse(BaseModel):
    document_id: int
    document_filename: str
    chunk_id: int
    chunk_position: int
    page_number: int
    text: str
    snippet: str
    character_count: int
    created_at: datetime


class SearchResponse(BaseModel):
    items: list[SearchResultResponse]
    total: int
    limit: int
    offset: int
    query: str


class RetrievalContextRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    max_chunks: int = Field(default=5, ge=1, le=20)


class RetrievalSourceResponse(BaseModel):
    source_number: int
    document_id: int
    document_filename: str
    chunk_id: int
    chunk_position: int
    page_number: int
    text: str


class RetrievalContextResponse(BaseModel):
    query: str
    sources: list[RetrievalSourceResponse]
    context: str


@dataclass(frozen=True)
class SavedUpload:
    path: Path
    size_bytes: int


class UploadTooLargeError(Exception):
    """Raised when an uploaded file exceeds the configured size limit."""


class UploadContentError(Exception):
    """Raised when an uploaded file does not look like a supported PDF."""


@app.exception_handler(ConfigurationError)
async def configuration_error_handler(
    _request: Request,
    error: ConfigurationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "detail": "Application configuration error.",
            "message": str(error),
        },
    )


def _build_text_preview(text: str) -> str:
    normalized_text = " ".join(text.split())
    return normalized_text[:TEXT_PREVIEW_MAX_CHARACTERS]


def _build_document_response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        filename=document.filename,
        owner_id=document.owner_id,
        file_size_bytes=document.file_size_bytes,
        page_count=document.page_count,
        character_count=document.character_count,
        status=document.status,
        processing_error=document.processing_error,
        text_preview=_build_text_preview(document.extracted_text),
        created_at=document.created_at,
    )


def _build_document_chunk_response(chunk: DocumentChunk) -> DocumentChunkResponse:
    return DocumentChunkResponse(
        id=chunk.id,
        document_id=chunk.document_id,
        position=chunk.position,
        page_number=chunk.page_number,
        text=chunk.text,
        character_count=chunk.character_count,
        created_at=chunk.created_at,
    )


def _build_search_snippet(text: str, query: str) -> str:
    normalized_text = " ".join(text.split())
    query_index = normalized_text.lower().find(query.lower())

    if query_index < 0:
        return normalized_text[: TEXT_PREVIEW_MAX_CHARACTERS]

    start = max(query_index - SEARCH_SNIPPET_CONTEXT_CHARACTERS, 0)
    end = min(
        query_index + len(query) + SEARCH_SNIPPET_CONTEXT_CHARACTERS,
        len(normalized_text),
    )
    snippet = normalized_text[start:end].strip()

    if start > 0:
        snippet = f"...{snippet}"

    if end < len(normalized_text):
        snippet = f"{snippet}..."

    return snippet


def _build_search_result_response(
    chunk: DocumentChunk,
    *,
    query: str,
) -> SearchResultResponse:
    return SearchResultResponse(
        document_id=chunk.document_id,
        document_filename=chunk.document.filename,
        chunk_id=chunk.id,
        chunk_position=chunk.position,
        page_number=chunk.page_number,
        text=chunk.text,
        snippet=_build_search_snippet(chunk.text, query),
        character_count=chunk.character_count,
        created_at=chunk.created_at,
    )


def get_current_user(
    x_studygraph_user: Annotated[
        str | None,
        Header(alias="X-StudyGraph-User", max_length=120),
    ] = None,
) -> CurrentUser:
    try:
        owner_id = resolve_owner_id(
            x_studygraph_user,
            require_header=get_require_user_header(),
        )
    except AuthenticationError as error:
        status_code = (
            status.HTTP_401_UNAUTHORIZED
            if x_studygraph_user is None
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=status_code,
            detail=str(error),
        ) from error

    return CurrentUser(owner_id=owner_id)


def get_document_service(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> DocumentService:
    return DocumentService(
        DocumentRepository(session),
        owner_id=current_user.owner_id,
    )


def get_retrieval_service(
    document_service: Annotated[DocumentService, Depends(get_document_service)],
) -> RetrievalService:
    return RetrievalService(document_service)


async def _save_upload_to_temporary_pdf(
    upload: UploadFile,
    *,
    max_bytes: int,
) -> SavedUpload:
    temporary_path: Path | None = None
    size_bytes = 0

    try:
        with NamedTemporaryFile(delete=False, suffix=".pdf") as temporary_file:
            temporary_path = Path(temporary_file.name)

            while chunk := await upload.read(UPLOAD_CHUNK_SIZE_BYTES):
                size_bytes += len(chunk)

                if size_bytes > max_bytes:
                    raise UploadTooLargeError(
                        "Uploaded file is too large. "
                        f"Maximum size is {max_bytes} bytes."
                    )

                temporary_file.write(chunk)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise

    return SavedUpload(path=temporary_path, size_bytes=size_bytes)


def _validate_upload_content_type(upload: UploadFile) -> None:
    if upload.content_type is None:
        return

    content_type = upload.content_type.split(";", maxsplit=1)[0].strip().lower()

    if content_type not in PDF_CONTENT_TYPES:
        raise UploadContentError("Uploaded file must use a PDF content type.")


def _validate_pdf_header(pdf_path: Path) -> None:
    with pdf_path.open("rb") as pdf_file:
        header = pdf_file.read(len(PDF_HEADER))

    if header != PDF_HEADER:
        raise UploadContentError("Uploaded file content is not a PDF.")


@app.get(
    "/",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def frontend_index() -> HTMLResponse:
    index_path = WEB_DIR / "index.html"
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
)
def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        database_configured=is_database_configured(),
    )


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

    try:
        _validate_upload_content_type(file)
    except UploadContentError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    saved_upload: SavedUpload | None = None
    document: Document | None = None

    try:
        saved_upload = await _save_upload_to_temporary_pdf(
            file,
            max_bytes=get_max_upload_bytes(),
        )
        _validate_pdf_header(saved_upload.path)
        document = document_service.create_pending_document(
            filename=filename,
            file_size_bytes=saved_upload.size_bytes,
        )
        document = process_pending_document(
            document_service,
            document_id=document.id,
            pdf_path=saved_upload.path,
            limits=DocumentProcessingLimits(
                max_pages=get_max_document_pages(),
                max_characters=get_max_document_characters(),
            ),
        )
    except UploadTooLargeError as error:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=str(error),
        ) from error
    except UploadContentError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    except DocumentProcessingFailed as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": f"Could not process PDF: {error.message}",
                "document_id": error.document_id,
            },
        ) from error
    except DocumentStorageError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save document.",
        ) from error
    except DocumentProcessingStateError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save document processing state.",
        ) from error
    finally:
        await file.close()

        if saved_upload is not None:
            saved_upload.path.unlink(missing_ok=True)

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not process document.",
        )

    return _build_document_response(document)


@app.get(
    "/documents",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
)
def list_documents(
    document_service: Annotated[DocumentService, Depends(get_document_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    query: Annotated[str | None, Query(max_length=200)] = None,
) -> DocumentListResponse:
    try:
        document_list = document_service.list_documents(
            limit=limit,
            offset=offset,
            query=query,
        )
    except DocumentReadError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not load documents.",
        ) from error

    return DocumentListResponse(
        items=[
            _build_document_response(document)
            for document in document_list.documents
        ],
        total=document_list.total,
        limit=document_list.limit,
        offset=document_list.offset,
    )


@app.get(
    "/search",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK,
)
def search_document_chunks(
    document_service: Annotated[DocumentService, Depends(get_document_service)],
    query: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SearchResponse:
    try:
        search_results = document_service.search_chunks(
            query=query,
            limit=limit,
            offset=offset,
        )
    except DocumentSearchQueryError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    except DocumentReadError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not search document chunks.",
        ) from error

    return SearchResponse(
        items=[
            _build_search_result_response(
                chunk,
                query=search_results.query,
            )
            for chunk in search_results.chunks
        ],
        total=search_results.total,
        limit=search_results.limit,
        offset=search_results.offset,
        query=search_results.query,
    )


@app.post(
    "/rag/context",
    response_model=RetrievalContextResponse,
    status_code=status.HTTP_200_OK,
)
def build_rag_context(
    request: RetrievalContextRequest,
    retrieval_service: Annotated[RetrievalService, Depends(get_retrieval_service)],
) -> RetrievalContextResponse:
    try:
        retrieval_context = retrieval_service.build_context(
            query=request.query,
            max_chunks=request.max_chunks,
        )
    except DocumentSearchQueryError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    except DocumentReadError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not build retrieval context.",
        ) from error

    return RetrievalContextResponse(
        query=retrieval_context.query,
        sources=[
            RetrievalSourceResponse(
                source_number=source.source_number,
                document_id=source.document_id,
                document_filename=source.document_filename,
                chunk_id=source.chunk_id,
                chunk_position=source.chunk_position,
                page_number=source.page_number,
                text=source.text,
            )
            for source in retrieval_context.sources
        ],
        context=retrieval_context.context,
    )


@app.get(
    "/documents/{document_id}/chunks",
    response_model=DocumentChunkListResponse,
    status_code=status.HTTP_200_OK,
)
def list_document_chunks(
    document_id: int,
    document_service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentChunkListResponse:
    try:
        chunk_list = document_service.list_document_chunks(document_id)
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with id {document_id} was not found.",
        ) from error
    except DocumentReadError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not load document chunks.",
        ) from error

    return DocumentChunkListResponse(
        items=[
            _build_document_chunk_response(chunk)
            for chunk in chunk_list.chunks
        ],
    )


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
    except DocumentReadError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not load document.",
        ) from error

    return _build_document_response(document)


@app.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_document(
    document_id: int,
    document_service: Annotated[DocumentService, Depends(get_document_service)],
) -> Response:
    try:
        document_service.delete_document(document_id)
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with id {document_id} was not found.",
        ) from error
    except DocumentDeletionError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not delete document.",
        ) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)
