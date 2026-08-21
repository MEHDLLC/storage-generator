"""Fit gauge: measure the two numbers the rack actually depends on.

A hanging rack lives or dies on the bin's width just below its rim and how
far the rim stands proud of that.  Neither number is published for any bin I
know of, and a caliper deep enough to reach across a tote is not something
most people own.

So this prints a stepped taper gauge instead.  Push the bin into the mouth
until it stops; each step is one millimetre narrower than the last, so the
step it stops on *is* the measurement.  Do it twice -- once over the rim,
once with the gauge held flat against the underside of the rim -- and you
have the bin's width and its body width.  Half the difference is the rim
overhang.

It also prints a short slice of the real rack at the span those numbers
imply, so the fit can be felt in ten minutes rather than after a six-hour
print.
"""

from __future__ import annotations

from typing import Any

from .. import geom
from ..generator import BuildResult, Generator, register
from ..mesh_io import PartSet
from ..options import Option, OptionSet, Report
from ..presets import DEFAULT_BIN, BinSpec, preset_keys
from ..units import mm_in

PIP_HEIGHT = 1.0
PIP_DEPTH = 1.4


OPTIONS = OptionSet([
    Option("bin", DEFAULT_BIN, "Bin preset the gauge is centred on",
           kind="choice", choices=preset_keys(), group="Bin fit"),
    Option("bin_width", None, "Override the bin's width across the rails",
           unit=" mm", minimum=20, maximum=600, group="Bin fit"),
    Option("bin_length", None, "Override the bin's length", unit=" mm",
           minimum=20, maximum=600, group="Bin fit"),
    Option("bin_height", None, "Override the bin's height", unit=" mm",
           minimum=15, maximum=400, group="Bin fit"),
    Option("lip_overhang", None, "Override the expected rim overhang",
           unit=" mm", minimum=0.5, maximum=25, group="Bin fit"),
    Option("lip_thickness", None, "Override the rim flange thickness",
           unit=" mm", minimum=0.5, maximum=25, group="Bin fit"),
    Option("bin_taper", None, "Override the bin's wall draft angle", unit=" deg",
           minimum=0, maximum=20, group="Bin fit"),

    Option("range_above", 4.0, "How far above the bin's width the gauge starts",
           unit=" mm", minimum=1, maximum=40, group="Gauge"),
    Option("range_below", 4.0,
           "How far below the expected body width the gauge runs", unit=" mm",
           minimum=1, maximum=40, group="Gauge"),
    Option("step", 1.0, "Width difference between neighbouring steps",
           unit=" mm", minimum=0.25, maximum=4, group="Gauge"),
    Option("step_length", 6.0, "How far each step runs, front to back",
           unit=" mm", minimum=2, maximum=30, group="Gauge"),
    Option("gauge_thickness", 4.0, "Gauge plate thickness", unit=" mm",
           minimum=2, maximum=12, group="Gauge"),
    Option("gauge_margin", 12.0, "Plate material around the slot", unit=" mm",
           minimum=5, maximum=40, group="Gauge"),

    Option("rail_sample", True, "Also print a short slice of the real rack",
           kind="bool", group="Rail sample"),
    Option("sample_length", 40.0, "Depth of the rail sample", unit=" mm",
           minimum=15, maximum=150, group="Rail sample"),
    Option("sample_span_offset", 0.0,
           "Shift the sample's rail span, to try a tighter or looser fit",
           unit=" mm", minimum=-10, maximum=10, group="Rail sample"),
    Option("side_clearance", 0.5, "Air between the bin wall and each rail",
           unit=" mm", minimum=0.0, maximum=5, group="Rail sample"),
    Option("wall", 3.0, "Side panel thickness in the sample", unit=" mm",
           minimum=1.2, maximum=12, group="Rail sample"),
    Option("rail_width", 7.0, "Rail reach in the sample", unit=" mm",
           minimum=2.0, maximum=40, group="Rail sample"),
    Option("rail_thickness", 4.0, "Rail thickness in the sample", unit=" mm",
           minimum=1.5, maximum=25, group="Rail sample"),

    Option("material", "pla", "Filament, used for the weight estimate only",
           kind="choice", choices=("pla", "petg", "abs", "asa"), group="Output"),
])


