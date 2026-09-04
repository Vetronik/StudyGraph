import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from studygraph.document_model import Document, DocumentChunk

SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+")
WORD_PATTERN = re.compile(r"[A-Za-zÄÖÜäöüß]{3,}")


@dataclass(frozen=True)
class SummarySource:
    chunk_id: int
    chunk_position: int
    page_number: int
    text: str


@dataclass(frozen=True)
class DocumentSummary:
    document_id: int
    filename: str
    summary: str
    sources: list[SummarySource]


class DocumentContentProtocol(Protocol):
    def get_document(self, document_id: int) -> Document: ...

    def list_document_chunks(self, document_id: int): ...


class ExtractiveSummaryService:
    """Create a local summary while preserving the source chunk for each sentence."""

    def __init__(self, document_service: DocumentContentProtocol) -> None:
        self._document_service = document_service

    def summarize(self, *, document_id: int, max_sentences: int) -> DocumentSummary:
        document = self._document_service.get_document(document_id)
        chunk_list = self._document_service.list_document_chunks(document_id)
        candidates = self._build_candidates(chunk_list.chunks)
        if not candidates:
            return DocumentSummary(
                document.id,
                document.filename,
                document.extracted_text,
                [],
            )

        word_frequency = Counter(
            word.lower()
            for candidate, _chunk in candidates
            for word in WORD_PATTERN.findall(candidate)
        )
        ranked = sorted(
            enumerate(candidates),
            key=lambda item: (
                -self._score_sentence(item[1][0], word_frequency, item[0]),
                item[0],
            ),
        )[:max_sentences]
        ranked.sort(key=lambda item: item[0])
        summary_sentences = [candidate for _index, (candidate, _chunk) in ranked]
        sources = []
        for _index, (sentence, chunk) in ranked:
            sources.append(
                SummarySource(
                    chunk_id=chunk.id,
                    chunk_position=chunk.position,
                    page_number=chunk.page_number,
                    text=sentence,
                )
            )
        return DocumentSummary(
            document_id=document.id,
            filename=document.filename,
            summary=" ".join(summary_sentences),
            sources=sources,
        )

    def _build_candidates(
        self,
        chunks: list[DocumentChunk],
    ) -> list[tuple[str, DocumentChunk]]:
        candidates: list[tuple[str, DocumentChunk]] = []
        for chunk in chunks:
            for sentence in SENTENCE_PATTERN.split(chunk.text):
                normalized = " ".join(sentence.split())
                if len(normalized) >= 30:
                    candidates.append((normalized, chunk))
        return candidates

    def _score_sentence(
        self,
        sentence: str,
        word_frequency: Counter[str],
        position: int,
    ) -> float:
        words = WORD_PATTERN.findall(sentence.lower())
        frequency_score = sum(word_frequency[word] for word in words)
        return frequency_score / max(len(words), 1) + 1 / (position + 1)
