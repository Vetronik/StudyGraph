import pytest

from studygraph.embedding_service import (
    DeterministicHashEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    cosine_similarity,
    get_embedding_provider,
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


def test_embedding_provider_factory_defaults_to_local_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STUDYGRAPH_EMBEDDING_PROVIDER", raising=False)

    provider = get_embedding_provider(dimensions=8)

    assert isinstance(provider, DeterministicHashEmbeddingProvider)
    assert provider.dimensions == 8


def test_embedding_provider_factory_requires_key_for_remote_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STUDYGRAPH_EMBEDDING_PROVIDER", "openai-compatible")
    monkeypatch.delenv("STUDYGRAPH_EMBEDDING_API_KEY", raising=False)

    with pytest.raises(ValueError, match="api_key"):
        get_embedding_provider(dimensions=8)


def test_openai_compatible_provider_rejects_wrong_dimensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OpenAICompatibleEmbeddingProvider(
        api_key="test-key",
        api_url="https://example.test/v1/embeddings",
        model="test-model",
        dimensions=2,
    )

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"data": [{"index": 0, "embedding": [1.0]}]}'

    def fake_urlopen(*_args: object, **_kwargs: object) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr(
        "urllib.request.urlopen",
        fake_urlopen,
    )
    with pytest.raises(RuntimeError, match="dimensions"):
        provider.embed_texts(["test"])
