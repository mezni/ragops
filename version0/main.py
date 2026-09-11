"""
main.py
Unified CLI entry point for managing database migrations, running indexing pipelines,
executing retrieval queries, running evaluation benchmarks, and launching the Streamlit app.
"""

import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from core.config import settings
from core.logging import get_logger
from database import DatabaseManager
from evaluation.runner import EvaluationRunner
from indexing.builder import run_indexing_pipeline
from loaders.filesystem import FilesystemLoader
from retrieval.builder import build_retrieval_pipeline
from retrieval.stages.models import Query, SynthesizedResponse
from retrieval.vector_store.qdrant import QdrantAdapter

app = typer.Typer(
    name="RAG Pipeline CLI",
    help="Production-grade RAG pipeline CLI for indexing, search, evaluation, and system administration.",
    add_completion=False,
)
console = Console()
logger = get_logger(name)


def _format_score(score: float) -> str:
    """Helper utility to color-code metric scores for Rich console output."""
    if score >= 0.8:
        return f"[bold green]{score:.4f}[/bold green]"
    elif score >= 0.6:
        return f"[bold yellow]{score:.4f}[/bold yellow]"
    return f"[bold red]{score:.4f}[/bold red]"


@app.command("migrate")
def run_migrations(
    message: Optional[str] = typer.Option(None, "--message", "-m", help="Revision description message for new migration.")
):
    """Executes database schema migrations using Alembic."""
    console.print("[bold blue]Running Database Migrations...[/bold blue]")
    try:
        if message:
            subprocess.run(["alembic", "revision", "--autogenerate", "-m", message], check=True)
            console.print(f"[bold green]Created migration revision with message: '{message}'[/bold green]")
        subprocess.run(["alembic", "upgrade", "head"], check=True)
        console.print("[bold green]Database migrations applied successfully.[/bold green]")
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Migration failed with exit code {e.returncode}[/bold red]")
        raise typer.Exit(code=1)


@app.command("index")
def run_indexing(
    dir_path: str = typer.Option("./data", "--dir", "-d", help="Directory containing source documents to index."),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", help="Scan subdirectories recursively."),
):
    """Scans a directory, parses documents, updates payload versions, and updates vector store."""
    path = Path(dir_path)
    if not path.exists():
        console.print(f"[bold red]Error: Directory '{dir_path}' does not exist.[/bold red]")
        raise typer.Exit(code=1)

    console.print(f"[bold blue]Starting Ingestion & Indexing Pipeline for directory:[/bold blue] {path.resolve()}")

    db_manager = DatabaseManager()
    loader = FilesystemLoader(directory_path=str(path), recursive=recursive)

    try:
        embedded_chunks = run_indexing_pipeline(
            loader=loader,
            db_manager=db_manager,
            vector_store_adapter=None,
        )

        table = Table(title="Indexing Pipeline Summary", show_header=True, header_style="bold magenta")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Processed Source Dir", str(path.resolve()))
        table.add_row("Total Generated Chunks", str(len(embedded_chunks)))
        table.add_row("Embedding Vector Dimension", str(len(embedded_chunks[0].vector) if embedded_chunks else 0))

        console.print(table)
        console.print("[bold green]Indexing process completed successfully![/bold green]")
    except Exception as e:
        logger.error("Indexing failed", error=str(e))
        console.print(f"[bold red]Indexing failed:[/bold red] {str(e)}")
        raise typer.Exit(code=1)


@app.command("query")
def query_rag(
    user_query: str = typer.Argument(..., help="Search query or user prompt."),
    top_k: int = typer.Option(settings.TOP_K, "--top-k", "-k", help="Number of context chunks to retrieve."),
    rerank_top_n: int = typer.Option(3, "--top-n", "-n", help="Number of chunks post-reranking."),
    transform_mode: str = typer.Option("rewrite", "--transform-mode", "-m", help="'rewrite' or 'hyde'."),
    collection: str = typer.Option("rag_documents", "--collection", "-c", help="Qdrant collection name."),
):
    """Executes vector search and returns synthesized RAG answer for a user prompt."""
    console.print("[bold cyan]Initializing Retrieval Pipeline...[/bold cyan]")

    try:
        vector_store = QdrantAdapter(collection_name=collection)
    except Exception as e:
        console.print(f"[bold red]Failed to connect to Qdrant:[/bold red] {e}")
        raise typer.Exit(code=1)

    pipeline = build_retrieval_pipeline(
        vector_store_adapter=vector_store,
        transform_mode=transform_mode,
        rerank_top_n=rerank_top_n,
    )

    query_input = Query(raw_query=user_query, top_k=top_k)

    try:
        result: SynthesizedResponse = pipeline.run(query_input)
    except Exception as e:
        console.print(f"[bold red]Pipeline execution failed:[/bold red] {e}")
        raise typer.Exit(code=1)

    console.print()
    console.print(Panel(result.answer, title="[bold green]Synthesized Response[/bold green]", border_style="green", expand=False))

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


