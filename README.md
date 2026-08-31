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
- Search stored document chunks through a dedicated API endpoint
- Use a minimal browser UI for uploading, browsing, searching, and deleting
  documents

No user accounts, Docker setup, or AI features are included yet.

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

Use `GET /documents` to list stored documents. The endpoint supports
`limit`, `offset`, and `query` parameters for pagination and simple text search.

Use `GET /documents/{document_id}` to load metadata for a stored document.

Use `GET /documents/{document_id}/chunks` to load the stored text chunks for a
document.

Use `GET /search?query=...` to search stored document chunks. The response
contains matching chunk text, a compact snippet, pagination metadata, and the
source document ID and filename.

Use `DELETE /documents/{document_id}` to remove a stored document.

## Tests

Run the automated tests with:

```powershell
python -m pytest
```

Repository integration tests require a dedicated PostgreSQL test database. Set
`TEST_DATABASE_URL` to run them:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@localhost:5432/studygraph_test"
python -m pytest -m postgresql
```
