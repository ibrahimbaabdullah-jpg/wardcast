PYTHON ?= python3.12
VENV ?= .venv
PY := $(VENV)/bin/python
PNPM ?= pnpm

.PHONY: help install frontend demo serve download prepare train reproduce test lint browsers e2e docker

help:
	@printf '%s\n' \
	  'install    Create the Python environment and install locked Python/JS dependencies' \
	  'demo       Build the frontend and serve the bundled demo on 127.0.0.1:8000' \
	  'serve      Serve existing frontend build and model artifacts' \
	  'frontend   Build the TypeScript/React frontend' \
	  'download   Download and checksum the pinned NHS source publications' \
	  'prepare    Validate raw files and produce the normalized panel' \
	  'train      Rebuild rolling evaluation and demo/model artifacts' \
	  'reproduce  Run download, preparation, and training' \
	  'test       Run Python tests' \
	  'lint       Check Python source and tests with Ruff' \
	  'browsers   Install Playwright Chromium for browser tests' \
	  'e2e        Run browser tests (start the API with make serve first)' \
	  'docker     Build and run the demo using Docker Compose'

install:
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install -r requirements.lock
	$(PY) -m pip install --no-deps -e .
	$(PNPM) --dir frontend install --frozen-lockfile

frontend:
	$(PNPM) --dir frontend build

demo: frontend
	$(PY) -m wardcast serve --host 127.0.0.1 --port 8000

serve:
	$(PY) -m wardcast serve --host 127.0.0.1 --port 8000

download:
	$(PY) -m wardcast download

prepare:
	$(PY) -m wardcast prepare

train:
	$(PY) -m wardcast train

reproduce:
	$(PY) -m wardcast reproduce

test:
	@wardcast_runtime="$$($(PY) -c 'import importlib.util, pathlib, sys; spec = importlib.util.find_spec("sklearn"); runtime = pathlib.Path(spec.origin).parent / ".dylibs" if spec else pathlib.Path("/nonexistent"); print(runtime if sys.platform == "darwin" and (runtime / "libomp.dylib").is_file() else "")')"; \
	if [ -n "$$wardcast_runtime" ]; then export DYLD_LIBRARY_PATH="$$wardcast_runtime$${DYLD_LIBRARY_PATH:+:$$DYLD_LIBRARY_PATH}"; fi; \
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check src tests

browsers:
	$(PNPM) --dir frontend exec playwright install chromium

e2e:
	$(PNPM) --dir frontend test:e2e

docker:
	docker compose up --build
