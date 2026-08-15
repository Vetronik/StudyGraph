from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from studygraph.document_model import Document


class DocumentRepositoryError(Exception):
    """Raised when document persistence fails."""


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, document: Document) -> Document:
        try:
            self._session.add(document)
            self._session.commit()
            self._session.refresh(document)
        except SQLAlchemyError as error:
            self._session.rollback()
            raise DocumentRepositoryError("Could not save document.") from error

        return document

    def get_by_id(self, document_id: int) -> Document | None:
        return self._session.get(Document, document_id)
