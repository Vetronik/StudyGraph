from dataclasses import dataclass

DEFAULT_CHUNK_OVERLAP = 150
DEFAULT_CHUNK_SIZE = 1000


@dataclass(frozen=True)
class TextChunk:
    position: int
    text: str

    @property
    def character_count(self) -> int:
        return len(self.text)


def chunk_text(
    text: str,
    *,
    max_characters: int = DEFAULT_CHUNK_SIZE,
    overlap_characters: int = DEFAULT_CHUNK_OVERLAP,
) -> list[TextChunk]:
    if max_characters <= 0:
        raise ValueError("max_characters must be greater than 0.")

    if overlap_characters < 0:
        raise ValueError("overlap_characters must not be negative.")

    if overlap_characters >= max_characters:
        raise ValueError("overlap_characters must be smaller than max_characters.")

    normalized_text = " ".join(text.split())

    if not normalized_text:
        return []

    chunks: list[TextChunk] = []
    start = 0

    while start < len(normalized_text):
        end = min(start + max_characters, len(normalized_text))

        if end < len(normalized_text):
            word_boundary = normalized_text.rfind(" ", start, end + 1)

            if word_boundary > start:
                end = word_boundary

        chunk = normalized_text[start:end].strip()

        if chunk:
            chunks.append(TextChunk(position=len(chunks), text=chunk))

        if end >= len(normalized_text):
            break

        start = max(end - overlap_characters, 0)

        while start < len(normalized_text) and normalized_text[start].isspace():
            start += 1

    return chunks
