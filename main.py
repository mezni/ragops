"""
main.py
CLI entry point for executing pipeline operations and RAG queries.
"""

from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from core.logging import get_logger
from retrieval.builder import build_retrieval_pipeline
from retrieval.stages.models import Query, SynthesizedResponse
from retrieval.vector_store.qdrant import QdrantAdapter

app = typer.Typer(
    name="rag-cli",
    help="CLI management tool for versioned retrieval pipelines and search execution.",
    add_completion=False,
)
console = Console()
logger = get_logger(name)


@app.command(name="query")
def run_query(
    user_query: str = typer.Argument(
        ...,
        help="The question or search prompt to execute through the RAG pipeline.",
    ),
    top_k: int = typer.Option(
        5,
        "--top-k",
        "-k",
        help="Number of initial candidate chunks to retrieve from Qdrant.",
    ),
    rerank_top_n: int = typer.Option(
        3,
        "--top-n",
        "-n",
        help="Number of top chunks to retain post-reranking for context synthesis.",
    ),
    transform_mode: str = typer.Option(
        "rewrite",
        "--transform-mode",
        "-m",
        help="Query transformation strategy: 'rewrite' or 'hyde'.",
    ),
    collection: str = typer.Option(
        "rag_documents",
        "--collection",
        "-c",
        help="Target Qdrant collection name.",
    ),
    payload_id: Optional[str] = typer.Option(
        None,
        "--payload-id",
        "-p",
        help="Filter vector search by a specific document/payload ID.",
    ),
    payload_version: Optional[int] = typer.Option(
        None,
        "--payload-version",
        "-v",
        help="Filter vector search by a specific version integer.",
    ),
) -> None:
    """Executes a search query using Qdrant vector retrieval and LLM answer synthesis."""
    console.print(f"[bold cyan]Initializing Retrieval Pipeline...[/bold cyan]")

    # 1. Initialize Vector Store Adapter
    try:
        vector_store = QdrantAdapter(collection_name=collection)
    except Exception as e:
        console.print(f"[bold red]Failed to connect to Qdrant:[/bold red] {e}")
        raise typer.Exit(code=1)

    # 2. Assemble Retrieval Pipeline
    pipeline = build_retrieval_pipeline(
        vector_store_adapter=vector_store,
        transform_mode=transform_mode,
        rerank_top_n=rerank_top_n,
    )

    # 3. Construct Query and Filters
    filters = {}
    if payload_id:
        filters["payload_id"] = payload_id
    if payload_version:
        filters["version"] = payload_version

    query_input = Query(
        raw_query=user_query,
        top_k=top_k,
        filters=filters,
    )

    # 4. Execute Pipeline
    console.print(f"[dim]Executing query: '{user_query}'[/dim]")
    try:
        result: SynthesizedResponse = pipeline.run(query_input)
    except Exception as e:
        console.print(f"[bold red]Pipeline execution failed:[/bold red] {e}")
        logger.error("Pipeline run error", error=str(e))
        raise typer.Exit(code=1)

    # 5. Display Answer
    console.print()
    console.print(
        Panel(
            result.answer,
            title="[bold green]Synthesized Response[/bold green]",
            border_style="green",
            expand=False,
        )
    )

    # 6. Display Cited Context Chunks
    if result.cited_chunks:
        table = Table(title="Retrieved & Reranked Context Chunks", show_header=True, header_style="bold magenta")
        table.add_column("Chunk ID", style="dim", width=25)
        table.add_column("Version", justify="center", width=8)
        table.add_column("Vector Score", justify="right", width=12)
        table.add_column("Rerank Score", justify="right", width=12)
        table.add_column("Snippet Preview", width=50)

        for chunk in result.cited_chunks:
            rerank_str = f"{chunk.rerank_score:.4f}" if chunk.rerank_score is not None else "N/A"
            table.add_row(
                chunk.chunk_id,
                str(chunk.payload_version),
                f"{chunk.score:.4f}",
                rerank_str,
                chunk.chunk_text[:75].replace("\n", " ") + "...",
            )

        console.print(table)


if __name__ == "__main__":
    app()
PYEOF