.PHONY: help up down dev-backend dev-frontend test migrate fresh

help:
	@echo "RepoLens — make targets"
	@echo ""
	@echo "  up             Start postgres (docker compose)"
	@echo "  down           Stop postgres"
	@echo "  dev-backend    Run backend (uvicorn) on :8004"
	@echo "  dev-frontend   Run frontend (next) on :3003"
	@echo "  test           Run backend tests"
	@echo "  migrate        Apply alembic migrations"
	@echo "  fresh          Drop volumes, recreate, migrate (destructive)"

up:
	docker compose up -d postgres

down:
	docker compose down

dev-backend:
	cd backend && uv run uvicorn repolens.main:app --port 8004 --reload

dev-frontend:
	cd frontend && npm run dev

test:
	cd backend && uv run pytest -v

migrate:
	cd backend && uv run alembic upgrade head

fresh:
	docker compose down -v
	docker compose up -d postgres
	sleep 3
	$(MAKE) migrate
