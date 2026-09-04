from datetime import UTC, datetime

from sqlalchemy import cast, func, or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, contains_eager

from studygraph.document_model import Document, DocumentChunk, LearningProgress
from studygraph.embedding_service import DeterministicHashEmbeddingProvider, Vector


class DocumentRepositoryError(Exception):
    """Raised when document persistence fails."""


class DocumentDuplicateError(DocumentRepositoryError):
    """Raised when a document hash already exists for an owner."""


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
            if isinstance(error, IntegrityError) and (
                "uq_documents_owner_content_hash" in str(error.orig)
            ):
                raise DocumentDuplicateError(
                    "Document already exists for this owner."
                ) from error
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

    def get_learning_progress(
        self,
        document_id: int,
        *,
        owner_id: str,
    ) -> LearningProgress | None:
        statement = select(LearningProgress).where(
            LearningProgress.document_id == document_id,
            LearningProgress.owner_id == owner_id,
        )
        try:
            return self._session.scalar(statement)
        except SQLAlchemyError as error:
            raise DocumentRepositoryError(
                "Could not load learning progress."
            ) from error

    def mark_learning_reviewed(
        self,
        document_id: int,
        *,
        owner_id: str,
    ) -> LearningProgress:
        statement = select(LearningProgress).where(
            LearningProgress.document_id == document_id,
            LearningProgress.owner_id == owner_id,
        ).with_for_update()
        try:
            progress = self._session.scalar(statement)
            if progress is None:
                progress = LearningProgress(
                    owner_id=owner_id,
                    document_id=document_id,
                    review_count=0,
                )
                self._session.add(progress)
            progress.review_count = (progress.review_count or 0) + 1
            progress.last_reviewed_at = datetime.now(UTC)
            self._session.commit()
            self._session.refresh(progress)
            return progress
        except SQLAlchemyError as error:
            self._session.rollback()
            raise DocumentRepositoryError(
                "Could not save learning progress."
            ) from error

    def set_learning_mastered(
        self,
        document_id: int,
        *,
        owner_id: str,
        mastered: bool,
    ) -> LearningProgress:
        progress = self.get_learning_progress(document_id, owner_id=owner_id)
        try:
            if progress is None:
                progress = LearningProgress(
                    owner_id=owner_id,
                    document_id=document_id,
                )
                self._session.add(progress)
            progress.mastered = mastered
            self._session.commit()
            self._session.refresh(progress)
            return progress
        except SQLAlchemyError as error:
            self._session.rollback()
            raise DocumentRepositoryError(
                "Could not update learning progress."
            ) from error

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

    def requeue_processing_documents(self) -> int:
        """Requeue jobs left in ``processing`` after a worker interruption."""
        try:
            result = self._session.execute(
                update(Document)
                .where(Document.status == "processing")
                .values(status="pending", processing_error=None)
            )
            self._session.commit()
            return result.rowcount
        except SQLAlchemyError as error:
            self._session.rollback()
            raise DocumentRepositoryError(
                "Could not requeue interrupted documents."
            ) from error

    def get_for_processing(self, document_id: int) -> Document | None:
        statement = select(Document).where(
            Document.id == document_id,
            Document.status.in_({"pending", "failed", "processing"}),
        )

        try:
            return self._session.scalar(statement)
        except SQLAlchemyError as error:
            raise DocumentRepositoryError(
                "Could not load document for processing."
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

    def semantic_search_chunks(
        self,
        *,
        owner_id: str,
        query: str,
        limit: int,
        offset: int,
    ) -> tuple[list[DocumentChunk], int]:
        query_embedding = DeterministicHashEmbeddingProvider().embed_texts([query])[0]
        distance = DocumentChunk.embedding.op("<=>")(
            cast(query_embedding.vector, Vector())
        )
        embedding_filter = DocumentChunk.embedding.is_not(None)
        total_statement = (
            select(func.count())
            .select_from(DocumentChunk)
            .join(DocumentChunk.document)
            .where(Document.owner_id == owner_id)
            .where(embedding_filter)
        )
        chunks_statement = (
            select(DocumentChunk)
            .join(DocumentChunk.document)
            .options(contains_eager(DocumentChunk.document))
            .where(Document.owner_id == owner_id)
            .where(embedding_filter)
            .order_by(distance, DocumentChunk.id)
            .limit(limit)
            .offset(offset)
        )

        try:
            total = self._session.scalar(total_statement) or 0
            chunks = list(self._session.scalars(chunks_statement).all())
        except SQLAlchemyError as error:
            raise DocumentRepositoryError(
                "Could not search document embeddings."
            ) from error

        return chunks, total
