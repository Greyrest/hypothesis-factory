.PHONY: up down logs test lint openapi frontend
up:
	docker compose up --build -d
down:
	docker compose down
logs:
	docker compose logs -f --tail=100
test:
	python -m unittest discover -s tests -v
lint:
	ruff check services tests
openapi:
	python scripts/export_openapi.py
frontend:
	cd frontend && npm run dev
