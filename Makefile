PYTHON ?= python3

.PHONY: test demo clean

test:
	$(PYTHON) -m unittest discover -s tests -v

demo:
	PYTHONPATH=src $(PYTHON) -m storagegen.cli bin-shelf --out out
	PYTHONPATH=src $(PYTHON) -m storagegen.cli fit-gauge --out out

clean:
	rm -rf out
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
