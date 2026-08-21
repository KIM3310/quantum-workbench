SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python
VENV_STAMP := $(VENV)/.installed-dev
PYTHON_MIN_VERSION := 3.11
PYTHON_CANDIDATES := $(VENV_PYTHON) python3.13 python3.12 python3.11 python3
PYTHON ?= $(shell for py in $(PYTHON_CANDIDATES); do \
	if command -v $$py >/dev/null 2>&1 && $$py -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then \
		command -v $$py; \
		break; \
	fi; \
done)
CF_PAGES_PROJECT ?= quantum-workbench

.PHONY: check-python install lint test repository-verify verify deploy-pages

check-python:
	@if [ -z "$(PYTHON)" ]; then \
		echo "Python $(PYTHON_MIN_VERSION)+ is required." >&2; \
		echo "Install Python $(PYTHON_MIN_VERSION)+ or run: make PYTHON=/path/to/python$(PYTHON_MIN_VERSION) <target>" >&2; \
		exit 1; \
	fi
	$(PYTHON) -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else "Python 3.11+ is required")'

$(VENV_PYTHON): check-python
	@if [ ! -x "$(VENV_PYTHON)" ] || ! $(VENV_PYTHON) -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >/dev/null 2>&1; then \
		rm -rf $(VENV); \
		$(PYTHON) -m venv $(VENV); \
	fi

$(VENV_STAMP): pyproject.toml $(VENV_PYTHON)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -e ".[dev]"
	touch $(VENV_STAMP)

install: $(VENV_STAMP)

lint: install
	$(VENV_PYTHON) -m ruff check app tests scripts
	$(VENV_PYTHON) -m ruff format --check app tests scripts

test: install
	$(VENV_PYTHON) -m pytest -q

repository-verify:
	$(PYTHON) scripts/validate_repository_surface.py
	$(PYTHON) scripts/validate_architecture_blueprint.py

verify: lint test repository-verify

deploy-pages:
	npx --yes wrangler@latest pages deploy site --project-name $(CF_PAGES_PROJECT)
