import hashlib
import logging
import os
import shutil
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated
from uuid import uuid4

from fastapi import (
    BackgroundTasks,
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
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.middleware.trustedhost import TrustedHostMiddleware

from studygraph.auth import (
    AuthenticationError,
    CurrentUser,
    answer_rate_limiter,
    create_access_token,
    decode_access_token,
    login_rate_limiter,
    resolve_owner_id,
)
from studygraph.auth_service import (
    AuthService,
    InvalidCredentialsError,
    UserAlreadyExistsError,
)
from studygraph.collection_repository import (
    CollectionNameConflictError,
    CollectionRepository,
    CollectionRepositoryError,
)
from studygraph.collection_service import (
    CollectionNotFoundError,
    CollectionService,
    CollectionValidationError,
)
from studygraph.config import (
    ConfigurationError,
    get_allowed_hosts,
    get_answer_max_requests,
    get_answer_rate_window_seconds,
    get_auth_max_login_attempts,
    get_auth_rate_window_seconds,
    get_auth_secret,
    get_document_storage_dir,
    get_max_upload_bytes,
    get_metrics_enabled,
    get_process_uploads_in_api,
    get_require_auth_token,
    get_require_user_header,
    get_token_lifetime_seconds,
    is_database_configured,
)
from studygraph.database import get_session
from studygraph.document_model import Document, DocumentChunk, LearningProgress
from studygraph.document_processing import DocumentProcessingStateError
from studygraph.document_repository import DocumentRepository
from studygraph.document_service import (
    DocumentDeletionError,
    DocumentDuplicateError,
    DocumentNotFoundError,
    DocumentReadError,
    DocumentSearchQueryError,
    DocumentService,
    DocumentStorageError,
)
from studygraph.document_storage import (
    InvalidDocumentStoragePath,
    resolve_stored_document_path,
)
from studygraph.document_worker import process_document_job
from studygraph.embedding_service import get_embedding_provider
from studygraph.learning_service import (
    ExtractiveSummaryService,
    LocalFlashcardService,
    LocalQuizService,
)
from studygraph.logging_config import configure_logging
from studygraph.metrics import HttpMetrics
from studygraph.rag_service import AnswerProviderError, RAGService
from studygraph.retrieval_service import RetrievalService
from studygraph.user_repository import UserRepository

logger = logging.getLogger(__name__)
http_metrics = HttpMetrics()

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

DocumentProcessor = Callable[[int, Path], None]
REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_ALLOWED_CHARACTERS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    yield

app = FastAPI(
    title="StudyGraph API",
    description="Minimal API for extracting text information from uploaded PDFs.",
    version="0.1.0",
    lifespan=lifespan,
)
allowed_hosts = get_allowed_hosts()
if allowed_hosts != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    request_id = request.headers.get(REQUEST_ID_HEADER, "")
    if not (
        0 < len(request_id) <= 64
        and all(character in REQUEST_ID_ALLOWED_CHARACTERS for character in request_id)
    ):
        request_id = uuid4().hex
    request.state.request_id = request_id
    started_at = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "http_request_failed method=%s path=%s request_id=%s",
            request.method,
            request.url.path,
            request_id,
        )
        raise

    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), geolocation=(), microphone=()",
    )
    if request.url.path.startswith("/auth/") or request.url.path == "/metrics":
        response.headers["Cache-Control"] = "no-store"
    response.headers[REQUEST_ID_HEADER] = request_id
    route = getattr(request.scope.get("route"), "path", "unmatched")
    http_metrics.observe(
        method=request.method,
        route=route,
        status_code=response.status_code,
        duration_seconds=time.perf_counter() - started_at,
    )
    logger.info(
        "http_request_completed method=%s path=%s status_code=%s "
        "duration_ms=%.2f request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        (time.perf_counter() - started_at) * 1000,
        request_id,
    )
    return response


class DocumentResponse(BaseModel):
    id: int
    filename: str
    owner_id: str
    content_hash: str | None
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


