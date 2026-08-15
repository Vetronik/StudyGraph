import os
import subprocess
import sys


def test_alembic_initial_migration_generates_documents_table_sql() -> None:
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
