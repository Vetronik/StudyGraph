from dataclasses import dataclass
from typing import Protocol

from studygraph.collection_repository import (
    CollectionNameConflictError,
    CollectionRepositoryError,
)
from studygraph.document_model import Collection


class CollectionNotFoundError(Exception):
    """Raised when a collection is not visible to the current owner."""


class CollectionValidationError(Exception):
    """Raised when collection input is invalid."""


class CollectionRepositoryProtocol(Protocol):
    def create(self, *, owner_id: str, name: str) -> Collection: ...

    def list(self, *, owner_id: str) -> list[Collection]: ...

    def get(self, collection_id: int, *, owner_id: str) -> Collection | None: ...

    def add_document(
        self,
        collection_id: int,
        document_id: int,
        *,
        owner_id: str,
    ) -> Collection | None: ...

    def remove_document(
        self,
        collection_id: int,
        document_id: int,
        *,
        owner_id: str,
    ) -> Collection | None: ...


@dataclass(frozen=True)
class CollectionList:
    collections: list[Collection]


class CollectionService:
    def __init__(
        self,
        repository: CollectionRepositoryProtocol,
        *,
        owner_id: str,
    ) -> None:
        self._repository = repository
        self._owner_id = owner_id

    def create(self, name: str) -> Collection:
        normalized_name = " ".join(name.split())
        if not normalized_name or len(normalized_name) > 120:
            raise CollectionValidationError(
                "Collection name must contain 1 to 120 characters."
            )
        try:
            return self._repository.create(
                owner_id=self._owner_id,
                name=normalized_name,
            )
        except CollectionNameConflictError:
            raise
        except CollectionRepositoryError as error:
            raise CollectionRepositoryError("Could not create collection.") from error

    def list(self) -> CollectionList:
        try:
            return CollectionList(self._repository.list(owner_id=self._owner_id))
        except CollectionRepositoryError as error:
            raise CollectionRepositoryError("Could not list collections.") from error

    def add_document(self, collection_id: int, document_id: int) -> Collection:
        try:
            collection = self._repository.add_document(
                collection_id,
                document_id,
                owner_id=self._owner_id,
            )
        except CollectionRepositoryError as error:
            raise CollectionRepositoryError(
                "Could not add document to collection."
            ) from error
        if collection is None:
            raise CollectionNotFoundError("Collection or document was not found.")
        return collection

    def remove_document(self, collection_id: int, document_id: int) -> Collection:
        try:
            collection = self._repository.remove_document(
                collection_id,
                document_id,
                owner_id=self._owner_id,
            )
        except CollectionRepositoryError as error:
            raise CollectionRepositoryError(
                "Could not remove document from collection."
            ) from error
        if collection is None:
            raise CollectionNotFoundError("Collection was not found.")
        return collection
