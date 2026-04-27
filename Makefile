PYTHON ?= python3
VENV ?= .venv
VPY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
RUNPY := $(if $(wildcard $(VPY)),$(VPY),$(PYTHON))

.PHONY: backend-install frontend-install backend-dev frontend-dev frontend-build frontend-preview test test-backend smoke-api smoke smoke-backend check check-backend deploy-prod clean

backend-install:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -r backend/app/requirements.txt

frontend-install:
	cd frontend && npm install

backend-dev:
	$(RUNPY) backend/main.py

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

frontend-preview:
	cd frontend && npm run preview

test:
	PYTHONPATH=backend $(RUNPY) -m unittest discover -s backend/tests -p 'test_*.py' -v

test-backend: test

smoke-api:
	PYTHONPATH=backend $(RUNPY) -m unittest backend.tests.test_api_read_smoke -v

smoke-backend: test check-backend

smoke: smoke-api smoke-backend frontend-build

check-backend:
	PYTHONPATH=backend $(RUNPY) -m py_compile backend/main.py
	PYTHONPATH=backend $(RUNPY) -m compileall -q backend/app

check: test check-backend frontend-build

deploy-prod:
	./scripts/deploy_production.sh

clean:
	rm -rf frontend/dist
