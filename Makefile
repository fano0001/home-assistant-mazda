\
PYTHON ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest

.PHONY: venv deps deps-ha test testv test-ha cov cov-html clean

venv:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip

deps: venv
	$(PIP) install pytest pytest-asyncio aiohttp pytest-aiohttp pytest-cov

deps-ha: deps
	$(PIP) install homeassistant

test: deps
	PYTHONPATH=. $(PYTEST) -q

testv: deps
	PYTHONPATH=. $(PYTEST) -vv -s

test-ha: deps-ha
	PYTHONPATH=. $(PYTEST) -q

cov: deps
	PYTHONPATH=. $(PYTEST) --cov=custom_components/mazda_cs --cov-report=term-missing

cov-html: deps
	PYTHONPATH=. $(PYTEST) --cov=custom_components/mazda_cs --cov-report=html

clean:
	rm -rf .pytest_cache .coverage htmlcov $(VENV)
