.PHONY: install test coverage lint fmt api engine web web-test web-e2e openapi demo clean

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
	@echo "FastAPI app is delivered in Phase 12; run 'make api' then."

engine:
	@echo "Engine CLI is delivered in Phase 11; run 'make engine' then."

web:
	@echo "Next.js dashboard is delivered in Phase 13; run 'make web' then."

web-test:
	@echo "Web tests are delivered in Phase 13; run 'make web-test' then."

web-e2e:
	@echo "Playwright tests are delivered in Phase 18; run 'make web-e2e' then."

openapi:
	@echo "OpenAPI generation is delivered in Phase 12; run 'make openapi' then."

demo:
	@echo "Demo CLI is delivered in Phase 18; run 'make demo' then."

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml \
		sentinel.egg-info build dist
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
