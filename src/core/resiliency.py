import logging
from typing import List

import openai
from openai import OpenAI
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger(__name__)

# OpenRouter calls that can transiently fail: rate limits (429), socket
# drops, read timeouts. Any other exception is raised immediately.
_RETRYABLE_ERRORS = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
)


@retry(
    reraise=True,
    stop=stop_after_attempt(5),
    wait=wait_exponential_jitter(initial=1, max=30, exp_base=2, jitter=2),
    retry=retry_if_exception_type(_RETRYABLE_ERRORS),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def embedding_request(client: OpenAI, model: str, texts: List[str]):
    """One embedding API call with exponential backoff + jitter retries."""
    return client.embeddings.create(model=model, input=texts)