from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from math import sqrt
from typing import Protocol

from sqlalchemy.types import UserDefinedType

DEFAULT_EMBEDDING_DIMENSIONS = 64


class Vector(UserDefinedType):
    """SQLAlchemy type for PostgreSQL's pgvector extension."""

    cache_ok = True

    def __init__(self, dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be greater than 0.")
        self.dimensions = dimensions

    def get_col_spec(self, **_kwargs: object) -> str:
        return f"VECTOR({self.dimensions})"

    def bind_processor(self, _dialect):
        def process(value):
            if value is None:
                return None
            return "[" + ",".join(str(float(item)) for item in value) + "]"

        return process

    def result_processor(self, _dialect, _coltype):
        def process(value):
            if value is None:
                return None
            if isinstance(value, str):
                return [float(item) for item in value.strip("[]()").split(",")]
            return list(value)

        return process


@dataclass(frozen=True)
class TextEmbedding:
    text: str
    vector: tuple[float, ...]


class EmbeddingProviderProtocol(Protocol):
    dimensions: int

    def embed_texts(self, texts: Sequence[str]) -> list[TextEmbedding]: ...


class DeterministicHashEmbeddingProvider:
    """Small local provider for tests and development, not semantic AI search."""

    def __init__(self, dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be greater than 0.")

        self.dimensions = dimensions

    def embed_texts(self, texts: Sequence[str]) -> list[TextEmbedding]:
        return [
            TextEmbedding(
                text=text,
                vector=self._embed_text(text),
            )
            for text in texts
        ]

    def _embed_text(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self.dimensions

        for token in _tokenize(text):
            digest = sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], byteorder="big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        return _normalize_vector(vector)


def cosine_similarity(
    first_vector: Sequence[float],
    second_vector: Sequence[float],
) -> float:
    if len(first_vector) != len(second_vector):
        raise ValueError("vectors must have the same dimensions.")

    first_norm = sqrt(sum(value * value for value in first_vector))
    second_norm = sqrt(sum(value * value for value in second_vector))

    if first_norm == 0 or second_norm == 0:
        return 0.0

    dot_product = sum(
        first_value * second_value
        for first_value, second_value in zip(first_vector, second_vector, strict=True)
    )
    return dot_product / (first_norm * second_norm)


def _tokenize(text: str) -> list[str]:
    return [
        token
        for token in text.lower().split()
        if token
    ]


def _normalize_vector(vector: Sequence[float]) -> tuple[float, ...]:
    norm = sqrt(sum(value * value for value in vector))

    if norm == 0:
        return tuple(0.0 for _ in vector)

    return tuple(value / norm for value in vector)
