"""Allow ``python -m pipeline`` to run the CLI."""

from pipeline.cli import app

if __name__ == "__main__":
    app()