"""Turns a finished build into the words that go with it.

Every run drops a title and a full description next to the models, generated
from the same numbers the geometry was built from, so the copy cannot claim a
size the model does not have.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .generator import MATERIAL_DENSITY, BuildResult, Generator
from .units import mm_in


@dataclass
class Listing:
    title: str
    summary: str
    highlights: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    body_markdown: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def write(self, directory: Path) -> list[Path]:
        directory.mkdir(parents=True, exist_ok=True)
        md = directory / "listing.md"
        md.write_text(self.body_markdown, encoding="utf-8")
        js = directory / "listing.json"
        js.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        return [md, js]


def build_listing(generator: Generator, opt: dict[str, Any],
                  result: BuildResult) -> Listing:
    facts = result.facts
    title = generator.listing_title(opt, result)
    summary = generator.summary

    sections: list[str] = [f"# {title}", ""]
    sections += generator.listing_body(opt, result)
    sections.append("")

    sections.append("## Highlights")
    sections += [f"- {item}" for item in result.highlights]
    sections.append("")

    sections.append("## What you get")
    for part in result.parts:
        width, depth, height = part.size
        sections.append(
            f"- **{part.name}** - {width:.1f} x {depth:.1f} x {height:.1f} mm"
            + (f". {part.note}" if part.note else "")
        )
    sections.append(
        f"- STL and 3MF for every part. The 3MF carries millimetre units and "
        f"named objects, already arranged on the plate."
    )
    sections.append("- A rendered preview and this description.")
    sections.append("")

    sections.append("## Dimensions")
    sections.append(_dimension_table(facts, result, opt))
    sections.append("")

    if result.print_notes:
        sections.append("## Printing")
        sections += [f"- {note}" for note in result.print_notes]
        sections.append("")

    fit = _fit_section(facts)
    if fit:
        sections.append("## Fit")
        sections.append(fit)
        sections.append("")

    if result.report.warnings:
        sections.append("## Check before you print")
        sections += [f"- {w}" for w in result.report.warnings]
        sections.append("")

    sections.append("## Options used")
    sections.append(_options_table(generator, opt))
    sections.append("")

    sections.append("## Tags")
    sections.append(", ".join(generator.tags))
    sections.append("")

    return Listing(
        title=title,
        summary=summary,
        highlights=list(result.highlights),
        tags=list(generator.tags),
        body_markdown="\n".join(sections).rstrip() + "\n",
    )


def _dimension_table(facts: dict[str, Any], result: BuildResult,
                     opt: dict[str, Any]) -> str:
    rows: list[tuple[str, str]] = []
    if "outside_mm" in facts:
        width, depth, height = facts["outside_mm"]
        rows.append(("Outside width", mm_in(width)))
        rows.append(("Outside depth", mm_in(depth)))
        rows.append(("Outside height", mm_in(height)))
    if "bin_outside_mm" in facts:
        length, width, height = facts["bin_outside_mm"]
        rows.append(
            ("Bin it fits", f"{mm_in(length)} x {mm_in(width)} x {mm_in(height)}")
        )
    if "capacity" in facts:
        rows.append(("Bins held", str(facts["capacity"])))
    if "rail_span_mm" in facts:
        rows.append(("Rail span", mm_in(facts["rail_span_mm"])))
    if "rail_bearing_per_side_mm" in facts:
        rows.append(
            ("Rim carried per side", f"{facts['rail_bearing_per_side_mm']:.1f} mm")
        )
    if "level_pitch_mm" in facts:
        rows.append(("Level spacing", mm_in(facts["level_pitch_mm"])))
    if "days" in facts:
        rows.append(("Boxes", str(facts["days"])))
        w, d, h = facts["box_outside_mm"]
        rows.append(("Each box", f"{mm_in(w)} x {mm_in(d)} x {mm_in(h)}, "
                                 f"about {facts['box_inside_ml']:.0f} ml inside"))
        rows.append(("Keys and panels",
                     f"{facts['keys']} keys, {facts['panels_total']} panels"))

    density = MATERIAL_DENSITY.get(opt.get("material", "pla"), 1.24)
    volume = result.total_volume_cm3
    rows.append(
        (
            "Plastic",
            f"{volume:.0f} cm3 solid, about {volume * density:.0f} g of "
            f"{opt.get('material', 'pla').upper()} if printed solid; a normal "
            "walls-and-infill profile uses less",
        )
    )
    rows.append(("Supports", "none"))
    rows.append(("Units", "millimetres"))

    lines = ["| | |", "|---|---|"]
    lines += [f"| {name} | {value} |" for name, value in rows]
    return "\n".join(lines)


def _fit_section(facts: dict[str, Any]) -> str:
    if "bin_source" not in facts:
        return ""
    parts = [facts["bin_source"]]
    if not facts.get("bin_fully_measured", True):
        estimated = ", ".join(facts.get("bin_estimated_fields", []))
        parts.append(
            f"Estimated rather than published: {estimated}. Run the "
            "`fit-gauge` generator and print that first if you want the rails "
            "set from your own bin instead of from a typical value."
        )
    if facts.get("bin_notes"):
        parts.append(facts["bin_notes"])
    return "\n\n".join(parts)


def _options_table(generator: Generator, opt: dict[str, Any]) -> str:
    lines = ["| Option | Value | What it does |", "|---|---|---|"]
    for option in generator.options:
        if not option.listed:
            continue
        value = opt.get(option.name)
        if value is None:
            continue
        if option.kind == "bool":
            shown = "yes" if value else "no"
        elif option.kind in ("int", "float"):
            shown = f"{value:g}{option.unit}"
        else:
            shown = str(value)
        lines.append(f"| `{option.name}` | {shown} | {option.help} |")
    return "\n".join(lines)
