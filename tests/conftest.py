"""Shared test fixtures.

Boots the docker-compose `postgres` service (quickstart step 3) once per
session and exposes a session factory / engine bound to `DATABASE_URL`,
matching `contracts/config-schema.md`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from pipeline.config import PipelineConfig
from pipeline.core.db import create_db_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKER_DIR = REPO_ROOT / "docker"
POSTGRES_SERVICE = "postgres"


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def _compose_up(service: str) -> None:
    subprocess.run(
        ["docker", "compose", "up", "-d", service],
        cwd=DOCKER_DIR,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="session")
def postgres_container() -> None:
    """Ensure the docker `postgres` service is running."""
    if not _docker_available():
        pytest.skip("docker not available; cannot run DB-backed tests")
    _compose_up(POSTGRES_SERVICE)
    yield


@pytest.fixture(scope="session")
def config() -> PipelineConfig:
    """Validated configuration from repo-root `config.yaml`."""
    return PipelineConfig()


@pytest.fixture(scope="session")
def engine(postgres_container: None, config: PipelineConfig) -> Engine:
    """Engine bound to the booted postgres service (pool from config)."""
    return create_db_engine(config)