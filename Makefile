.PHONY: dev-backend dev-frontend test seed install lint

install:
	pip install fastapi pydantic pydantic-settings uvicorn pyyaml httpx pytest pytest-cov respx jsonschema "python-jose[cryptography]" gitpython hdbcli
	cd apps/cockpit && npm install

# S5: Bind-Host kommt aus den Settings — uvicorn wird explizit darauf gebunden,
# damit die fail-closed-Prüfung in main.py den realen Bind beschreibt.
BIND_HOST ?= 127.0.0.1

dev-backend:
	SQLITE_DB=signal.db \
	INVENTORY_FILE=data/inventory.json \
	LINEAGE_FILE=data/lineage.json \
	CONTRACTS_DIR=contracts \
	CHECKS_DIR=checks \
	BIND_HOST=$(BIND_HOST) \
	uvicorn services.api.main:app --reload --host $(BIND_HOST) --port 8000

dev-frontend:
	cd apps/cockpit && npm run dev

test:
	python -m pytest tests/ -v --tb=short

seed:
	python scripts/seed.py

lint:
	python -m py_compile packages/dq_core/**/*.py services/api/**/*.py
	cd apps/cockpit && npx tsc --noEmit
