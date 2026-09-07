import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class TopicCandidate:
    name: str
    confidence: float
    evidence: str


@dataclass(frozen=True)
class TopicRelation:
    source: str
    target: str
    evidence: str


@dataclass(frozen=True)
class TopicAnalysis:
    document_title: str | None
    metadata_lines: list[str]
    topics: list[TopicCandidate]
    relations: list[TopicRelation]


def analyze_document_topics(*, filename: str, text: str) -> TopicAnalysis:
    lines = [_clean_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    document_title, title_index = _detect_document_title(filename, lines)

    metadata_lines: list[str] = []
    topic_candidates: list[TopicCandidate] = []
    seen_topics: set[str] = set()
    for index, line in enumerate(lines):
        if _is_metadata_line(line) or index == title_index:
            metadata_lines.append(line)
            continue
        if not _looks_like_topic(line):
            continue
        key = _topic_key(line)
        if key in seen_topics:
            continue
        seen_topics.add(key)
        topic_candidates.append(
            TopicCandidate(
                name=line,
                confidence=0.9 if _looks_like_heading(line) else 0.7,
                evidence="heading-like line in extracted lecture content",
            )
        )

    relations = [
        TopicRelation(
            source=left.name,
            target=right.name,
            evidence="topics occur in the same document",
        )
        for index, left in enumerate(topic_candidates)
        for right in topic_candidates[index + 1 :]
        if _topics_are_related(left.name, right.name)
    ]
    return TopicAnalysis(
        document_title=document_title,
        metadata_lines=metadata_lines,
        topics=topic_candidates,
        relations=relations,
    )


def _detect_document_title(
    filename: str,
    lines: list[str],
) -> tuple[str | None, int | None]:
    del filename
    for index, line in enumerate(lines[:12]):
        if _is_metadata_line(line):
            continue
        if _looks_like_heading(line) and len(line.split()) >= 2:
            return line, index
    return None, None


def _is_metadata_line(line: str) -> bool:
    folded = _fold(line)
    return any(
        marker in folded
        for marker in (
            "vorlesungsfolien",
            "lecture slides",
            "letzte anderung",
            "universitat",
            "university",
            "ects",
            "ac-tu-inf",
        )
    ) or bool(re.search(r"\b(?:vu|ue|ss|ws)\s*\d", folded)) or bool(
        re.search(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", line)
    )


def _looks_like_topic(line: str) -> bool:
    if len(line) < 3 or len(line) > 100 or len(line.split()) > 12:
        return False
    if line.startswith(("http://", "https://")):
        return False
    if line[-1:] in ".,;:!?":
        return False
    return any(character.isalpha() for character in line)


def _looks_like_heading(line: str) -> bool:
    return line.isupper() or len(line.split()) <= 6


def _topics_are_related(left: str, right: str) -> bool:
    left_terms = set(_fold(left).split())
    right_terms = set(_fold(right).split())
    return (
        bool(left_terms & right_terms)
        or len(left_terms) == 1
        or len(right_terms) == 1
    )


def _clean_line(line: str) -> str:
    return " ".join(line.replace("\x00", "").split())


def _topic_key(value: str) -> str:
    return " ".join(_fold(value).split())


def _fold(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    )
