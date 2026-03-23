COREPACK_PNPM=corepack pnpm

.PHONY: dev-research test-research run-streamlit demo-local web-install web-dev web-build

dev-research:
	$(MAKE) -C services/research-engine dev

test-research:
	$(MAKE) -C services/research-engine test

run-streamlit:
	cd apps/streamlit && \
	python3 -m venv .venv && \
	. .venv/bin/activate && \
	pip install -r requirements.txt && \
	RESEARCH_API_BASE=$${RESEARCH_API_BASE:-http://localhost:8000} streamlit run app.py

# Starts the FastAPI backend on :8000 and the Streamlit app on :8501.
demo-local:
	sh scripts/run_local_demo.sh

web-install:
	cd apps/web && $(COREPACK_PNPM) install

web-dev:
	cd apps/web && NEXT_PUBLIC_API_BASE_URL=$${NEXT_PUBLIC_API_BASE_URL:-http://localhost:8787} $(COREPACK_PNPM) dev

web-build:
	cd apps/web && NEXT_PUBLIC_API_BASE_URL=$${NEXT_PUBLIC_API_BASE_URL:-http://localhost:8787} $(COREPACK_PNPM) build
