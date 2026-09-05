from pathlib import Path

import pytest

from studygraph.api import SavedUpload, _persist_upload
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


def test_persist_upload_writes_atomically_to_storage_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "documents"
    source_path = tmp_path / "temporary.pdf"
    source_path.write_bytes(b"%PDF-1.4\ncontent")
    monkeypatch.setenv("STUDYGRAPH_DOCUMENT_STORAGE_DIR", str(storage_root))

    persistent_path = _persist_upload(
        SavedUpload(
            path=source_path,
            size_bytes=source_path.stat().st_size,
            content_hash="hash",
        )
    )

    assert persistent_path.parent == storage_root.resolve()
    assert persistent_path.read_bytes() == b"%PDF-1.4\ncontent"
    assert not source_path.exists()
    assert list(storage_root.glob(".upload-*.tmp")) == []
