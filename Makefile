.PHONY: help install env up down build rebuild logs restart ps shell run stop clean

PORT ?= 8000
COMPOSE ?= docker compose
export DOCKER_BUILDKIT ?= 1
export COMPOSE_DOCKER_CLI_BUILD ?= 1

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Create venv and install Python dependencies
	python3 -m venv .venv
	.venv/bin/pip install -U pip
	.venv/bin/pip install -r requirements.txt

env: ## Copy .env.example to .env if missing
	@test -f .env || cp .env.example .env
	@echo ".env is ready — set OPENAI_API_KEY"

up: env ## Build and start with Docker Compose
	$(COMPOSE) up --build -d
	@echo "Open http://127.0.0.1:$(PORT)"

down: ## Stop and remove containers
	$(COMPOSE) down

build: ## Build Docker image
	$(COMPOSE) build

rebuild: ## Rebuild image without cache and restart
	$(COMPOSE) build --no-cache
	$(COMPOSE) up -d

logs: ## Follow container logs
	$(COMPOSE) logs -f app

restart: ## Restart the app container
	$(COMPOSE) restart app

ps: ## Show compose status
	$(COMPOSE) ps

shell: ## Open a shell in the running container
	$(COMPOSE) exec app bash

run: env ## Run locally with uvicorn (no Docker)
	.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port $(PORT)

stop: down ## Alias for down

clean: down ## Stop containers and remove local generated files
	rm -rf uploads/* outputs/*
	@touch uploads/.gitkeep outputs/.gitkeep
