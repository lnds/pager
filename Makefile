.PHONY: up down reset seed logs test test-incidents test-catalog test-notifications lint check

up:
	docker compose up --build -d
	@echo "Pager en http://localhost:8080"

down:
	docker compose down

reset:
	docker compose down -v

seed:
	python3 scripts/seed.py

logs:
	docker compose logs -f incidents catalog notifications

test: test-incidents test-catalog test-notifications

test-incidents:
	cd services/incidents && uv run pytest

test-catalog:
	cd services/catalog && npm test

test-notifications:
	cd services/notifications && go test ./...

lint:
	cd services/incidents && uv run ruff check . && uv run ruff format --check .
	cd services/catalog && npm run lint
	cd services/notifications && go vet ./... && test -z "$$(gofmt -l .)"

check: lint test
