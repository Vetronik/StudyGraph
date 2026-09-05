from pathlib import Path

import pytest

from studygraph.document_storage import (
    InvalidDocumentStoragePath,
    resolve_stored_document_path,
)


def test_resolve_stored_document_path_accepts_file_in_storage_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "documents"
    monkeypatch.setenv("STUDYGRAPH_DOCUMENT_STORAGE_DIR", str(storage_root))

    result = resolve_stored_document_path(str(storage_root / "upload.pdf"))

    assert result == (storage_root / "upload.pdf").resolve()


def test_resolve_stored_document_path_rejects_path_escape(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "documents"
    monkeypatch.setenv("STUDYGRAPH_DOCUMENT_STORAGE_DIR", str(storage_root))

    with pytest.raises(InvalidDocumentStoragePath):
        resolve_stored_document_path(str(tmp_path / "outside.pdf"))