@app.command("evaluate")
def run_evaluation(
    dataset_path: str = typer.Option("tests/eval_dataset.json", "--dataset", "-d", help="Ground truth JSON benchmark dataset."),
    output_path: Optional[str] = typer.Option("eval_report.json", "--output", "-o", help="Destination path to export JSON report."),
    run_id: Optional[str] = typer.Option(None, "--run-id", "-r", help="Optional run identifier."),
):
    """Runs quality benchmarks against evaluation test datasets (Context Precision, Recall, Faithfulness)."""
    dataset_file = Path(dataset_path)
    if not dataset_file.exists():
        console.print(f"[bold red]Error:[/bold red] Dataset file not found at '{dataset_path}'")
        raise typer.Exit(code=1)

    console.print(
        Panel.fit(
            f"[bold cyan]RAG Quality Evaluation Benchmark[/bold cyan]\n[dim]Dataset:[/dim] {dataset_path}",
            border_style="cyan",
        )
    )

    runner = EvaluationRunner()

    with console.status("[bold green]Executing evaluation benchmark suite...", spinner="dots"):
        try:
            report = runner.run_suite(dataset=dataset_file, run_id=run_id)
        except Exception as e:
            console.print(f"[bold red]Evaluation execution failed:[/bold red] {e}")
            raise typer.Exit(code=1)

    console.print("\n[bold green]Evaluation execution completed successfully![/bold green]\n")

    # Display summary score table
    summary_table = Table(title="[bold]Global Mean Evaluation Metrics[/bold]", show_header=True, header_style="bold magenta")
    summary_table.add_column("Metric Name", style="cyan", no_wrap=True)
    summary_table.add_column("Mean Score", justify="right")

    for metric_name, score in report.mean_scores.items():
        summary_table.add_row(metric_name, _format_score(score))

    console.print(summary_table)
    console.print()

    # Display test case table
    case_table = Table(title=f"[bold]Detailed Results ({report.total_test_cases} Test Cases)[/bold]", show_header=True, header_style="bold blue")
    case_table.add_column("Test ID", style="dim", no_wrap=True)
    case_table.add_column("User Query", style="white", max_width=40)
    case_table.add_column("Precision", justify="right")
    case_table.add_column("Recall", justify="right")
    case_table.add_column("Faithfulness", justify="right")
    case_table.add_column("Latency (s)", justify="right", style="dim")

    for detail in report.detailed_results:
        prec = detail.metric_scores.get("context_precision")
        rec = detail.metric_scores.get("context_recall")
        faith = detail.metric_scores.get("faithfulness")

        case_table.add_row(
            detail.test_id,
            detail.user_query,
            _format_score(prec.score) if prec else "N/A",
            _format_score(rec.score) if rec else "N/A",
            _format_score(faith.score) if faith else "N/A",
            f"{detail.execution_time_seconds:.2f}",
        )

    console.print(case_table)

    if output_path:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        import json
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(report.model_dump(mode="json"), f, indent=2)

        console.print(f"\n[bold green]Report exported to:[/bold green] [underline]{out_file.resolve()}[/underline]\n")


@app.command("ui")
def launch_streamlit():
    """Launches the Streamlit web app interface."""
    console.print("[bold blue]Starting Streamlit UI...[/bold blue]")
    app_path = Path(__file__).parent / "app" / "streamlit_app.py"
    try:
        subprocess.run(["streamlit", "run", str(app_path)], check=True)
    except KeyboardInterrupt:
        console.print("[bold yellow]Streamlit server stopped.[/bold yellow]")
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Streamlit launch failed with exit code {e.returncode}[/bold red]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
 PYEOF