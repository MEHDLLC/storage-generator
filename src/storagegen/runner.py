"""Runs a generator end to end: build, export, render, describe, record."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from . import mesh_io, preview
from .generator import MATERIAL_DENSITY, BuildResult, Generator
from .listing import Listing, build_listing

DEFAULT_FORMATS = ("stl", "3mf")
APPLICATION = "storage-generator"


@dataclass
class RunResult:
    generator: str
    slug: str
    directory: Path
    files: list[Path] = field(default_factory=list)
    build: BuildResult | None = None
    listing: Listing | None = None
    manifest: dict[str, Any] = field(default_factory=dict)

    @property
    def warnings(self) -> list[str]:
        return list(self.build.report.warnings) if self.build else []


def run(generator: Generator, supplied: dict[str, Any] | None = None,
        out_root: Path = Path("out"), formats: Iterable[str] = DEFAULT_FORMATS,
        with_preview: bool = True, slug: str | None = None) -> RunResult:
    formats = tuple(dict.fromkeys(f.lower() for f in formats))
    unknown = set(formats) - {"stl", "3mf"}
    if unknown:
        raise ValueError(
            "unsupported format(s): " + ", ".join(sorted(unknown))
            + ". Supported: stl, 3mf"
        )

    opt = generator.options.resolve(supplied)
    result = generator.build(opt)
    # Describe what was built, which is not always what was asked for.
    opt = result.effective_options or opt

    slug = slug or generator.slug(opt)
    directory = out_root / slug
    directory.mkdir(parents=True, exist_ok=True)

    files: list[Path] = []
    if "stl" in formats:
        for part in result.parts:
            files.append(mesh_io.write_stl(directory / f"{part.name}.stl", part))

    listing = build_listing(generator, opt, result)

    if "3mf" in formats:
        files.append(
            mesh_io.write_3mf(
                directory / f"{slug}.3mf",
                list(result.parts),
                {
                    "Title": listing.title,
                    "Designer": APPLICATION,
                    "Description": listing.summary,
                    "Application": APPLICATION,
                },
            )
        )

    if with_preview and len(result.parts):
        files.append(
            preview.render_scene(directory / "preview.png", result.parts.parts)
        )
        if result.context_parts:
            files.append(
                preview.render_scene(
                    directory / "preview-in-use.png",
                    result.parts.parts,
                    result.context_parts,
                )
            )

    files += listing.write(directory)

    manifest_path = directory / "manifest.json"
    files.append(manifest_path)
    manifest = _manifest(generator, opt, result, listing, slug, files, directory)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return RunResult(
        generator=generator.key,
        slug=slug,
        directory=directory,
        files=files,
        build=result,
        listing=listing,
        manifest=manifest,
    )


def _manifest(generator: Generator, opt: dict[str, Any], result: BuildResult,
              listing: Listing, slug: str, files: list[Path],
              directory: Path) -> dict[str, Any]:
    density = MATERIAL_DENSITY.get(opt.get("material", "pla"), 1.24)
    volume = result.total_volume_cm3
    return {
        "generator": generator.key,
        "generator_title": generator.title,
        "slug": slug,
        "options": _jsonable(opt),
        "options_hash": _options_hash(generator.key, opt),
        "facts": _jsonable(result.facts),
        "parts": [
            {
                "name": part.name,
                "copies": part.copies,
                "size_mm": [round(v, 3) for v in part.size],
                "volume_cm3": round(part.volume_mm3 / 1000.0, 3),
                "triangles": part.triangle_count,
                "watertight_manifold": part.is_manifold(),
                "note": part.note,
            }
            for part in result.parts
        ],
        "estimated_grams_solid": round(volume * density, 1),
        "listing": {"title": listing.title, "summary": listing.summary,
                    "tags": listing.tags},
        "warnings": result.report.warnings,
        "notes": result.report.notes,
        "print_notes": result.print_notes,
        "files": sorted(str(f.relative_to(directory)) for f in files),
    }


def _options_hash(key: str, opt: dict[str, Any]) -> str:
    payload = json.dumps({"generator": key, "options": _jsonable(opt)},
                         sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, float):
        return round(value, 4)
    return value
