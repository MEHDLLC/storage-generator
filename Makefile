PYTHON ?= python3

.PHONY: test demo patterns fold advent batch verify clean

test:
	$(PYTHON) -m unittest discover -s tests -v

demo:
	PYTHONPATH=src $(PYTHON) -m storagegen.cli bin-shelf --out out
	PYTHONPATH=src $(PYTHON) -m storagegen.cli fit-gauge --out out
	PYTHONPATH=src $(PYTHON) -m storagegen.cli folding-bin --out out
	PYTHONPATH=src $(PYTHON) -m storagegen.cli advent-calendar --out out

patterns:
	$(PYTHON) tools/pattern_sheet.py

fold:
	$(PYTHON) tools/fold_sheet.py

advent:
	$(PYTHON) tools/advent_sheet.py

batch:
	PYTHONPATH=src $(PYTHON) -m storagegen.cli batch --out out --keep-going

verify:
	PYTHONPATH=src $(PYTHON) -m storagegen.cli verify out

clean:
	rm -rf out
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
