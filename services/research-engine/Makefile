PYTHONPATH=src

install:
	./.venv/bin/pip install -r requirements.txt

dev:
	PYTHONPATH=$(PYTHONPATH) ./.venv/bin/python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8080

test:
	PYTHONPATH=$(PYTHONPATH) ./.venv/bin/python -m pytest tests/ -v
