from pathlib import Path

from studygraph.config import get_document_storage_dir


class InvalidDocumentStoragePath(ValueError):
    """Raised when a stored document path escapes the configured storage root."""


def resolve_stored_document_path(source_path: str) -> Path:
    storage_root = Path(get_document_storage_dir()).resolve()
    candidate = Path(source_path).resolve()

    try:
        candidate.relative_to(storage_root)
    except ValueError as error:
        raise InvalidDocumentStoragePath(
            "Stored document path is outside the configured storage directory."
        ) from error

    return candidate
