import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from studygraph.retrieval_service import (
    RetrievalContext,
    RetrievalService,
    RetrievalSource,
)


class AnswerProviderProtocol(Protocol):
    def answer(self, *, query: str, context: RetrievalContext) -> str: ...


class AnswerProviderError(RuntimeError):
    """Raised when a configured remote answer provider cannot answer."""


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


class OpenAICompatibleAnswerProvider:
    """Call an OpenAI-compatible chat-completions endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        api_url: str,
        model: str,
        timeout_seconds: int,
        max_context_characters: int,
        max_output_tokens: int,
    ) -> None:
        if not api_key:
            raise ValueError("answer api_key must not be empty.")
        self._api_key = api_key
        self._api_url = api_url
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._max_context_characters = max_context_characters
        self._max_output_tokens = max_output_tokens

    def answer(self, *, query: str, context: RetrievalContext) -> str:
        payload = json.dumps(
            {
                "model": self._model,
                "temperature": 0,
                "max_tokens": self._max_output_tokens,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Answer only from the supplied context. Cite supporting "
                            "material using [source N]. If the context does not "
                            "contain the answer, say that clearly."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Question: {query}\n\nContext:\n"
                            f"{context.context[:self._max_context_characters]}"
                        ),
                    },
                ],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self._api_url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self._timeout_seconds,
            ) as response:
                body = json.load(response)
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            raise AnswerProviderError("Answer provider request failed.") from error

        try:
            answer = body["choices"][0]["message"]["content"]
        except (IndexError, KeyError, TypeError) as error:
            raise AnswerProviderError(
                "Answer provider returned an invalid response."
            ) from error
        if not isinstance(answer, str) or not answer.strip():
            raise AnswerProviderError("Answer provider returned an empty answer.")
        return answer.strip()


def get_answer_provider() -> AnswerProviderProtocol:
    from studygraph.config import (
        ConfigurationError,
        get_answer_api_key,
        get_answer_api_url,
        get_answer_max_context_characters,
        get_answer_max_output_tokens,
        get_answer_model,
        get_answer_provider_name,
        get_answer_timeout_seconds,
    )

    if get_answer_provider_name() == "local":
        return LocalExtractiveAnswerProvider()
    api_key = get_answer_api_key()
    if not api_key:
        raise ConfigurationError(
            "STUDYGRAPH_ANSWER_API_KEY must be set for the remote answer provider."
        )
    return OpenAICompatibleAnswerProvider(
        api_key=api_key,
        api_url=get_answer_api_url(),
        model=get_answer_model(),
        timeout_seconds=get_answer_timeout_seconds(),
        max_context_characters=get_answer_max_context_characters(),
        max_output_tokens=get_answer_max_output_tokens(),
    )


class RAGService:
    def __init__(
        self,
        retrieval_service: RetrievalService,
        answer_provider: AnswerProviderProtocol | None = None,
    ) -> None:
        self._retrieval_service = retrieval_service
        self._answer_provider = answer_provider or get_answer_provider()

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
