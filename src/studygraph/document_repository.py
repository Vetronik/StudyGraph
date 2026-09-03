from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, contains_eager

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

    def get_by_id(self, document_id: int, *, owner_id: str) -> Document | None:
        statement = select(Document).where(
            Document.id == document_id,
            Document.owner_id == owner_id,
        )

        try:
            return self._session.scalar(statement)
        except SQLAlchemyError as error:
            raise DocumentRepositoryError("Could not load document.") from error

    def list_pending(self, *, limit: int = 20) -> list[Document]:
        statement = (
            select(Document)
            .where(Document.status.in_({"pending", "failed", "processing"}))
            .order_by(Document.created_at, Document.id)
            .limit(limit)
        )

        try:
            return list(self._session.scalars(statement).all())
        except SQLAlchemyError as error:
            raise DocumentRepositoryError(
                "Could not load pending documents."
            ) from error

    def claim_for_processing(
        self,
        document_id: int,
        *,
        owner_id: str,
    ) -> Document | None:
        statement = (
            select(Document)
            .where(
                Document.id == document_id,
                Document.owner_id == owner_id,
                Document.status.in_({"pending", "failed", "processing"}),
            )
            .with_for_update()
        )

        try:
            document = self._session.scalar(statement)
            if document is None or document.status == "processing":
                return None

            document.status = "processing"
            document.processing_attempts = (document.processing_attempts or 0) + 1
            document.processing_error = None
            self._session.commit()
            self._session.refresh(document)
            return document
        except SQLAlchemyError as error:
            self._session.rollback()
            raise DocumentRepositoryError(
                "Could not claim document for processing."
            ) from error

    def list_chunks(self, document_id: int, *, owner_id: str) -> list[DocumentChunk]:
        statement = (
            select(DocumentChunk)
            .join(DocumentChunk.document)
            .where(DocumentChunk.document_id == document_id)
            .where(Document.owner_id == owner_id)
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
        owner_id: str,
        limit: int,
        offset: int,
        query: str | None = None,
    ) -> tuple[list[Document], int]:
        total_statement = (
            select(func.count())
            .select_from(Document)
            .where(Document.owner_id == owner_id)
        )
        documents_statement = (
            select(Document)
            .where(Document.owner_id == owner_id)
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

    def search_chunks(
        self,
        *,
        owner_id: str,
        query: str,
        limit: int,
        offset: int,
    ) -> tuple[list[DocumentChunk], int]:
        search_query = func.websearch_to_tsquery("simple", query)
        chunk_search_vector = func.to_tsvector("simple", DocumentChunk.text)
        filename_search_vector = func.to_tsvector("simple", Document.filename)
        search_filter = or_(
            chunk_search_vector.op("@@")(search_query),
            filename_search_vector.op("@@")(search_query),
        )
        rank = func.ts_rank_cd(
            chunk_search_vector,
            search_query,
        )
        total_statement = (
            select(func.count())
            .select_from(DocumentChunk)
            .join(DocumentChunk.document)
            .where(Document.owner_id == owner_id)
            .where(search_filter)
        )
        chunks_statement = (
            select(DocumentChunk)
            .join(DocumentChunk.document)
            .options(contains_eager(DocumentChunk.document))
            .where(Document.owner_id == owner_id)
            .where(search_filter)
            .order_by(
                rank.desc(),
                Document.created_at.desc(),
                Document.id.desc(),
                DocumentChunk.position,
            )
            .limit(limit)
            .offset(offset)
        )

        try:
            total = self._session.scalar(total_statement) or 0
            chunks = list(self._session.scalars(chunks_statement).all())
        except SQLAlchemyError as error:
            raise DocumentRepositoryError("Could not search chunks.") from error

        return chunks, total
