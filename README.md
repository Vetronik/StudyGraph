# StudyGraph

StudyGraph is a learning project that will grow step by step into a web
application for working with study material.

Current milestone:

- Read a PDF file from the command line
- Extract its text
- Print the extracted text to the terminal
- Upload a PDF through a minimal REST API
- Return basic PDF information as JSON
- Store processed documents in PostgreSQL
- Manage database schema changes with Alembic migrations
- Split extracted document text into reusable chunks for later search features
- Validate PDF uploads with configurable size and content limits
- Track document processing status and failed processing attempts
- Search stored document chunks through a dedicated API endpoint backed by
  PostgreSQL full text search
- Store page numbers for chunks so search and RAG context can cite source pages
- Use a minimal browser UI for uploading, browsing, searching, and deleting
  documents with selectable local owner context
- Build source-grounded retrieval context for future RAG features
- Scope document access by owner through an `X-StudyGraph-User` request header
- Keep document processing in a worker-ready service boundary instead of inside
  the API route
- Provide an embedding provider interface with a deterministic local provider
  for tests and future pgvector integration

No real authentication or AI answer generation are included yet.

## Requirements

- Python 3.11 or newer

## Setup

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the project in editable mode:

```powershell
python -m pip install -e .
```

To include test dependencies:

```powershell
python -m pip install -e ".[test]"
```

To include development tools such as Ruff:

```powershell
python -m pip install -e ".[test,dev]"
```

## Local Database

Start PostgreSQL with Docker Compose:

```powershell
docker compose up -d postgres
```

The Compose setup creates two databases:

- `studygraph` for local development
- `studygraph_test` for integration tests

Use these local connection strings:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://studygraph_user:studygraph_password@localhost:5432/studygraph"
$env:TEST_DATABASE_URL = "postgresql+psycopg://studygraph_user:studygraph_password@localhost:5432/studygraph_test"
```

## Usage

Run the command with the path to a PDF file:

```powershell
studygraph path\to\file.pdf
```

You can also run it as a Python module:

```powershell
python -m studygraph path\to\file.pdf
```

The extracted text will be printed to the terminal.

## API

StudyGraph stores successfully processed documents in PostgreSQL. Configure the
database connection with an environment variable:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@localhost:5432/studygraph"
```

Optional runtime limits can be configured through environment variables:

```powershell
$env:STUDYGRAPH_MAX_UPLOAD_BYTES = "10485760"
$env:STUDYGRAPH_MAX_DOCUMENT_PAGES = "500"
$env:STUDYGRAPH_MAX_DOCUMENT_CHARACTERS = "1000000"
$env:STUDYGRAPH_REQUIRE_USER_HEADER = "false"
$env:STUDYGRAPH_LOG_LEVEL = "INFO"
```

Run database migrations before starting the API:

```powershell
python -m alembic upgrade head
```

Start the local FastAPI server:

```powershell
python -m uvicorn studygraph.api:app --reload
```

Open the browser UI:

```text
http://127.0.0.1:8000/
```

Open the automatically generated API documentation:

```text
http://127.0.0.1:8000/docs
```

Use `GET /health` to check whether the API is running and whether the database
connection is configured.

Use `POST /documents` to upload one PDF file. StudyGraph validates the upload
size, PDF content type, and PDF file header before processing it. The response
contains the document ID, filename, file size, processing status, page count,
character count, creation time, and a short text preview.

All document endpoints are scoped by owner. For local development, requests
without a header use `local-user`. To simulate separate users before real
authentication exists, send an `X-StudyGraph-User` header:

```powershell
curl -H "X-StudyGraph-User: alice" http://127.0.0.1:8000/documents
```

Set `STUDYGRAPH_REQUIRE_USER_HEADER=true` to reject document requests that do
not include the owner header. Owner IDs may contain letters, numbers, dots,
underscores, hyphens, and `@`.

StudyGraph logs processing lifecycle events such as upload acceptance,
processing success, processing failure, and deletion. Logs include document IDs,
owners, filenames, and counts, but not extracted document text.

Use `GET /documents` to list stored documents. The endpoint supports
`limit`, `offset`, and `query` parameters for pagination and simple text search.

Use `GET /documents/{document_id}` to load metadata for a stored document.

Use `GET /documents/{document_id}/chunks` to load the stored text chunks for a
document.

Use `GET /search?query=...` to search stored document chunks. On PostgreSQL,
the endpoint uses full text search indexes for chunk text and document
filenames. The response contains matching chunk text, a compact snippet,
pagination metadata, and the source document ID, filename, and page number.

Use `POST /rag/context` with a JSON body such as
`{"query": "derivatives", "max_chunks": 5}` to build a source-grounded context
block from matching chunks. This endpoint prepares retrieval context for future
RAG usage, including document and page references, but it does not call an LLM
or generate an answer.

The codebase includes an embedding provider interface and a deterministic local
hash-based provider for tests and development. It is not intended to replace
real semantic embeddings. A future pgvector milestone can persist embeddings
for `document_chunks` once the provider, model name, and vector dimensions are
chosen.

Use `DELETE /documents/{document_id}` to remove a stored document.

Uploaded PDF files are stored below `STUDYGRAPH_DOCUMENT_STORAGE_DIR` so that
processing can be moved out of the API request. Pending documents can be
processed through the CLI:

```powershell
studygraph --process-pending
```

The API returns after the upload has been stored. Processing runs in a
background task with a separate worker service and database session, and the
document status can be read through `GET /documents/{document_id}`. The CLI
worker is useful for retries and for processing documents outside the API
process.

## Tests

Run the automated tests with:

```powershell
python -m pytest
```

Run linting with:

```powershell
python -m ruff check .
```

Repository integration tests require a dedicated PostgreSQL test database. Set
`TEST_DATABASE_URL` to run them:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@localhost:5432/studygraph_test"
python -m pytest -m postgresql
```
