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
    assert "CREATE TABLE documents" in result.stdout
    assert "extracted_text" in result.stdout
    assert "CREATE TABLE document_chunks" in result.stdout
    assert "FOREIGN KEY(document_id) REFERENCES documents" in result.stdout