class FitGaugeGenerator(Generator):
    key = "fit-gauge"
    title = "Bin fit gauge"
    summary = (
        "A stepped taper gauge that reads a bin's width and rim overhang "
        "without a caliper, plus a short slice of the rack to try the fit on."
    )
    tags = ("gauge", "measuring tool", "calibration", "bin rack", "parametric",
            "no supports")
    options = OPTIONS

    def build(self, opt: dict[str, Any]) -> BuildResult:
        from .bin_shelf import resolve_bin

        report = Report()
        spec = resolve_bin(opt, report)
        steps = _steps(spec, opt)
        _check_range(spec, steps, opt)

        parts = PartSet()
        parts.add(
            f"fit-gauge_{spec.key}",
            _gauge(steps, opt),
            note=(
                f"Reads {steps[0]:.1f} mm down to {steps[-1]:.1f} mm in "
                f"{opt['step']:g} mm steps"
            ),
        )
        if opt["rail_sample"]:
            parts.add(
                f"rail-sample_{spec.key}",
                _rail_sample(spec, opt),
                note="A slice of the real rack at the span these numbers imply",
            )

        span = spec.body_width + 2 * opt["side_clearance"] + opt["sample_span_offset"]
        facts = {
            "bin_key": spec.key,
            "bin_label": spec.label,
            "bin_short_label": spec.short_label,
            "bin_source": spec.source,
            "bin_fully_measured": spec.fully_measured,
            "bin_estimated_fields": list(spec.estimated_fields),
            "bin_notes": spec.notes,
            "bin_outside_mm": [round(spec.length, 2), round(spec.width, 2),
                               round(spec.height, 2)],
            "step_widths_mm": [round(w, 2) for w in steps],
            "expected_rim_width_mm": round(spec.width, 2),
            "expected_body_width_mm": round(spec.body_width, 2),
            "sample_rail_span_mm": round(span, 2),
            "supports_required": False,
        }
        return BuildResult(
            parts=parts,
            effective_options=opt,
            report=report,
            facts=facts,
            highlights=[
                f"Reads any width from {mm_in(steps[0])} down to "
                f"{mm_in(steps[-1])}",
                f"{len(steps)} steps, {opt['step']:g} mm apart, with a raised "
                "pip every fifth step so they are easy to count",
                "No caliper needed, and nothing to assemble",
                "Prints flat with no supports in well under an hour",
            ],
            print_notes=[
                "Print flat on the bed as supplied. No supports.",
                "Use the same filament and profile you will print the rack "
                "with, so both parts land the same way off nominal.",
                "0.2 mm layers and 3 perimeters is plenty. Do not scale it.",
            ],
        )

    def slug(self, opt: dict[str, Any]) -> str:
        return f"fit-gauge_{opt['bin']}"

    def listing_title(self, opt: dict[str, Any], result: BuildResult) -> str:
        return (
            f"{result.facts['bin_short_label']} Fit Gauge - Measure Rim "
            "Overhang Without a Caliper - STL + 3MF"
        )

    def listing_body(self, opt: dict[str, Any], result: BuildResult) -> list[str]:
        facts = result.facts
        steps = facts["step_widths_mm"]
        return [
            "Print this before you print a rack. It answers the only two "
            "questions a hanging rack really asks of a bin: how wide is it, "
            "and how far does its rim stand proud of its wall?",
            "**How to use it.** Push the bin into the wide end of the slot "
            "until it stops. Each step is "
            f"{opt['step']:g} mm narrower than the one before it, so the step "
            "the bin stops on is the measurement. Take the reading twice:",
            "1. **Over the rim** - let the rim itself run into the slot. That "
            "is the bin's overall width.\n"
            "2. **Under the rim** - hold the gauge flat against the underside "
            "of the rim so the slot passes over the bin's wall instead. That "
            "is the body width.",
            "Half the difference between the two readings is the rim overhang. "
            "Feed both numbers to the rack generator with `--bin-width` and "
            "`--lip-overhang` and the rails will be cut to your bin rather "
            "than to a typical one.",
            "**Reading the steps.** The mouth is "
            f"{steps[0]:.1f} mm. Every step toward the closed end takes "
            f"{opt['step']:g} mm off, down to {steps[-1]:.1f} mm at the end. A "
            "raised pip sits beside every fifth step so you can count them at "
            "a glance; the table below gives every step.",
            _step_table(steps, opt),
        ]


def _check_range(spec: BinSpec, steps: list[float], opt: dict[str, Any]) -> None:
    """The gauge is only useful if it brackets both readings it has to take.

    It must reach past the bin's rim at the open end and past the expected
    body width at the closed end, with a step of margin either way -- a gauge
    that bottoms out on the first or last step tells you nothing except that
    the answer is somewhere off the end of it.
    """
    step = opt["step"]
    if len(steps) < 4:
        raise ValueError(
            f"That range and step size leave only {len(steps)} steps. Widen "
            "--range-above / --range-below, or reduce --step."
        )
    if steps[0] < spec.width + step:
        raise ValueError(
            f"The gauge starts at {steps[0]:.1f} mm, which is not clear of the "
            f"bin's {spec.width:.1f} mm rim. Raise --range-above to at least "
            f"{step + 1:.0f} mm."
        )
    if steps[-1] > spec.body_width - step:
        raise ValueError(
            f"The gauge stops at {steps[-1]:.1f} mm, before the expected "
            f"{spec.body_width:.1f} mm body width. Raise --range-below to at "
            f"least {step + 1:.0f} mm."
        )


