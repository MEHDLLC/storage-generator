"""Base class and registry for generators."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .mesh_io import Part, PartSet
from .options import OptionSet, Report


@dataclass
class BuildResult:
    """Everything a single generator run produced, before it hits disk."""

    parts: PartSet
    # What the generator actually built with. Some options imply others -- a
    # wall-mounted rack needs a solid back to put keyholes in -- and the
    # manifest and listing must describe the model, not the request.
    effective_options: dict[str, Any] = field(default_factory=dict)
    # Things the printed parts hold -- the bins a rack carries. Rendered into
    # the previews so a listing shows the product in use, never exported.
    context_parts: list[Part] = field(default_factory=list)
    report: Report = field(default_factory=Report)
    facts: dict[str, Any] = field(default_factory=dict)
    highlights: list[str] = field(default_factory=list)
    print_notes: list[str] = field(default_factory=list)

    @property
    def total_volume_cm3(self) -> float:
        return sum(p.volume_mm3 * p.copies for p in self.parts) / 1000.0


class Generator:
    """One product family.

    Subclasses declare `key`, `title`, `summary`, `options`, and implement
    `build`.  Everything else -- CLI wiring, validation, export, listing copy,
    manifest -- is handled by the shared runner.
    """

    key: str = ""
    title: str = ""
    summary: str = ""
    tags: tuple[str, ...] = ()
    options: OptionSet = OptionSet([])

    def build(self, opts: dict[str, Any]) -> BuildResult:  # pragma: no cover
        raise NotImplementedError

    def slug(self, opts: dict[str, Any]) -> str:
        return self.key

    def listing_title(self, opts: dict[str, Any], result: BuildResult) -> str:
        return self.title

    def listing_body(self, opts: dict[str, Any], result: BuildResult) -> list[str]:
        """Generator-specific paragraphs inserted near the top of the listing."""
        return [self.summary]


_REGISTRY: dict[str, Generator] = {}


def register(generator: Generator) -> Generator:
    if not generator.key:
        raise ValueError("generator needs a key")
    _REGISTRY[generator.key] = generator
    return generator


def get(key: str) -> Generator:
    try:
        return _REGISTRY[key]
    except KeyError:
        raise KeyError(
            f"unknown generator {key!r}; available: " + ", ".join(sorted(_REGISTRY))
        ) from None


def all_generators() -> dict[str, Generator]:
    return dict(sorted(_REGISTRY.items()))


MATERIAL_DENSITY = {   # g/cm^3
    "pla": 1.24,
    "petg": 1.27,
    "abs": 1.04,
    "asa": 1.07,
}
