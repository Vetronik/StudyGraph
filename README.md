# StudyGraph

StudyGraph is a learning project that will grow step by step into a web
application for working with study material.

Current milestone:

- Read a PDF file from the command line
- Extract its text
- Print the extracted text to the terminal

No web backend, frontend, database, or AI features are included yet.

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

