from dataclasses import dataclass
from typing import Protocol

from studygraph.document_model import DocumentChunk
from studygraph.document_service import (
    DocumentReadError,
    DocumentSearchQueryError,
    DocumentSearchResultList,
)


@dataclass(frozen=True)
class RetrievalSource:
    source_number: int
    document_id: int
    document_filename: str
    chunk_id: int
    chunk_position: int
    page_number: int
    text: str


@dataclass(frozen=True)
class RetrievalContext:
    query: str
    sources: list[RetrievalSource]
    context: str


class ChunkSearchProtocol(Protocol):
    def search_chunks(
        self,
        *,
        query: str,
        limit: int,
        offset: int,
    ) -> DocumentSearchResultList: ...


class RetrievalService:
    def __init__(self, chunk_search: ChunkSearchProtocol) -> None:
        self._chunk_search = chunk_search

    def build_context(self, *, query: str, max_chunks: int) -> RetrievalContext:
        search_results = self._chunk_search.search_chunks(
            query=query,
            limit=max_chunks,
            offset=0,
        )
        sources = [
            self._build_source(source_number, chunk)
            for source_number, chunk in enumerate(search_results.chunks, start=1)
        ]

        return RetrievalContext(
            query=search_results.query,
            sources=sources,
            context=self._build_context_text(sources),
        )

    def _build_source(
        self,
        source_number: int,
        chunk: DocumentChunk,
    ) -> RetrievalSource:
        return RetrievalSource(
            source_number=source_number,
            document_id=chunk.document_id,
            document_filename=chunk.document.filename,
            chunk_id=chunk.id,
            chunk_position=chunk.position,
            page_number=chunk.page_number,
            text=chunk.text,
        )

    def _build_context_text(self, sources: list[RetrievalSource]) -> str:
        return "\n\n".join(
            (
                f"[source {source.source_number}] "
                f"{source.document_filename}, page {source.page_number}, "
                f"chunk {source.chunk_position + 1}\n"
                f"{source.text}"
            )
            for source in sources
        )


__all__ = [
    "DocumentReadError",
    "DocumentSearchQueryError",
    "RetrievalContext",
    "RetrievalService",
    "RetrievalSource",
]
