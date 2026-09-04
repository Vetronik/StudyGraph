FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic

RUN python -m pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STUDYGRAPH_DOCUMENT_STORAGE_DIR=/app/data/documents

RUN mkdir -p /app/data/documents

EXPOSE 8000

CMD ["sh", "-c", "python -m alembic upgrade head && python -m uvicorn studygraph.api:app --host 0.0.0.0 --port 8000"]
