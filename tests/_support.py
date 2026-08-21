"""Shared setup: make `src` importable without installing the package."""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from storagegen import generator as registry  # noqa: E402
from storagegen.generators import bin_shelf, fit_gauge  # noqa: E402,F401


def build(key: str, **options):
    generator = registry.get(key)
    resolved = generator.options.resolve(options)
    return generator, resolved, generator.build(resolved)
