import os
import subprocess
import sys


def test_alembic_migrations_generate_document_schema_sql() -> None:
    env = {
        **os.environ,
        "DATABASE_URL": (
            "postgresql+psycopg://studygraph_user:password"
            "@localhost:5432/studygraph_test"
        ),
    }

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "CREATE TABLE users" in result.stdout
    assert "password_hash" in result.stdout
    assert "UNIQUE (username)" in result.stdout
    assert "CREATE TABLE documents" in result.stdout
    assert "extracted_text" in result.stdout
    assert "file_size_bytes" in result.stdout
    assert "owner_id" in result.stdout
    assert "processing_error" in result.stdout
    assert "processing_attempts" in result.stdout
    assert "content_hash" in result.stdout
    assert "uq_documents_owner_content_hash" in result.stdout
    assert "status" in result.stdout
    assert "ix_documents_owner_id" in result.stdout
    assert "ix_document_chunks_text_fts" in result.stdout
    assert "ix_documents_filename_fts" in result.stdout
    assert "USING gin" in result.stdout
    assert "CREATE TABLE document_chunks" in result.stdout
    assert "page_number" in result.stdout
    assert "FOREIGN KEY(document_id) REFERENCES documents" in result.stdout
