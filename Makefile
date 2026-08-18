.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help
help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.env: ## Create .env from the example if it does not exist
	@test -f .env || (cp .env.example .env && echo "created .env from .env.example")

.PHONY: up
up: .env ## Start the whole stack and wait for health
	$(COMPOSE) up -d --wait
	@echo
	@echo "api      http://localhost:8000/docs"
	@echo "minio    http://localhost:9001  (filmroll / filmroll-dev-secret)"
	@echo "mailpit  http://localhost:8025"

.PHONY: down
down: ## Stop the stack, keep volumes
	$(COMPOSE) down

.PHONY: clean
clean: ## Stop the stack and destroy volumes for a true cold boot
	$(COMPOSE) down -v --remove-orphans

.PHONY: build
build: .env ## Rebuild images
	$(COMPOSE) build

.PHONY: logs
logs: ## Tail logs from every service
	$(COMPOSE) logs -f

.PHONY: ps
ps: ## Show service status
	$(COMPOSE) ps

.PHONY: migrate
migrate: ## Apply database migrations
	$(COMPOSE) run --rm api alembic upgrade head

.PHONY: revision
revision: ## Autogenerate a migration:  make revision m="add shots"
	$(COMPOSE) run --rm api alembic revision --autogenerate -m "$(m)"

.PHONY: test
test: .env ## Run the full suite including the load test
	$(COMPOSE) run --rm api pytest

.PHONY: test-fast
test-fast: .env ## Run everything except the load test, used by the pre-push hook
	$(COMPOSE) run --rm api pytest -m "not load" -q

.PHONY: lint
lint: ## Ruff and mypy
	$(COMPOSE) run --rm api ruff check .
	$(COMPOSE) run --rm api mypy app

.PHONY: fmt
fmt: ## Format with ruff
	$(COMPOSE) run --rm api ruff format .
	$(COMPOSE) run --rm api ruff check --fix .

.PHONY: shell
shell: ## Shell into the api container
	$(COMPOSE) run --rm api bash

.PHONY: psql
psql: ## Open psql against the dev database
	$(COMPOSE) exec db psql -U filmroll -d filmroll

.PHONY: mobile
mobile: ## Start the Expo guest camera (hosts stay on the web)
	cd mobile && npm start