class ReadinessResponse(BaseModel):
    status: str
    database: str


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


class RAGAnswerRequest(BaseModel):
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


class RAGAnswerResponse(BaseModel):
    query: str
    answer: str
    sources: list[RetrievalSourceResponse]


class SummarySourceResponse(BaseModel):
    chunk_id: int
    chunk_position: int
    page_number: int
    text: str


class SummaryResponse(BaseModel):
    document_id: int
    filename: str
    summary: str
    sources: list[SummarySourceResponse]


class QuizQuestionResponse(BaseModel):
    question_type: str
    question: str
    answer: str
    options: list[str]
    chunk_id: int
    chunk_position: int
    page_number: int


class QuizResponse(BaseModel):
    document_id: int
    filename: str
    questions: list[QuizQuestionResponse]


class FlashcardResponse(BaseModel):
    front: str
    back: str
    chunk_id: int
    chunk_position: int
    page_number: int


class FlashcardsResponse(BaseModel):
    document_id: int
    filename: str
    cards: list[FlashcardResponse]


class CollectionCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class CollectionDocumentRequest(BaseModel):
    document_id: int = Field(gt=0)


class CollectionDocumentResponse(BaseModel):
    id: int
    filename: str


class CollectionResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    documents: list[CollectionDocumentResponse]


class QuizValidationRequest(BaseModel):
    question_index: int = Field(ge=0, le=19)
    answer: str = Field(min_length=1, max_length=200)
    count: int = Field(default=5, ge=1, le=20)


class QuizValidationResponse(BaseModel):
    question_index: int
    correct: bool


class ProgressResponse(BaseModel):
    document_id: int
    review_count: int
    mastered: bool
    last_reviewed_at: datetime | None


class ProgressUpdateRequest(BaseModel):
    mastered: bool | None = None


class AuthRequest(BaseModel):
    username: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=8, max_length=256)


class UserResponse(BaseModel):
    username: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


@dataclass(frozen=True)
class SavedUpload:
    path: Path
    size_bytes: int
    content_hash: str


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
        content_hash=document.content_hash,
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
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    if authorization is not None:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization must use a Bearer token.",
            )
        try:
            return CurrentUser(
                owner_id=decode_access_token(token, secret=get_auth_secret()),
            )
        except AuthenticationError as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(error),
            ) from error

    if get_require_auth_token():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer authentication is required.",
        )

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


