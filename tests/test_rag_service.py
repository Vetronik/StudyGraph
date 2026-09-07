import json

import pytest

from studygraph.config import ConfigurationError
from studygraph.rag_service import (
    AnswerProviderError,
    LocalExtractiveAnswerProvider,
    OpenAICompatibleAnswerProvider,
    RetrievalContext,
    RetrievalSource,
    get_answer_provider,
)


def _context() -> RetrievalContext:
    source = RetrievalSource(
        source_number=1,
        document_id=1,
        document_filename="lecture.pdf",
        chunk_id=1,
        chunk_position=0,
        page_number=2,
        text="The answer is forty-two.",
    )
    return RetrievalContext(
        query="What is the answer?",
        sources=[source],
        context="[source 1] lecture.pdf, page 2, chunk 1\nThe answer is forty-two.",
    )


def test_answer_provider_defaults_to_offline_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STUDYGRAPH_ANSWER_PROVIDER", raising=False)

    assert isinstance(get_answer_provider(), LocalExtractiveAnswerProvider)


def test_openai_compatible_answer_provider_sends_grounded_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OpenAICompatibleAnswerProvider(
        api_key="test-key",
        api_url="https://example.test/v1/chat/completions",
        model="test-model",
        timeout_seconds=5,
        max_context_characters=10,
        max_output_tokens=25,
        max_output_characters=6_000,
    )
    captured_requests: list[object] = []

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"choices": [{"message": {"content": "42 [source 1]"}}]}'

    def fake_urlopen(request: object, **_kwargs: object) -> FakeResponse:
        captured_requests.append(request)
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    answer = provider.answer(query="Was ist die L\u00f6sung?", context=_context())

    request = captured_requests[0]
    payload = json.loads(request.data)
    assert "L\u00f6sung".encode("utf-8") in request.data
    assert answer == "42 [source 1]"
    assert payload["model"] == "test-model"
    assert payload["max_tokens"] == 25
    assert len(payload["messages"][1]["content"]) < 60
    assert "[source N]" in payload["messages"][0]["content"]
    assert "\u00e4, \u00f6, \u00fc and \u00df" in payload["messages"][0]["content"]
    assert "L\u00f6sung" in payload["messages"][1]["content"]


def test_remote_answer_provider_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STUDYGRAPH_ANSWER_PROVIDER", "openai-compatible")
    monkeypatch.delenv("STUDYGRAPH_ANSWER_API_KEY", raising=False)

    with pytest.raises(ConfigurationError, match="STUDYGRAPH_ANSWER_API_KEY"):
        get_answer_provider()


def test_remote_answer_provider_rejects_oversized_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OpenAICompatibleAnswerProvider(
        api_key="test-key",
        api_url="https://example.test/v1/chat/completions",
        model="test-model",
        timeout_seconds=5,
        max_context_characters=10,
        max_output_tokens=25,
        max_output_characters=5,
    )

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    def fake_urlopen(_request: object, **_kwargs: object) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(
        "json.load",
        lambda _response: {"choices": [{"message": {"content": "123456"}}]},
    )

    with pytest.raises(AnswerProviderError, match="oversized"):
        provider.answer(query="What is the answer?", context=_context())
