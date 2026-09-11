.PHONY: help install dev test lint docker-up docker-down

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "} {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies
	uv pip install -e ".[dev]"

dev: install  ## Set up development environment

test:  ## Run unit tests
	uv run pytest -q

lint:  ## Run linting
	uv run ruff check src/

docker-up:  ## Start docker services
	docker compose up -d

docker-down:  ## Stop docker services
	docker compose down

# TODO: Add more targets as the project grows