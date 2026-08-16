.PHONY: help install env up down build rebuild logs restart ps shell run stop clean test test-message test-golden

COMPOSE ?= docker compose
export DOCKER_BUILDKIT ?= 1
export COMPOSE_DOCKER_CLI_BUILD ?= 1

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Create venv and install Python dependencies
	python3 -m venv .venv
	.venv/bin/pip install -U pip
	.venv/bin/pip install -r requirements.txt

env: ## Copy .env.example to .env if missing
	@test -f .env || cp .env.example .env
	@echo ".env is ready — set TELEGRAM_BOT_TOKEN, RXRESUME_API_KEY, OPENAI_API_KEY"

up: env ## Build and start the bot with Docker Compose
	$(COMPOSE) up --build -d
	@echo "Bot is running. Follow logs with: make logs"

down: ## Stop and remove containers
	$(COMPOSE) down

build: ## Build Docker image
	$(COMPOSE) build

rebuild: ## Rebuild image without cache and restart
	$(COMPOSE) build --no-cache
	$(COMPOSE) up -d

logs: ## Follow container logs
	$(COMPOSE) logs -f bot

restart: ## Restart the bot container
	$(COMPOSE) restart bot

ps: ## Show compose status
	$(COMPOSE) ps

shell: ## Open a shell in the running container
	$(COMPOSE) exec bot bash

run: env ## Run the bot locally (no Docker)
	.venv/bin/python -m app.bot

test: ## Run unit tests (no LLM calls)
	.venv/bin/pytest -q

test-message: env ## Live /message cover-letter run against sample vacancy
	.venv/bin/python -m scripts.test_message

test-golden: env ## Validate golden cover-letter examples (letters only)
	.venv/bin/python -m scripts.eval_golden

stop: down ## Alias for down

clean: down ## Stop containers
	@echo "Cleaned up containers."
