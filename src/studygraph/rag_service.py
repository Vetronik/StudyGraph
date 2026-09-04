import re
from dataclasses import dataclass
from typing import Protocol

from studygraph.retrieval_service import (
    RetrievalContext,
    RetrievalService,
    RetrievalSource,
)


class AnswerProviderProtocol(Protocol):
    def answer(self, *, query: str, context: RetrievalContext) -> str: ...


@dataclass(frozen=True)
class RAGAnswer:
    query: str
    answer: str
    sources: list[RetrievalSource]


class LocalExtractiveAnswerProvider:
    """Offline answer provider that always keeps source citations visible."""

    def answer(self, *, query: str, context: RetrievalContext) -> str:
        if not context.sources:
            return "No relevant information was found in the uploaded documents."

        candidates: list[str] = []
        for source in context.sources:
            sentences = re.split(r"(?<=[.!?])\s+", source.text.strip())
            if sentences and sentences[0]:
                candidates.append(f"{sentences[0]} [source {source.source_number}]")
            if len(candidates) >= 3:
                break

        if not candidates:
            return (
                "Relevant source material was found, but it contains no readable "
                "sentences."
            )
        return " ".join(candidates)


class RAGService:
    def __init__(
        self,
        retrieval_service: RetrievalService,
        answer_provider: AnswerProviderProtocol | None = None,
    ) -> None:
        self._retrieval_service = retrieval_service
        self._answer_provider = answer_provider or LocalExtractiveAnswerProvider()

    def answer(self, *, query: str, max_chunks: int) -> RAGAnswer:
        context = self._retrieval_service.build_context(
            query=query,
            max_chunks=max_chunks,
        )
        return RAGAnswer(
            query=context.query,
            answer=self._answer_provider.answer(query=query, context=context),
            sources=context.sources,
        )
