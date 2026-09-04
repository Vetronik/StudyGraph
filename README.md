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
- Persistent chunk embeddings and pgvector semantic search
- Persistent PDF storage with configurable storage directory
- Asynchronous upload processing with `pending`, `processing`, `processed`, and `failed` states
- Database locking to prevent duplicate processing
- Retry discovery for failed or interrupted processing jobs
- Minimal browser interface for upload, search, inspection, and deletion
- Structured logging without logging extracted document text
- Unit tests, migration tests, and optional PostgreSQL integration tests

### Current limitations ⚠️

- The legacy `X-StudyGraph-User` header is only a local development identity mechanism.
- Authentication currently uses application-managed accounts and signed bearer tokens;
  a production identity provider is not integrated yet.
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

### Recommended: run the complete local stack with Docker

This is the easiest way to use StudyGraph on a laptop. Docker starts
PostgreSQL and the API; database migrations run automatically before the API
starts. Uploaded PDFs are kept in `data/documents` on the host.

Copy the example configuration once:

```powershell
Copy-Item .env.example .env
```

Build and start the application:

```powershell
docker compose up --build
```

Open <http://127.0.0.1:8000/> for the web interface or
<http://127.0.0.1:8000/docs> for the API documentation. Stop the stack with
`Ctrl+C`; run `docker compose down` later to remove the containers while
keeping the database volume.

To run it in the background, use `docker compose up --build -d` and inspect
the logs with `docker compose logs -f api`.

For a deployment that requires bearer authentication, set a strong secret and
use the secure override:

```powershell
$env:STUDYGRAPH_AUTH_SECRET = "replace-with-a-random-secret-at-least-32-characters"
docker compose -f docker-compose.yml -f docker-compose.secure.yml up --build -d
```

The secure override requires bearer tokens and disables the development owner
header. The default compose command remains intentionally convenient for local
single-user development.

The current application processes an upload as a background task in the API
container. The separate CLI worker remains available for recovery and manual
processing with `studygraph --process-pending`.

The web interface refreshes the document statuses automatically while the
worker processes uploads. A failed document can be queued again through the
`POST /documents/{id}/retry` endpoint.

Start the API:

```powershell
python -m uvicorn studygraph.api:app --reload
```

Open the application at <http://127.0.0.1:8000/>.

Useful endpoints:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Check API and database configuration |
| `POST` | `/auth/register` | Register a user account |
| `POST` | `/auth/login` | Obtain a bearer token |
| `POST` | `/documents` | Validate and queue a PDF upload |
| `GET` | `/documents` | List documents for the current development owner |
| `GET` | `/documents/{id}` | Read document status and metadata |
| `GET` | `/documents/{id}/chunks` | Read page-aware chunks |
| `GET` | `/search?query=...` | Full-text search over document chunks |
| `GET` | `/semantic-search?query=...` | Semantic search over document chunks |
| `GET` | `/hybrid-search?query=...` | Combined full-text and semantic search |
| `GET` | `/documents/{id}/summary` | Create a source-referenced local summary |
| `GET` | `/documents/{id}/quiz` | Generate local source-referenced cloze questions |
| `GET` | `/documents/{id}/progress` | Read learning progress |
| `POST` | `/documents/{id}/progress/review` | Count a review session |
| `PUT` | `/documents/{id}/progress` | Mark a document mastered or unmastered |
| `POST` | `/documents/{id}/retry` | Queue failed document processing again |
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
$env:STUDYGRAPH_AUTH_SECRET = "replace-this-with-a-long-random-secret"
$env:STUDYGRAPH_REQUIRE_AUTH_TOKEN = "false"
$env:STUDYGRAPH_MAX_UPLOAD_BYTES = "10485760"
$env:STUDYGRAPH_MAX_DOCUMENT_PAGES = "500"
$env:STUDYGRAPH_MAX_DOCUMENT_CHARACTERS = "1000000"
$env:STUDYGRAPH_MAX_PROCESSING_ATTEMPTS = "3"
$env:STUDYGRAPH_REQUIRE_USER_HEADER = "false"
$env:STUDYGRAPH_LOG_LEVEL = "INFO"
```

For local development, requests without a bearer token use `local-user`.
After login, send the returned token as a bearer token:

```powershell
curl -H "Authorization: Bearer <access-token>" http://127.0.0.1:8000/documents
```

The web interface also provides login, registration, and logout controls. To
require bearer authentication in a local deployment, set
`STUDYGRAPH_REQUIRE_AUTH_TOKEN=true` in `.env` and use the account controls.

Register and log in with the API:

```powershell
curl -X POST http://127.0.0.1:8000/auth/register `
  -H "Content-Type: application/json" `
  -d '{"username":"alice","password":"a-secure-password"}'

curl -X POST http://127.0.0.1:8000/auth/login `
  -H "Content-Type: application/json" `
  -d '{"username":"alice","password":"a-secure-password"}'
```

Until `STUDYGRAPH_REQUIRE_AUTH_TOKEN=true` is enabled, different development
owners can still be simulated with:

```powershell
curl -H "X-StudyGraph-User: alice" http://127.0.0.1:8000/documents
```

Set `STUDYGRAPH_REQUIRE_AUTH_TOKEN=true` before deploying a multi-user version.
The development owner header is then rejected when no bearer token is present.
🔐

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

## Recommended next milestones 🗺️

1. Add a real continuously running worker and job observability so processing
   survives API restarts reliably.
2. Add OCR support for scanned PDFs and tests for representative documents.
3. Combine full-text and semantic retrieval into hybrid search and evaluate it
   with a small fixed search dataset.
4. Replace the deterministic embedding provider with a configurable production
   provider.
5. Add an LLM provider interface for cited RAG answers, with token/cost and
   privacy controls.
6. Build quizzes, flashcards, collections, and learning progress tracking.
7. Harden authentication and deployment settings before exposing the service
   beyond the laptop.

## Contributing 🤝

StudyGraph is developed in small milestones. New functionality should include
focused tests, use environment-based configuration, and preserve the layered
`API -> Service -> Repository -> Database` design.

Please do not commit passwords, API keys, `.env` files, private documents, or
other credentials.
