from types import SimpleNamespace

import httpx
import openai
import pytest
from tenacity import retry as tenacity_retry
from tenacity import retry_if_exception_type, stop_after_attempt, wait_fixed

from core.resiliency import _RETRYABLE_ERRORS, embedding_request


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://openrouter.ai/api/v1/embeddings")


def _rate_limit_error() -> openai.RateLimitError:
    return openai.RateLimitError(
        "429 rate limited",
        response=httpx.Response(429, request=_request()),
        body={},
    )


class ResilientClient:
    """Minimal OpenAI-like client that fails a configurable number of times."""

    def __init__(self, failure_count: int, exc, dims: int = 2):
        self.failure_count = failure_count
        self.exc = exc
        self.dims = dims
        self.calls = 0
        # OpenAI SDK accesses client.embeddings.create(...) — mirror it.
        self.embeddings = self

    def create(self, model, input):
        self.calls += 1
        if self.calls <= self.failure_count:
            raise self.exc
        texts = list(input)
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[1.0] * self.dims) for _ in texts]
        )


def test_embedding_request_happy_path_no_retry():
    client = ResilientClient(
        failure_count=0,
        exc=openai.APIConnectionError(message="boom", request=_request()),
    )
    resp = embedding_request(client, "model-x", ["a", "b"])
    assert client.calls == 1
    assert len(resp.data) == 2


def test_embedding_request_does_not_retry_non_retryable_errors():
    client = ResilientClient(
        failure_count=10,
        exc=openai.BadRequestError("400 bad", response=httpx.Response(400, request=_request()), body={}),
    )
    with pytest.raises(openai.BadRequestError):
        embedding_request(client, "model-x", ["a"])
    assert client.calls == 1


def test_retryable_error_set_covers_transient_failures():
    assert openai.RateLimitError in _RETRYABLE_ERRORS
    assert openai.APITimeoutError in _RETRYABLE_ERRORS
    assert openai.APIConnectionError in _RETRYABLE_ERRORS
    assert openai.BadRequestError not in _RETRYABLE_ERRORS


def test_retry_policy_retries_transient_errors_then_succeeds():
    # Mirrored policy with zero wait so the test stays deterministic/fast.
    resilient = tenacity_retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_fixed(0),
        retry=retry_if_exception_type(_RETRYABLE_ERRORS),
    )(lambda client, model, texts: client.create(model, texts))

    client = ResilientClient(failure_count=2, exc=_rate_limit_error())
    resp = resilient(client, "model-x", ["a"])
    assert client.calls == 3
    assert len(resp.data) == 1


def test_retry_policy_exhausts_attempts_then_raises():
    resilient = tenacity_retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_fixed(0),
        retry=retry_if_exception_type(_RETRYABLE_ERRORS),
    )(lambda client, model, texts: client.create(model, texts))

    client = ResilientClient(failure_count=10, exc=_rate_limit_error())
    with pytest.raises(openai.RateLimitError):
        resilient(client, "model-x", ["a"])
    assert client.calls == 3