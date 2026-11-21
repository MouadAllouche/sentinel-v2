.PHONY: install test coverage lint fmt api demo-api engine web web-test web-e2e openapi demo clean

install:
	./venv/bin/pip install -e ".[dev]"

test:
	./venv/bin/python -m pytest

coverage:
	./venv/bin/python -m pytest --cov=core --cov=collectors --cov=storage --cov=engine \
		--cov=api --cov-report=term-missing

lint:
	./venv/bin/ruff check .
	./venv/bin/ruff format --check .
	./venv/bin/mypy

fmt:
	./venv/bin/ruff format .
	./venv/bin/ruff check --fix .

api:
	SENTINEL_SESSION_KEY=$${SENTINEL_SESSION_KEY:-$$($$(pwd)/venv/bin/python -c "import secrets;print(secrets.token_hex(32))")} \
		SENTINEL_CONFIG=$${SENTINEL_CONFIG:-config/settings.toml} \
		./venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000

demo-api:
	SENTINEL_SESSION_KEY=demo-session-key-0123456789abcdef \
		SENTINEL_CONFIG=demo_workdir/settings.toml \
		./venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000

engine:
	./venv/bin/python cli.py engine

web:
	cd web && npm run dev

web-test:
	cd web && npm test && npm run typecheck && npm run lint

web-e2e:
	cd web && npm run test:e2e

openapi:
	SENTINEL_SESSION_KEY=openapi-generation-key-0123456789abcdef ./venv/bin/python -c "import json;from api.main import create_app;json.dump(create_app().openapi(),open('web/openapi.json','w'),sort_keys=True,indent=2)"

demo:
	./venv/bin/python cli.py demo

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml \
		sentinel.egg-info build dist
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