def _steps(spec: BinSpec, opt: dict[str, Any]) -> list[float]:
    step = opt["step"]
    # Snap the mouth to a whole multiple of the step so every reading is a
    # round number worth writing down, instead of 87.82 mm.
    top = round((spec.width + opt["range_above"]) / step) * step
    bottom = spec.body_width - opt["range_below"]
    count = int(round((top - bottom) / step)) + 1
    return [round(top - index * step, 4) for index in range(max(count, 0))]


def _step_table(steps: list[float], opt: dict[str, Any]) -> str:
    lines = ["| Step from the mouth | Width |", "|---|---|"]
    for index, width in enumerate(steps):
        mark = " (pip)" if index % 5 == 0 else ""
        lines.append(f"| {index}{mark} | {width:.1f} mm |")
    return "\n".join(lines)


def _gauge(steps: list[float], opt: dict[str, Any]) -> geom.Solid:
    """A plate with a staircase slot cut in from the front edge."""
    step_len = opt["step_length"]
    thickness = opt["gauge_thickness"]
    margin = opt["gauge_margin"]

    travel = len(steps) * step_len
    width = steps[0] + 2 * margin
    depth = travel + margin
    centre = width / 2.0

    plate = geom.box([width, depth, thickness])

    slot: list[geom.Solid] = []
    for index, step_width in enumerate(steps):
        y0 = index * step_len
        y1 = travel if index == len(steps) - 1 else y0 + step_len
        slot.append(
            geom.box(
                [step_width, y1 - y0, thickness + 2.0],
                at=[centre - step_width / 2.0, y0, -1.0],
            )
        )

    pips: list[geom.Solid] = []
    for index, step_width in enumerate(steps):
        if index % 5:
            continue
        length = 9.0 if index % 10 == 0 else 6.0
        x1 = centre - step_width / 2.0 - 2.0
        pips.append(
            geom.box(
                [length, PIP_DEPTH, PIP_HEIGHT + 0.4],
                at=[x1 - length, index * step_len, thickness - 0.4],
            )
        )

    # Break the two mouth corners so the bin is guided in rather than caught.
    lead = min(4.0, margin - 1.0, step_len)
    corners = [
        geom.prism_z(
            [(0.0, 0.0), (lead, 0.0), (0.0, lead)], -1.0, thickness + 1.0
        ),
        geom.prism_z(
            [(width, 0.0), (width, lead), (width - lead, 0.0)],
            -1.0, thickness + 1.0,
        ),
    ]
    return geom.difference(geom.union([plate], pips), slot, corners)


def _rail_sample(spec: BinSpec, opt: dict[str, Any]) -> geom.Solid:
    """A short, standalone slice of the rack: two rails and a back wall."""
    wall = opt["wall"]
    reach = opt["rail_width"]
    rail_t = opt["rail_thickness"]
    span = spec.body_width + 2 * opt["side_clearance"] + opt["sample_span_offset"]
    if span <= 2.0:
        raise ValueError(
            "sample_span_offset makes the rail span vanish; use a smaller "
            "negative offset."
        )

    depth = opt["sample_length"]
    below, above = rail_t + 4.0, 9.0
    height = below + above
    rail_top = below
    width = span + 2 * reach + 2 * wall

    panels = [
        geom.box([wall, depth, height]),
        geom.box([wall, depth, height], at=[width - wall, 0.0, 0.0]),
    ]
    back = geom.box([width, wall, height], at=[0.0, depth - wall, 0.0])

    left_face, right_face = wall, width - wall
    chamfer = min(rail_t, reach)
    # Reach into the side panels rather than stopping on their faces: solids
    # that meet on exactly one plane leave slivers along the seam.
    embed = 0.5
    rails = [
        geom.prism_y(
            [
                (left_face - embed, rail_top - rail_t),
                (left_face + reach - chamfer, rail_top - chamfer),
                (left_face + reach, rail_top),
                (left_face - embed, rail_top),
            ],
            0.0, depth,
        ),
        geom.prism_y(
            [
                (right_face + embed, rail_top - rail_t),
                (right_face + embed, rail_top),
                (right_face - reach, rail_top),
                (right_face - reach + chamfer, rail_top - chamfer),
            ],
            0.0, depth,
        ),
    ]
    return geom.union(panels, [back], rails)


register(FitGaugeGenerator())
