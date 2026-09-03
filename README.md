# StudyGraph 📚

StudyGraph is an AI-assisted learning platform for turning university PDFs
into searchable, source-grounded study material.

The project is being developed incrementally with a focus on clean backend
architecture, reproducible tests, and transparent document sources. The long
term goal is to support semantic search, RAG answers, quizzes, flashcards, and
learning progress in one workspace. 🚀

## Project Status 🛠️

### Already implemented ✅

- PDF extraction through a CLI and REST API
- Upload validation for file type, PDF header, size, pages, and text length
- PostgreSQL persistence with SQLAlchemy
- Versioned database migrations with Alembic
- Page-aware text chunking with overlap
- PostgreSQL full-text search with pagination and snippets
- Source-grounded retrieval context with document and page references
- Persistent PDF storage with configurable storage directory
- Asynchronous upload processing with `pending`, `processing`, `processed`, and `failed` states
- Database locking to prevent duplicate processing
- Retry discovery for failed or interrupted processing jobs
- Minimal browser interface for upload, search, inspection, and deletion
- Structured logging without logging extracted document text
- Unit tests, migration tests, and optional PostgreSQL integration tests

### Current limitations ⚠️

- The `X-StudyGraph-User` header is only a local development identity mechanism.
- There is no real login, password authentication, session, or JWT yet.
- The current embedding provider is deterministic and intended for tests only.
- No LLM is called and no AI-generated answer is produced yet.
- OCR for scanned PDFs is not implemented yet.

## Architecture 🧱

The backend follows a simple layered flow:

```text
HTTP API
  -> Service
    -> Repository
      -> PostgreSQL
```

Document processing is kept independent from the API:

```text
Upload
  -> persistent PDF storage
    -> pending document
      -> worker
        -> PDF extraction
          -> page-aware chunks
            -> processed or failed document
```

The main source code is located in [`src/studygraph`](src/studygraph). Tests
are located in [`tests`](tests), and schema migrations are in
[`alembic/versions`](alembic/versions).

## Requirements 📦

- Python 3.11 or newer
- Docker Desktop for local PostgreSQL and integration tests

## Installation 🚀

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the project:

```powershell
python -m pip install -e .
```

Install test and development dependencies:

```powershell
python -m pip install -e ".[test,dev]"
```

## Local Database 🐘

Start PostgreSQL with Docker Compose:

```powershell
docker compose up -d postgres
```

The Compose setup provides two databases:

- `studygraph` for local development
- `studygraph_test` for integration tests

Configure the connection strings:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://studygraph_user:studygraph_password@localhost:5432/studygraph"
$env:TEST_DATABASE_URL = "postgresql+psycopg://studygraph_user:studygraph_password@localhost:5432/studygraph_test"
```

Apply all migrations:

```powershell
python -m alembic upgrade head
```

## Running the Application ▶️

Start the API:

```powershell
python -m uvicorn studygraph.api:app --reload
```

Open the application at <http://127.0.0.1:8000/>.

Useful endpoints:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Check API and database configuration |
| `POST` | `/documents` | Validate and queue a PDF upload |
| `GET` | `/documents` | List documents for the current development owner |
| `GET` | `/documents/{id}` | Read document status and metadata |
| `GET` | `/documents/{id}/chunks` | Read page-aware chunks |
| `GET` | `/search?query=...` | Search document chunks |
| `POST` | `/rag/context` | Build source-grounded retrieval context |
| `DELETE` | `/documents/{id}` | Delete a document and its stored PDF |

Interactive API documentation is available at
<http://127.0.0.1:8000/docs>. 🔎

Uploads return `202 Accepted`. The response contains a document with status
`pending`; processing then runs in the worker and can be checked through
`GET /documents/{id}`.

## CLI and Worker 🧰

Extract text directly from a local PDF:

```powershell
studygraph path\to\file.pdf
```

Process pending, failed, or interrupted documents outside the API process:

```powershell
studygraph --process-pending
```

PDF files are stored below `STUDYGRAPH_DOCUMENT_STORAGE_DIR`. The default is
`data/documents`.

## Configuration ⚙️

Copy [`.env.example`](.env.example) to your local environment setup and never
commit real credentials. The application reads configuration from environment
variables:

```powershell
$env:STUDYGRAPH_DOCUMENT_STORAGE_DIR = "data/documents"
$env:STUDYGRAPH_MAX_UPLOAD_BYTES = "10485760"
$env:STUDYGRAPH_MAX_DOCUMENT_PAGES = "500"
$env:STUDYGRAPH_MAX_DOCUMENT_CHARACTERS = "1000000"
$env:STUDYGRAPH_REQUIRE_USER_HEADER = "false"
$env:STUDYGRAPH_LOG_LEVEL = "INFO"
```

For local development, requests without an owner header use `local-user`.
Different development owners can be simulated with:

```powershell
curl -H "X-StudyGraph-User: alice" http://127.0.0.1:8000/documents
```

This mechanism must be replaced before deploying a multi-user version. 🔐

## Testing 🧪

Run the complete test suite:

```powershell
python -m pytest
```

Run linting:

```powershell
python -m ruff check .
```

Run PostgreSQL integration tests explicitly:

```powershell
python -m pytest -m postgresql
```

The integration tests require `TEST_DATABASE_URL` and a dedicated test
database. They must never run against personal or production data.

## Roadmap 🗺️

1. Replace the development owner header with real authentication and JWT-based user identity.
2. Add retry limits, worker observability, and stronger recovery for interrupted jobs.
3. Add document hashes, duplicate detection, and OCR support.
4. Persist real embeddings and add `pgvector` semantic search.
5. Combine full-text and semantic retrieval into hybrid search.
6. Add an LLM provider interface for cited RAG answers.
7. Build quizzes, flashcards, collections, and learning progress tracking.

## Contributing 🤝

StudyGraph is developed in small milestones. New functionality should include
focused tests, use environment-based configuration, and preserve the layered
`API -> Service -> Repository -> Database` design.

Please do not commit passwords, API keys, `.env` files, private documents, or
other credentials.
