from types import SimpleNamespace

from ingestion.schemas import ChunkMetadata, EmbeddedChunk, TextChunk
from ingestion.stages.embedder import Embedder


class FakeEmbeddingsAPI:
    def __init__(self, dims: int):
        self.dims = dims
        self.calls = []

    def create(self, model, input):
        texts = list(input)
        self.calls.append((model, texts))
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[1.0] * self.dims) for _ in texts]
        )


class FakeClient:
    def __init__(self, dims: int = 4):
        self.embeddings = FakeEmbeddingsAPI(dims)


def _chunks(n: int):
    return [
        TextChunk(
            chunk_id=f"c{i}",
            doc_id="d",
            text=f"text {i}",
            chunk_index=i,
            metadata=ChunkMetadata(
                doc_id="d",
                source_path="docs/d.txt",
                source="docs/d.txt",
                content_hash="abc" * 21 + "ab1",
                chunk_index=i,
                total_chunks=n,
            ),
        )
        for i in range(n)
    ]


def test_embedder_empty_input_returns_empty():
    client = FakeClient()
    assert Embedder(client, "model-x").run([]) == []
    assert client.embeddings.calls == []


def test_embedder_batches_and_maps_results():
    client = FakeClient(dims=4)
    embedded = Embedder(client, "model-x").run(_chunks(5), batch_size=2)

    assert len(embedded) == 5
    assert all(isinstance(c, EmbeddedChunk) for c in embedded)
    # ChunkMetadata is flattened to a plain dict for Chroma.
    assert embedded[0].metadata["doc_id"] == "d"
    assert embedded[4].metadata["chunk_index"] == 4
    assert embedded[0].embedding == [1.0, 1.0, 1.0, 1.0]
    assert client.embeddings.calls == [
        ("model-x", ["text 0", "text 1"]),
        ("model-x", ["text 2", "text 3"]),
        ("model-x", ["text 4"]),
    ]


def test_embedder_single_batch_when_under_limit():
    client = FakeClient()
    embedded = Embedder(client, "model-x").run(_chunks(3), batch_size=10)
    assert len(embedded) == 3
    assert client.embeddings.calls == [("model-x", ["text 0", "text 1", "text 2"])]