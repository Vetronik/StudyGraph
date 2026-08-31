from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from studygraph.document_model import Document, DocumentChunk


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

    def update(self, document: Document) -> Document:
        try:
            self._session.commit()
            self._session.refresh(document)
        except SQLAlchemyError as error:
            self._session.rollback()
            raise DocumentRepositoryError("Could not update document.") from error

        return document

    def delete(self, document: Document) -> None:
        try:
            self._session.delete(document)
            self._session.commit()
        except SQLAlchemyError as error:
            self._session.rollback()
            raise DocumentRepositoryError("Could not delete document.") from error

    def get_by_id(self, document_id: int) -> Document | None:
        return self._session.get(Document, document_id)

    def list_chunks(self, document_id: int) -> list[DocumentChunk]:
        statement = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.position)
        )

        try:
            return list(self._session.scalars(statement).all())
        except SQLAlchemyError as error:
            raise DocumentRepositoryError(
                "Could not list document chunks."
            ) from error

    def list_documents(
        self,
        *,
        limit: int,
        offset: int,
        query: str | None = None,
    ) -> tuple[list[Document], int]:
        total_statement = select(func.count()).select_from(Document)
        documents_statement = (
            select(Document)
            .order_by(Document.created_at.desc(), Document.id.desc())
            .limit(limit)
            .offset(offset)
        )

        if query:
            search_pattern = f"%{query}%"
            search_filter = or_(
                Document.filename.ilike(search_pattern),
                Document.extracted_text.ilike(search_pattern),
            )
            total_statement = total_statement.where(search_filter)
            documents_statement = documents_statement.where(search_filter)

        try:
            total = self._session.scalar(total_statement) or 0
            documents = list(self._session.scalars(documents_statement).all())
        except SQLAlchemyError as error:
            raise DocumentRepositoryError("Could not list documents.") from error

        return documents, total
