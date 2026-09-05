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
- Browser interface for authentication, learning tools, and document collections
- Source-grounded offline question answering in the browser
- Separate liveness and PostgreSQL readiness checks
- Non-root API/worker containers with Docker image validation in CI
- Structured logging without logging extracted document text
- Unit tests, migration tests, and optional PostgreSQL integration tests

### Current limitations ⚠️

- The legacy `X-StudyGraph-User` header is only a local development identity mechanism.
- Authentication currently uses application-managed accounts and signed bearer tokens;
  a production identity provider is not integrated yet.
- The current embedding provider is deterministic and intended for tests only.
- The default answer provider is offline and extractive; an external LLM is optional
  and not integrated yet.
- OCR support exists as an opt-in fallback, but still needs production hardening and
  broader language coverage.

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
$env:POSTGRES_USER = "studygraph_production"
$env:POSTGRES_PASSWORD = "replace-with-a-url-safe-random-password"
$env:POSTGRES_DB = "studygraph_production"
docker compose -f docker-compose.yml -f docker-compose.secure.yml up --build -d
```

The secure override requires bearer tokens and disables the development owner
header. `STUDYGRAPH_AUTH_SECRET` must be explicitly set when bearer tokens are
required; the development fallback secret is rejected in that mode. The
secure override also requires explicit PostgreSQL credentials; use a URL-safe
password because it is embedded in `DATABASE_URL`. The
default compose command remains intentionally convenient for local single-user
development. The API and worker containers run as an unprivileged user.
The secure override also keeps PostgreSQL private to the Docker network.
It restricts accepted HTTP `Host` headers to `localhost` and `127.0.0.1` by
default; set `STUDYGRAPH_ALLOWED_HOSTS` when deploying behind a real domain.
Dependency update pull requests are configured through Dependabot for Python
packages and GitHub Actions.

The current application processes an upload as a background task in the API
container. The separate CLI worker remains available for recovery and manual
processing with `studygraph --process-pending`.

For the secure Docker deployment, `STUDYGRAPH_PROCESS_UPLOADS_IN_API=false`
keeps extraction in the dedicated worker. Local development defaults to `true`
for convenience.

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
| `GET` | `/documents/{id}/flashcards` | Generate source-referenced flashcards |
| `GET` | `/documents/{id}/progress` | Read learning progress |
| `POST` | `/documents/{id}/progress/review` | Count a review session |
| `PUT` | `/documents/{id}/progress` | Mark a document mastered or unmastered |
| `POST` | `/collections` | Create a document collection |
| `GET` | `/collections` | List collections for the current owner |
| `POST` | `/collections/{id}/documents` | Add a document to a collection |
| `DELETE` | `/collections/{id}/documents/{document_id}` | Remove a document from a collection |
| `POST` | `/documents/{id}/retry` | Queue failed document processing again |
| `POST` | `/rag/context` | Build source-grounded retrieval context |
| `POST` | `/ask` | Return an offline source-cited answer |
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

## Completed milestones and next steps 🗺️

The worker, recovery, OCR fallback, hybrid search, status UI, authentication,
local summaries, quizzes, persistent learning progress, and the laptop Docker
stack are implemented. Embeddings are configurable through
`STUDYGRAPH_EMBEDDING_PROVIDER`: `deterministic` is the zero-configuration
local default, while `openai-compatible` uses the configured API URL, model,
and key. The database schema currently uses 64-dimensional vectors.

The local `/ask` endpoint provides a source-cited offline fallback behind an
`AnswerProviderProtocol`. The next steps are ordered by risk and user value:

1. Stabilize the current product: make background processing observable and keep
   README/configuration aligned as the deployment evolves. API coverage for
   collections and authentication is now in place.
2. Finish the study workspace: filter search and learning actions by collection,
   improve loading/empty/error states, and add a small responsive UI test smoke path.
3. Add production-ready AI answers: implement a provider adapter with explicit
   privacy, timeout, token/cost, and source-grounding controls; keep offline mode as
   the safe default.
4. Harden operations: secure cookie/token handling, rate limits, upload isolation,
   health checks, backups, and documented deployment configuration.
5. Improve ingestion quality: OCR language configuration, extraction diagnostics,
   duplicate handling, and larger-document processing outside the API process.
6. Add learning depth only after the foundation is stable: spaced repetition,
   progress analytics, and topic/knowledge-graph views based on real usage data.

## Contributing 🤝

StudyGraph is developed in small milestones. New functionality should include
focused tests, use environment-based configuration, and preserve the layered
`API -> Service -> Repository -> Database` design.

Please do not commit passwords, API keys, `.env` files, private documents, or
other credentials.
