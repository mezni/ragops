# Future Steps / Backlog

## Step 6: Convert to Async I/O for High-Throughput Batch Processing

| | |
|---|---|
| **Phase** | Ingestion |
| **Status** | Backlog |

**The Problem**

Your pipeline currently runs synchronously using standard `for` loops and blocking HTTP calls. Processing hundreds of documents or thousands of chunks sequentially wastes CPU time while waiting for OpenRouter API responses.

**How to Resolve It**

Migrate the pipeline to `AsyncOpenAI` and `asyncio`. Concurrent API requests and asynchronous file I/O reduce indexing latency significantly when handling entire document directories.

- **Use Async SDK:** Replace `OpenAI` with `AsyncOpenAI` in `Embedder` (`src/ingestion/stages/embedder.py`).
- **Batch & Bound Concurrency:** Use `asyncio.Semaphore` to manage parallel API requests without hitting rate limits (HTTP 429).
- **Process Files Concurrently:** Run embedding tasks in parallel using `asyncio.gather`.

## Step 7: Production Hardening (Logging, Retries, Error Isolation)

| | |
|---|---|
| **Phase** | Ingestion |
| **Status** | Backlog |

**The Problem**

Production ingestion pipelines fail in unpredictably noisy environments: OpenRouter returns rate limits (HTTP 429), network sockets drop, single corrupted PDF pages throw extraction exceptions, or malformed UTF-8 characters break parsing. Using simple `print()` statements leaves you blind in production logs, and unhandled errors crash the entire batch job halfway through.

**How to Resolve It**

- **Structured Logging:** Replace `print()` with standard `logging` configured for production tracing.
- **Exponential Backoff Retries:** Wrap OpenRouter API calls using `tenacity` so transient network hiccups and 429 rate limits retry automatically with jitter.
- **Graceful Pipeline Error Isolation:** Catch and log document-level failures so one broken file doesn't stop the processing of thousands of other files.