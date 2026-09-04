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


@dataclass(frozen=True)
class QuizQuestion:
    question_type: str
    question: str
    answer: str
    options: list[str]
    chunk_id: int
    chunk_position: int
    page_number: int


@dataclass(frozen=True)
class DocumentQuiz:
    document_id: int
    filename: str
    questions: list[QuizQuestion]


@dataclass(frozen=True)
class Flashcard:
    front: str
    back: str
    chunk_id: int
    chunk_position: int
    page_number: int


@dataclass(frozen=True)
class DocumentFlashcards:
    document_id: int
    filename: str
    cards: list[Flashcard]


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


class LocalQuizService:
    """Generate deterministic cloze and multiple-choice questions."""

    def __init__(self, document_service: DocumentContentProtocol) -> None:
        self._document_service = document_service

    def generate(self, *, document_id: int, count: int) -> DocumentQuiz:
        document = self._document_service.get_document(document_id)
        chunk_list = self._document_service.list_document_chunks(document_id)
        questions: list[QuizQuestion] = []
        answer_pool = self._collect_answers(chunk_list.chunks)
        for chunk in chunk_list.chunks:
            for sentence in SENTENCE_PATTERN.split(chunk.text):
                words = WORD_PATTERN.findall(sentence)
                if not words:
                    continue
                answer = max(words, key=len)
                question = sentence.replace(answer, "____", 1).strip()
                if question == sentence.strip():
                    continue
                question_type = (
                    "cloze" if len(questions) % 2 == 0 else "multiple_choice"
                )
                options = (
                    self._build_options(answer, answer_pool)
                    if question_type == "multiple_choice"
                    else []
                )
                questions.append(
                    QuizQuestion(
                        question_type=question_type,
                        question=question,
                        answer=answer,
                        options=options,
                        chunk_id=chunk.id,
                        chunk_position=chunk.position,
                        page_number=chunk.page_number,
                    )
                )
                if len(questions) >= count:
                    return DocumentQuiz(document.id, document.filename, questions)
        return DocumentQuiz(document.id, document.filename, questions)

    def validate_answer(
        self,
        *,
        document_id: int,
        question_index: int,
        submitted_answer: str,
        count: int,
    ) -> bool:
        quiz = self.generate(
            document_id=document_id,
            count=max(count, question_index + 1),
        )
        if question_index < 0 or question_index >= len(quiz.questions):
            raise IndexError("question_index is outside the generated quiz.")
        return _normalize_answer(submitted_answer) == _normalize_answer(
            quiz.questions[question_index].answer
        )

    def _collect_answers(self, chunks: list[DocumentChunk]) -> list[str]:
        answers = {
            word
            for chunk in chunks
            for sentence in SENTENCE_PATTERN.split(chunk.text)
            for word in WORD_PATTERN.findall(sentence)
        }
        return sorted(answers, key=lambda item: (len(item), item.lower()))

    def _build_options(self, answer: str, answer_pool: list[str]) -> list[str]:
        distractors = [
            candidate
            for candidate in answer_pool
            if candidate.lower() != answer.lower()
        ]
        options = [answer, *distractors[-2:]]
        return sorted(options, key=str.casefold)


class LocalFlashcardService:
    """Create simple source-linked flashcards without external services."""

    def __init__(self, document_service: DocumentContentProtocol) -> None:
        self._document_service = document_service

    def generate(self, *, document_id: int, count: int) -> DocumentFlashcards:
        document = self._document_service.get_document(document_id)
        chunk_list = self._document_service.list_document_chunks(document_id)
        cards: list[Flashcard] = []
        for chunk in chunk_list.chunks:
            for sentence in SENTENCE_PATTERN.split(chunk.text):
                text = " ".join(sentence.split())
                if len(text) < 20:
                    continue
                cards.append(
                    Flashcard(
                        front="Explain this concept: " + text,
                        back=text,
                        chunk_id=chunk.id,
                        chunk_position=chunk.position,
                        page_number=chunk.page_number,
                    )
                )
                if len(cards) >= count:
                    return DocumentFlashcards(document.id, document.filename, cards)
        return DocumentFlashcards(document.id, document.filename, cards)


def _normalize_answer(value: str) -> str:
    return " ".join(value.strip().casefold().split())
