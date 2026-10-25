.PHONY: all test eval demo seed verify-audit anchor clean

PYTHON ?= python

all: test

seed:
	$(PYTHON) -m leash.db

test: seed
	$(PYTHON) -m pytest -v tests/

eval: seed
	$(PYTHON) -m eval.harness

demo: seed
	$(PYTHON) run_demo.py

verify-audit:
	$(PYTHON) leash_cli.py verify-audit

anchor:
	$(PYTHON) leash_cli.py anchor

clean:
	rm -rf data/*.db __pycache__ */__pycache__ .pytest_cache