@app.get("/metrics", include_in_schema=False)
def metrics(
    _current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> PlainTextResponse:
    if not get_metrics_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return PlainTextResponse(
        http_metrics.render_prometheus(),
        media_type="text/plain; version=0.0.4",
    )


def get_document_service(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> DocumentService:
    embedding_provider = get_embedding_provider()
    return DocumentService(
        DocumentRepository(session, embedding_provider=embedding_provider),
        owner_id=current_user.owner_id,
        embedding_provider=embedding_provider,
    )


def get_collection_service(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> CollectionService:
    return CollectionService(
        CollectionRepository(session),
        owner_id=current_user.owner_id,
    )


def get_retrieval_service(
    document_service: Annotated[DocumentService, Depends(get_document_service)],
) -> RetrievalService:
    return RetrievalService(document_service)


def get_rag_service(
    retrieval_service: Annotated[RetrievalService, Depends(get_retrieval_service)],
) -> RAGService:
    return RAGService(retrieval_service)


def get_summary_service(
    document_service: Annotated[DocumentService, Depends(get_document_service)],
) -> ExtractiveSummaryService:
    return ExtractiveSummaryService(document_service)


def get_quiz_service(
    document_service: Annotated[DocumentService, Depends(get_document_service)],
) -> LocalQuizService:
    return LocalQuizService(document_service)


def get_flashcard_service(
    document_service: Annotated[DocumentService, Depends(get_document_service)],
) -> LocalFlashcardService:
    return LocalFlashcardService(document_service)


def get_document_processor() -> DocumentProcessor:
    return process_document_job


def get_auth_service(
    session: Annotated[Session, Depends(get_session)],
) -> AuthService:
    return AuthService(UserRepository(session))


def _normalize_username(username: str) -> str:
    try:
        return resolve_owner_id(username, require_header=True)
    except AuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username contains invalid characters.",
        ) from error


@app.get(
    "/hybrid-search",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK,
)
def hybrid_search_document_chunks(
    document_service: Annotated[DocumentService, Depends(get_document_service)],
    query: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SearchResponse:
    try:
        search_results = document_service.hybrid_search_chunks(
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
            detail="Could not run hybrid document search.",
        ) from error

    return SearchResponse(
        items=[
            _build_search_result_response(chunk, query=search_results.query)
            for chunk in search_results.chunks
        ],
        total=search_results.total,
        limit=search_results.limit,
        offset=search_results.offset,
        query=search_results.query,
    )


@app.post(
    "/auth/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(
    request: AuthRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserResponse:
    username = _normalize_username(request.username)
    try:
        user = auth_service.register(username, request.password)
    except UserAlreadyExistsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username is already registered.",
        ) from error

    return UserResponse(username=user.username, created_at=user.created_at)


@app.post(
    "/auth/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
def login_user(
    request: AuthRequest,
    http_request: Request,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    rate_window_seconds = get_auth_rate_window_seconds()
    client_key = http_request.client.host if http_request.client else "unknown"
    if login_rate_limiter.is_blocked(
        client_key,
        max_attempts=get_auth_max_login_attempts(),
        window_seconds=rate_window_seconds,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
            headers={"Retry-After": str(rate_window_seconds)},
        )

    username = _normalize_username(request.username)
    try:
        auth_service.authenticate(username, request.password)
    except InvalidCredentialsError as error:
        login_rate_limiter.record_failure(
            client_key,
            window_seconds=rate_window_seconds,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        ) from error

    login_rate_limiter.reset(client_key)
    lifetime_seconds = get_token_lifetime_seconds()
    return TokenResponse(
        access_token=create_access_token(
            username,
            secret=get_auth_secret(),
            lifetime_seconds=lifetime_seconds,
        ),
        token_type="bearer",
        expires_in=lifetime_seconds,
    )


async def _save_upload_to_temporary_pdf(
    upload: UploadFile,
    *,
    max_bytes: int,
) -> SavedUpload:
    temporary_path: Path | None = None
    size_bytes = 0
    content_hasher = hashlib.sha256()

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
                content_hasher.update(chunk)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise

    return SavedUpload(
        path=temporary_path,
        size_bytes=size_bytes,
        content_hash=content_hasher.hexdigest(),
    )


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


def _persist_upload(saved_upload: SavedUpload) -> Path:
    storage_dir = Path(get_document_storage_dir()).resolve()
    storage_dir.mkdir(parents=True, exist_ok=True)
    persistent_path = storage_dir / f"upload-{uuid4().hex}.pdf"
    temporary_path = storage_dir / f".upload-{uuid4().hex}.tmp"

    try:
        with (
            saved_upload.path.open("rb") as source,
            temporary_path.open("xb") as target,
        ):
            shutil.copyfileobj(source, target)
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, persistent_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    saved_upload.path.unlink(missing_ok=True)
    return persistent_path


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
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_document(
    file: Annotated[UploadFile, File(description="PDF file to process")],
    background_tasks: BackgroundTasks,
    document_service: Annotated[DocumentService, Depends(get_document_service)],
    document_processor: Annotated[
        DocumentProcessor,
        Depends(get_document_processor),
    ],
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
    persistent_path: Path | None = None
    document: Document | None = None

    try:
        saved_upload = await _save_upload_to_temporary_pdf(
            file,
            max_bytes=get_max_upload_bytes(),
        )
        _validate_pdf_header(saved_upload.path)
        persistent_path = _persist_upload(saved_upload)
        document = document_service.create_pending_document(
            filename=filename,
            file_size_bytes=saved_upload.size_bytes,
            content_hash=saved_upload.content_hash,
            source_path=str(persistent_path),
        )
        logger.info(
            "document_upload_accepted owner_id=%s document_id=%s filename=%s "
            "file_size_bytes=%s",
            document.owner_id,
            document.id,
            document.filename,
            document.file_size_bytes,
        )
        if get_process_uploads_in_api():
            background_tasks.add_task(
                document_processor,
                document.id,
                persistent_path,
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
    except DocumentDuplicateError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document already exists for the current user.",
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

        if document is None and persistent_path is not None:
            persistent_path.unlink(missing_ok=True)

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
    "/ready",
    response_model=ReadinessResponse,
    status_code=status.HTTP_200_OK,
)
def readiness_check(
    session: Annotated[Session, Depends(get_session)],
) -> ReadinessResponse:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not ready.",
        ) from error

    return ReadinessResponse(status="ready", database="ok")


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


@app.get(
    "/semantic-search",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK,
)
def semantic_search_document_chunks(
    document_service: Annotated[DocumentService, Depends(get_document_service)],
    query: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SearchResponse:
    try:
        search_results = document_service.semantic_search_chunks(
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
            detail="Could not search document embeddings.",
        ) from error

    return SearchResponse(
        items=[
            _build_search_result_response(chunk, query=search_results.query)
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


@app.post(
    "/ask",
    response_model=RAGAnswerResponse,
    status_code=status.HTTP_200_OK,
)
def ask_documents(
    request: RAGAnswerRequest,
    http_request: Request,
    rag_service: Annotated[RAGService, Depends(get_rag_service)],
) -> RAGAnswerResponse:
    rate_window_seconds = get_answer_rate_window_seconds()
    client_key = http_request.client.host if http_request.client else "unknown"
    if answer_rate_limiter.is_blocked(
        client_key,
        max_attempts=get_answer_max_requests(),
        window_seconds=rate_window_seconds,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many answer requests. Try again later.",
            headers={"Retry-After": str(rate_window_seconds)},
        )
    answer_rate_limiter.record_failure(
        client_key,
        window_seconds=rate_window_seconds,
    )
    try:
        result = rag_service.answer(
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
            detail="Could not answer the document question.",
        ) from error
    except AnswerProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The configured answer provider is unavailable.",
        ) from error

    return RAGAnswerResponse(
        query=result.query,
        answer=result.answer,
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
            for source in result.sources
        ],
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


@app.get(
    "/documents/{document_id}/summary",
    response_model=SummaryResponse,
    status_code=status.HTTP_200_OK,
)
def summarize_document(
    document_id: int,
    summary_service: Annotated[
        ExtractiveSummaryService,
        Depends(get_summary_service),
    ],
    max_sentences: Annotated[int, Query(ge=1, le=10)] = 5,
) -> SummaryResponse:
    try:
        summary = summary_service.summarize(
            document_id=document_id,
            max_sentences=max_sentences,
        )
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with id {document_id} was not found.",
        ) from error
    except DocumentReadError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create document summary.",
        ) from error

    return SummaryResponse(
        document_id=summary.document_id,
        filename=summary.filename,
        summary=summary.summary,
        sources=[
            SummarySourceResponse(
                chunk_id=source.chunk_id,
                chunk_position=source.chunk_position,
                page_number=source.page_number,
                text=source.text,
            )
            for source in summary.sources
        ],
    )


@app.get(
    "/documents/{document_id}/quiz",
    response_model=QuizResponse,
    status_code=status.HTTP_200_OK,
)
def generate_document_quiz(
    document_id: int,
    quiz_service: Annotated[LocalQuizService, Depends(get_quiz_service)],
    count: Annotated[int, Query(ge=1, le=20)] = 5,
) -> QuizResponse:
    try:
        quiz = quiz_service.generate(document_id=document_id, count=count)
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with id {document_id} was not found.",
        ) from error
    except DocumentReadError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create document quiz.",
        ) from error

    return QuizResponse(
        document_id=quiz.document_id,
        filename=quiz.filename,
        questions=[
            QuizQuestionResponse(
                question_type=question.question_type,
                question=question.question,
                answer=question.answer,
                options=question.options,
                chunk_id=question.chunk_id,
                chunk_position=question.chunk_position,
                page_number=question.page_number,
            )
            for question in quiz.questions
        ],
    )


@app.post(
    "/documents/{document_id}/quiz/validate",
    response_model=QuizValidationResponse,
    status_code=status.HTTP_200_OK,
)
def validate_document_quiz_answer(
    document_id: int,
    request: QuizValidationRequest,
    quiz_service: Annotated[LocalQuizService, Depends(get_quiz_service)],
) -> QuizValidationResponse:
    try:
        correct = quiz_service.validate_answer(
            document_id=document_id,
            question_index=request.question_index,
            submitted_answer=request.answer,
            count=request.count,
        )
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with id {document_id} was not found.",
        ) from error
    except (DocumentReadError, IndexError) as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question index is not available for this quiz.",
        ) from error

    return QuizValidationResponse(
        question_index=request.question_index,
        correct=correct,
    )


def _build_collection_response(collection) -> CollectionResponse:
    return CollectionResponse(
        id=collection.id,
        name=collection.name,
        created_at=collection.created_at,
        documents=[
            CollectionDocumentResponse(id=document.id, filename=document.filename)
            for document in collection.documents
        ],
    )


@app.post(
    "/collections",
    response_model=CollectionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_collection(
    request: CollectionCreateRequest,
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> CollectionResponse:
    try:
        return _build_collection_response(collection_service.create(request.name))
    except CollectionValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except CollectionNameConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except CollectionRepositoryError as error:
        raise HTTPException(
            status_code=500,
            detail="Could not create collection.",
        ) from error


@app.get(
    "/collections",
    response_model=list[CollectionResponse],
    status_code=status.HTTP_200_OK,
)
def list_collections(
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> list[CollectionResponse]:
    try:
        collections = collection_service.list().collections
        return [_build_collection_response(item) for item in collections]
    except CollectionRepositoryError as error:
        raise HTTPException(
            status_code=500,
            detail="Could not list collections.",
        ) from error


@app.post(
    "/collections/{collection_id}/documents",
    response_model=CollectionResponse,
    status_code=status.HTTP_200_OK,
)
def add_document_to_collection(
    collection_id: int,
    request: CollectionDocumentRequest,
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> CollectionResponse:
    try:
        collection = collection_service.add_document(collection_id, request.document_id)
    except CollectionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except CollectionRepositoryError as error:
        raise HTTPException(
            status_code=500,
            detail="Could not add document to collection.",
        ) from error
    return _build_collection_response(collection)


@app.delete(
    "/collections/{collection_id}/documents/{document_id}",
    response_model=CollectionResponse,
    status_code=status.HTTP_200_OK,
)
def remove_document_from_collection(
    collection_id: int,
    document_id: int,
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> CollectionResponse:
    try:
        collection = collection_service.remove_document(collection_id, document_id)
    except CollectionNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except CollectionRepositoryError as error:
        raise HTTPException(
            status_code=500,
            detail="Could not remove document from collection.",
        ) from error
    return _build_collection_response(collection)


@app.get(
    "/documents/{document_id}/flashcards",
    response_model=FlashcardsResponse,
    status_code=status.HTTP_200_OK,
)
def generate_document_flashcards(
    document_id: int,
    flashcard_service: Annotated[
        LocalFlashcardService,
        Depends(get_flashcard_service),
    ],
    count: Annotated[int, Query(ge=1, le=50)] = 10,
) -> FlashcardsResponse:
    try:
        flashcards = flashcard_service.generate(
            document_id=document_id,
            count=count,
        )
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with id {document_id} was not found.",
        ) from error
    except DocumentReadError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create document flashcards.",
        ) from error

    return FlashcardsResponse(
        document_id=flashcards.document_id,
        filename=flashcards.filename,
        cards=[
            FlashcardResponse(
                front=card.front,
                back=card.back,
                chunk_id=card.chunk_id,
                chunk_position=card.chunk_position,
                page_number=card.page_number,
            )
            for card in flashcards.cards
        ],
    )


def _build_progress_response(progress: LearningProgress) -> ProgressResponse:
    return ProgressResponse(
        document_id=progress.document_id,
        review_count=progress.review_count,
        mastered=progress.mastered,
        last_reviewed_at=progress.last_reviewed_at,
    )


@app.get(
    "/documents/{document_id}/progress",
    response_model=ProgressResponse,
    status_code=status.HTTP_200_OK,
)
def get_document_progress(
    document_id: int,
    document_service: Annotated[DocumentService, Depends(get_document_service)],
) -> ProgressResponse:
    try:
        return _build_progress_response(
            document_service.get_learning_progress(document_id)
        )
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with id {document_id} was not found.",
        ) from error
    except DocumentReadError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not load learning progress.",
        ) from error


@app.post(
    "/documents/{document_id}/progress/review",
    response_model=ProgressResponse,
    status_code=status.HTTP_200_OK,
)
def review_document(
    document_id: int,
    document_service: Annotated[DocumentService, Depends(get_document_service)],
) -> ProgressResponse:
    try:
        return _build_progress_response(
            document_service.mark_learning_reviewed(document_id)
        )
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with id {document_id} was not found.",
        ) from error
    except DocumentStorageError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save learning progress.",
        ) from error


