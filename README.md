# StudyGraph

StudyGraph is a learning project that will grow step by step into a web
application for working with study material.

Current milestone:

- Read a PDF file from the command line
- Extract its text
- Print the extracted text to the terminal
- Upload a PDF through a minimal REST API
- Return basic PDF information as JSON

No frontend, database, user accounts, Docker setup, or AI features are included yet.

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

Start the local FastAPI server:

```powershell
python -m uvicorn studygraph.api:app --reload
```

Open the automatically generated API documentation:

```text
http://127.0.0.1:8000/docs
```

Use `POST /documents` to upload one PDF file. The response contains the
filename, page count, character count, and a short text preview.

## Tests

Run the automated tests with:

```powershell
python -m pytest
```
