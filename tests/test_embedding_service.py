import pytest

from studygraph.embedding_service import (
    DeterministicHashEmbeddingProvider,
    cosine_similarity,
)


def test_hash_embedding_provider_returns_fixed_dimension_vectors() -> None:
    provider = DeterministicHashEmbeddingProvider(dimensions=8)

    embeddings = provider.embed_texts(["Chain rule derivatives"])

    assert len(embeddings) == 1
    assert embeddings[0].text == "Chain rule derivatives"
    assert len(embeddings[0].vector) == 8


def test_hash_embedding_provider_is_deterministic() -> None:
    provider = DeterministicHashEmbeddingProvider(dimensions=16)

    first_embedding = provider.embed_texts(["Roman empire overview"])[0]
    second_embedding = provider.embed_texts(["Roman empire overview"])[0]

    assert first_embedding.vector == second_embedding.vector


def test_cosine_similarity_scores_identical_vectors_highest() -> None:
    provider = DeterministicHashEmbeddingProvider(dimensions=16)
    first_embedding, second_embedding, third_embedding = provider.embed_texts(
        [
            "linear algebra matrix",
            "linear algebra matrix",
            "roman history empire",
        ]
    )

    assert cosine_similarity(
        first_embedding.vector,
        second_embedding.vector,
    ) == pytest.approx(1.0)
    assert cosine_similarity(first_embedding.vector, third_embedding.vector) < 1


def test_cosine_similarity_rejects_mismatched_dimensions() -> None:
    with pytest.raises(ValueError, match="same dimensions"):
        cosine_similarity([1.0, 0.0], [1.0])


def test_hash_embedding_provider_rejects_invalid_dimensions() -> None:
    with pytest.raises(ValueError, match="dimensions"):
        DeterministicHashEmbeddingProvider(dimensions=0)