@app.put(
    "/documents/{document_id}/progress",
    response_model=ProgressResponse,
    status_code=status.HTTP_200_OK,
)
def update_document_progress(
    document_id: int,
    request: ProgressUpdateRequest,
    document_service: Annotated[DocumentService, Depends(get_document_service)],
) -> ProgressResponse:
    if request.mastered is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="mastered must be provided.",
        )
    try:
        return _build_progress_response(
            document_service.set_learning_mastered(
                document_id,
                mastered=request.mastered,
            )
        )
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with id {document_id} was not found.",
        ) from error
    except DocumentStorageError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update learning progress.",
        ) from error


@app.post(
    "/documents/{document_id}/retry",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    document_service: Annotated[DocumentService, Depends(get_document_service)],
    document_processor: Annotated[
        DocumentProcessor,
        Depends(get_document_processor),
    ],
) -> DocumentResponse:
    stored_path: Path | None = None
    try:
        existing_document = document_service.get_document(document_id)
        if existing_document.source_path:
            stored_path = resolve_stored_document_path(existing_document.source_path)
        document = document_service.retry_document(document_id)
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with id {document_id} was not found.",
        ) from error
    except DocumentStorageError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retry document processing.",
        ) from error
    except DocumentReadError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retry document processing.",
        ) from error
    except InvalidDocumentStoragePath as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored document path is invalid.",
        ) from error

    if stored_path is not None and get_process_uploads_in_api():
        background_tasks.add_task(
            document_processor,
            document.id,
            stored_path,
        )

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
        document = document_service.get_document(document_id)
        stored_path = (
            resolve_stored_document_path(document.source_path)
            if document.source_path
            else None
        )
        document_service.delete_document(document_id)
        if stored_path is not None:
            stored_path.unlink(missing_ok=True)
        logger.info(
            "document_deleted owner_id=%s document_id=%s filename=%s",
            document.owner_id,
            document.id,
            document.filename,
        )
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with id {document_id} was not found.",
        ) from error
    except DocumentReadError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not delete document.",
        ) from error
    except DocumentDeletionError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not delete document.",
        ) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)
