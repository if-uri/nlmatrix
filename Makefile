.PHONY: test check doctor-build doctor-test doctor-health clean

PYTHON ?= python3

doctor-build:
	$(PYTHON) -m compileall -q *.py

doctor-test:
	$(PYTHON) -m pytest -q

doctor-health:
	$(PYTHON) -c "import properties, transforms, twin_registry_sim"

test: doctor-test

check: doctor-build doctor-test doctor-health

clean:
	rm -rf .pytest_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
