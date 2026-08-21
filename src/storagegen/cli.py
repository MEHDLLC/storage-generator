"""Command line entry point.

    storagegen list
    storagegen options bin-shelf
    storagegen build bin-shelf --rows 4 --columns 2
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from . import generator as registry
from . import runner
from .options import OptionError, merge_sequence
from .presets import BIN_PRESETS
from .units import to_inch

# Importing the modules is what registers the generators.
from .generators import bin_shelf, fit_gauge  # noqa: F401


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="storagegen",
        description="Parametric generators for printable storage hardware.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="list the available generators")
    sub.add_parser("bins", help="list the bin presets")

    show = sub.add_parser("options", help="show one generator's options")
    show.add_argument("generator")

    for key, generator in registry.all_generators().items():
        build = sub.add_parser(
            key, help=generator.summary, description=generator.summary,
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )
        _add_common(build)
        generator.options.add_to_parser(build)

    args = parser.parse_args(argv)

    if args.command == "list":
        return _list_generators()
    if args.command == "bins":
        return _list_bins()
    if args.command == "options":
        return _show_options(args.generator)
    return _build(args)


def _add_common(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("Run")
    group.add_argument("--out", default="out", metavar="DIR",
                       help="where to write the run directory")
    group.add_argument("--format", default="stl,3mf", metavar="LIST",
                       help="comma separated: stl, 3mf")
    group.add_argument("--no-preview", action="store_true",
                       help="skip rendering the preview image")
    group.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                       help="set an option by name; repeatable")
    group.add_argument("--options-file", metavar="FILE",
                       help="JSON file of option values, applied before flags")
    group.add_argument("--slug", metavar="NAME",
                       help="override the output directory name")


def _list_generators() -> int:
    for key, generator in registry.all_generators().items():
        print(f"{key:12s}  {generator.title}")
        print(f"{'':12s}  {generator.summary}")
        print()
    return 0


def _list_bins() -> int:
    for key, spec in BIN_PRESETS.items():
        print(f"{key}")
        print(f"  {spec.label}")
        print(
            f"  {spec.length:.1f} x {spec.width:.1f} x {spec.height:.1f} mm "
            f"({to_inch(spec.length):.2f} x {to_inch(spec.width):.2f} x "
            f"{to_inch(spec.height):.2f} in)"
        )
        if spec.estimated_fields:
            print("  estimated: " + ", ".join(spec.estimated_fields))
        print()
    return 0


def _show_options(key: str) -> int:
    try:
        generator = registry.get(key)
    except KeyError as exc:
        print(exc, file=sys.stderr)
        return 2
    print(f"{generator.key} - {generator.title}\n")
    for group, options in generator.options.groups().items():
        print(group)
        for option in options:
            print(f"  {option.flag:<26} {option.help}")
            print(f"  {'':<26} default: {option.describe_default()}"
                  + (f"; one of {', '.join(option.choices)}"
                     if option.choices else ""))
        print()
    return 0


def _build(args: argparse.Namespace) -> int:
    generator = registry.get(args.command)
    known = {option.name for option in generator.options}

    supplied: dict[str, Any] = {}
    if args.options_file:
        supplied.update(json.loads(Path(args.options_file).read_text()))
    try:
        supplied.update(merge_sequence(args.set))
    except OptionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    supplied.update(
        {k: v for k, v in vars(args).items() if k in known}
    )

    try:
        result = runner.run(
            generator,
            supplied,
            out_root=Path(args.out),
            formats=[f.strip() for f in args.format.split(",") if f.strip()],
            with_preview=not args.no_preview,
            slug=args.slug,
        )
    except (OptionError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    _report(result)
    return 0


def _report(result: runner.RunResult) -> None:
    print(f"{result.manifest['listing']['title']}\n")
    for part in result.manifest["parts"]:
        width, depth, height = part["size_mm"]
        print(
            f"  {part['name']:<34} {width:6.1f} x {depth:6.1f} x {height:6.1f} mm"
            f"   {part['volume_cm3']:6.1f} cm3   {part['triangles']:>6d} tris"
        )
    print(
        f"\n  about {result.manifest['estimated_grams_solid']:.0f} g if printed "
        "solid; supports: none"
    )
    for note in result.manifest["notes"]:
        print(f"  note: {note}")
    for warning in result.warnings:
        print(f"  warning: {warning}")
    print(f"\nwrote {len(result.files)} files to {result.directory}")
    for name in result.manifest["files"]:
        print(f"  {name}")


if __name__ == "__main__":
    raise SystemExit(main())
