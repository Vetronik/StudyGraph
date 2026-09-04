from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from studygraph.document_model import Collection, Document


class CollectionRepositoryError(Exception):
    """Raised when collection persistence fails."""


class CollectionNameConflictError(CollectionRepositoryError):
    """Raised when an owner already has a collection with the same name."""


class CollectionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, *, owner_id: str, name: str) -> Collection:
        collection = Collection(owner_id=owner_id, name=name)
        try:
            self._session.add(collection)
            self._session.commit()
            self._session.refresh(collection)
            return collection
        except IntegrityError as error:
            self._session.rollback()
            raise CollectionNameConflictError(
                "A collection with this name already exists."
            ) from error
        except SQLAlchemyError as error:
            self._session.rollback()
            raise CollectionRepositoryError("Could not create collection.") from error

    def list(self, *, owner_id: str) -> list[Collection]:
        statement = (
            select(Collection)
            .options(selectinload(Collection.documents))
            .where(Collection.owner_id == owner_id)
            .order_by(Collection.created_at, Collection.id)
        )
        try:
            return list(self._session.scalars(statement).all())
        except SQLAlchemyError as error:
            raise CollectionRepositoryError("Could not list collections.") from error

    def get(self, collection_id: int, *, owner_id: str) -> Collection | None:
        statement = (
            select(Collection)
            .options(selectinload(Collection.documents))
            .where(
                Collection.id == collection_id,
                Collection.owner_id == owner_id,
            )
        )
        try:
            return self._session.scalar(statement)
        except SQLAlchemyError as error:
            raise CollectionRepositoryError("Could not load collection.") from error

    def add_document(
        self,
        collection_id: int,
        document_id: int,
        *,
        owner_id: str,
    ) -> Collection | None:
        collection = self.get(collection_id, owner_id=owner_id)
        document = self._session.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.owner_id == owner_id,
            )
        )
        if collection is None or document is None:
            return None
        if document not in collection.documents:
            collection.documents.append(document)
        try:
            self._session.commit()
            self._session.refresh(collection)
            return self.get(collection_id, owner_id=owner_id)
        except SQLAlchemyError as error:
            self._session.rollback()
            raise CollectionRepositoryError(
                "Could not add document to collection."
            ) from error

    def remove_document(
        self,
        collection_id: int,
        document_id: int,
        *,
        owner_id: str,
    ) -> Collection | None:
        collection = self.get(collection_id, owner_id=owner_id)
        if collection is None:
            return None
        collection.documents = [
            document
            for document in collection.documents
            if document.id != document_id
        ]
        try:
            self._session.commit()
            return self.get(collection_id, owner_id=owner_id)
        except SQLAlchemyError as error:
            self._session.rollback()
            raise CollectionRepositoryError(
                "Could not remove document from collection."
            ) from error
