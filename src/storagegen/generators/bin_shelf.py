"""Bin rack: a shelf unit that carries tote bins hanging by their rims.

How it holds the bin
--------------------
Each level is a pair of rails running front-to-back, one down each side of
the opening.  The bin drops in between them and stops when the flange around
its rim lands on the rail tops, so the bin is supported on its two long
sides and nothing sits underneath it.  Sliding a bin out is a straight pull
toward you; there is no drawer, no runner, and nothing to wear out.

Why the fit is forgiving
------------------------
The rail span is set to the bin's width *just below the rim*, plus a little
clearance.  Because the bin's walls taper inward toward its base, a span that
is slightly too wide only lets the bin settle a millimetre lower until the
taper wedges against the rails, and a span that is slightly too narrow lets
it ride a little higher on the rim.  Both still carry the bin.  That is the
property that makes this design survive an imperfect guess at the rim
overhang -- and the `fit-gauge` generator exists to remove the guess.

Printing
--------
The rack prints standing up, exactly as modelled, with no support material.
Every rail cantilevers into the opening over a 45-degree underside, the
stacking ribs are chamfered, and the rail mouths flare outward at the front
so a bin guides itself in.  The only unsupported spans are the optional
front lip and top plate, which bridge one bay and are called out in the
print notes when you turn them on.
"""

from __future__ import annotations

import math
from typing import Any

from .. import geom
from ..generator import BuildResult, Generator, register
from ..mesh_io import Part, PartSet
from ..options import Option, OptionSet, Report
from ..presets import DEFAULT_BIN, BinSpec, get_bin, preset_keys
from ..units import mm_in

# Printed plastic shrinks and squishes; these are the fudge factors that keep
# mating printed features apart without making them sloppy.
RIB_FIT_GAP = 0.35          # per side, stacking rib in its socket
RIM_SIDE_GAP = 1.0          # minimum air between the bin's rim and a side panel
MIN_BEARING = 0.8           # least rim-on-rail contact per side worth shipping
RIB_EMBED = 0.6             # how far mating features sink into their parent
FLANGE_MIN_THICKNESS = 4.0  # the hanger flange carries the whole rack
# The widest flat span left at the top of a window. Short enough that every
# slicer bridges it cleanly, long enough that the window is not a triangle.
MAX_WINDOW_BRIDGE = 12.0


OPTIONS = OptionSet([
    # ---- which bin -------------------------------------------------------
    Option("bin", DEFAULT_BIN, "Bin preset to fit", kind="choice",
           choices=preset_keys(), group="Bin fit"),
    Option("bin_length", None, "Override bin length, its long axis",
           unit=" mm", minimum=20, maximum=600, group="Bin fit"),
    Option("bin_width", None, "Override bin width across the rails",
           unit=" mm", minimum=20, maximum=600, group="Bin fit"),
    Option("bin_height", None, "Override bin height, rim to base",
           unit=" mm", minimum=15, maximum=400, group="Bin fit"),
    Option("lip_overhang", None,
           "Override how far the rim flange stands proud of the bin wall",
           unit=" mm", minimum=0.5, maximum=25, group="Bin fit"),
    Option("lip_thickness", None, "Override the rim flange's vertical thickness",
           unit=" mm", minimum=0.5, maximum=25, group="Bin fit"),
    Option("bin_taper", None, "Override the bin's wall draft angle per side",
           unit=" deg", minimum=0, maximum=20, group="Bin fit"),
    Option("side_clearance", 0.5, "Air between the bin wall and each rail",
           unit=" mm", minimum=0.0, maximum=5, group="Bin fit"),
    Option("depth_clearance", 2.0, "Total front-to-back slop for the bin",
           unit=" mm", minimum=0.0, maximum=20, group="Bin fit"),
    Option("headroom", 10.0, "Clear space above each bin's rim",
           unit=" mm", minimum=0.0, maximum=100, group="Bin fit"),

    # ---- layout ----------------------------------------------------------
    Option("columns", 1, "Bins side by side", kind="int", minimum=1, maximum=6,
           group="Layout"),
    Option("rows", 3, "Levels of bins", kind="int", minimum=1, maximum=12,
           group="Layout"),

    # ---- structure -------------------------------------------------------
    Option("wall", 3.0, "Side panel thickness", unit=" mm", minimum=1.2,
           maximum=12, group="Structure"),
    Option("rail_width", 7.0, "How far each rail reaches into the opening",
           unit=" mm", minimum=2.0, maximum=40, group="Structure"),
    Option("rail_thickness", 4.0, "Rail depth below its bearing surface",
           unit=" mm", minimum=1.5, maximum=25, group="Structure"),
    Option("rail_style", "full", "Continuous rails, or just a pad at each end",
           kind="choice", choices=("full", "pads"), group="Structure"),
    Option("pad_length", 30.0, "Length of each rail pad when rail_style=pads",
           unit=" mm", minimum=8, maximum=200, group="Structure"),
    Option("rail_lead_in", 1.5, "How far the rail mouths flare open at the front",
           unit=" mm", minimum=0.0, maximum=8, group="Structure"),
    Option("back", "windowed",
           "Back of the rack. This is the member that ties the two sides "
           "together and stops the bins at a consistent depth.",
           kind="choice", choices=("windowed", "panel", "open"),
           group="Structure"),
    Option("back_thickness", 2.4, "Back panel thickness", unit=" mm",
           minimum=1.2, maximum=12, group="Structure"),
    Option("sides", "windowed",
           "Side panels: cut away between levels, or left solid",
           kind="choice", choices=("windowed", "solid"), group="Structure"),
    Option("front_stop", "tabs",
           "Front retention: none, corner tabs, a full lip, or a label plate",
           kind="choice", choices=("none", "tabs", "lip", "label"),
           group="Structure"),
    Option("stop_height", 5.0, "How high the front and back stops stand",
           unit=" mm", minimum=1.0, maximum=60, group="Structure"),
    Option("label_height", 18.0, "Height of the front plate when front_stop=label",
           unit=" mm", minimum=6, maximum=80, group="Structure"),
    Option("base", "open", "Bottom of the rack: open, or a closed floor",
           kind="choice", choices=("open", "plate"), group="Structure"),
    Option("base_thickness", 3.0, "Floor thickness when base=plate", unit=" mm",
           minimum=1.2, maximum=15, group="Structure"),
    Option("floor_gap", 4.0, "Clearance beneath the lowest bin", unit=" mm",
           minimum=0.0, maximum=100, group="Structure"),
    Option("top", "none", "Top of the rack: open, or a closed plate",
           kind="choice", choices=("none", "plate"), group="Structure"),
    Option("top_thickness", 3.0, "Top plate thickness when top=plate", unit=" mm",
           minimum=1.2, maximum=15, group="Structure"),
    Option("chamfer", 1.2, "Edge break on the outer front and back corners",
           unit=" mm", minimum=0.0, maximum=8, group="Structure"),

    # ---- features --------------------------------------------------------
    Option("stackable", True, "Ribs on top and sockets underneath so racks stack",
           kind="bool", group="Features"),
    Option("stack_rib_height", 3.0, "Height of the stacking ribs", unit=" mm",
           minimum=1.0, maximum=12, group="Features"),
    Option("wall_mount", False,
           "Add a keyhole hanger flange above a full back panel", kind="bool",
           group="Features"),
    Option("mount_flange_height", 30.0, "Height of the wall-mount flange",
           unit=" mm", minimum=18, maximum=120, group="Features"),
    Option("keyhole_screw", 4.2, "Screw shank diameter for the keyholes",
           unit=" mm", minimum=2.5, maximum=8, group="Features"),
    Option("keyhole_head", 9.0, "Screw head diameter for the keyholes",
           unit=" mm", minimum=5, maximum=16, group="Features"),

    # ---- output ----------------------------------------------------------
    Option("material", "pla", "Filament, used for the weight estimate only",
           kind="choice", choices=("pla", "petg", "abs", "asa"), group="Output"),
    Option("bed_x", 256.0, "Printer bed width, for the fit check", unit=" mm",
           minimum=50, maximum=1200, group="Output", listed=False),
    Option("bed_y", 256.0, "Printer bed depth, for the fit check", unit=" mm",
           minimum=50, maximum=1200, group="Output", listed=False),
    Option("bed_z", 256.0, "Printer build height, for the fit check", unit=" mm",
           minimum=50, maximum=1200, group="Output", listed=False),
])


class Layout:
    """Every derived dimension, computed once and read everywhere else."""

    def __init__(self, spec: BinSpec, opt: dict[str, Any]):
        self.spec = spec
        self.o = opt
        wall = opt["wall"]

        # --- across the rack -------------------------------------------
        self.span = spec.body_width + 2.0 * opt["side_clearance"]
        self.cell_inner = self.span + 2.0 * opt["rail_width"]
        self.pitch_x = self.cell_inner + wall
        self.width = opt["columns"] * self.cell_inner + (opt["columns"] + 1) * wall

        # --- front to back ---------------------------------------------
        self.front_t = wall if opt["front_stop"] != "none" else 0.0
        self.rear_t = opt["back_thickness"] if opt["back"] != "open" else 0.0
        self.cavity_len = spec.length + opt["depth_clearance"]
        self.depth = self.front_t + self.cavity_len + self.rear_t
        self.cavity_y0 = self.front_t
        self.cavity_y1 = self.front_t + self.cavity_len

        # --- up the rack -------------------------------------------------
        self.base_t = opt["base_thickness"] if opt["base"] == "plate" else 0.0
        self.top_t = opt["top_thickness"] if opt["top"] == "plate" else 0.0
        self.pitch_z = spec.height + opt["headroom"]
        self.rail_top_0 = self.base_t + opt["floor_gap"] + spec.hang_depth
        self.rail_tops = [
            self.rail_top_0 + i * self.pitch_z for i in range(opt["rows"])
        ]
        self.body_height = (
            self.rail_tops[-1] + spec.lip_thickness + opt["headroom"] + self.top_t
        )
        self.flange_height = (
            opt["mount_flange_height"] if opt["wall_mount"] else 0.0
        )
        self.height = self.body_height + self.flange_height

        # --- fit numbers worth reporting ---------------------------------
        self.bearing = spec.lip_overhang - opt["side_clearance"]
        self.rim_side_gap = (self.cell_inner - spec.width) / 2.0
        self.capacity = opt["columns"] * opt["rows"]

    def panel_x0(self, index: int) -> float:
        return index * self.pitch_x

    def cell_x0(self, column: int) -> float:
        """Inner face of the left-hand panel of a bay."""
        return self.panel_x0(column) + self.o["wall"]

    def cell_center(self, column: int) -> float:
        return self.cell_x0(column) + self.cell_inner / 2.0


class BinShelfGenerator(Generator):
    key = "bin-shelf"
    title = "Hanging bin rack"
    summary = (
        "A shelf unit that carries tote bins hanging by their rims on a pair "
        "of rails, so each bin pulls straight out with nothing underneath it."
    )
    tags = ("storage", "bin rack", "shelf", "organizer", "parametric",
            "print in place", "no supports", "stackable")
    options = OPTIONS

    # -- entry point ------------------------------------------------------

    def build(self, opt: dict[str, Any]) -> BuildResult:
        report = Report()
        spec = resolve_bin(opt, report)
        opt = dict(opt)
        _validate(spec, opt, report)
        layout = Layout(spec, opt)
        _check_fit(spec, layout, opt, report)

        solid = _assemble(spec, layout, opt)

        parts = PartSet()
        part = parts.add(
            _part_name(spec, opt),
            solid,
            note=f"{layout.capacity} bin rack, prints upright with no supports",
        )

        facts = _facts(spec, layout, opt)
        # Report what the slicer will actually see, ribs and flange included,
        # rather than the nominal body height.
        facts["outside_mm"] = [round(v, 2) for v in part.size]
        context = [Part("bins-in-place", geom.union(bin_solids(spec, layout, opt)))]
        return BuildResult(
            parts=parts,
            effective_options=opt,
            context_parts=context,
            report=report,
            facts=facts,
            highlights=_highlights(spec, layout, opt, part.size),
            print_notes=_print_notes(layout, opt),
        )

    def slug(self, opt: dict[str, Any]) -> str:
        return (
            f"bin-shelf_{opt['bin']}_{opt['columns']}x{opt['rows']}"
            f"_{opt['back']}-back_{opt['front_stop']}-front"
        )

    def listing_title(self, opt: dict[str, Any], result: BuildResult) -> str:
        facts = result.facts
        bins = facts["capacity"]
        grid = f"{opt['columns']}x{opt['rows']}"
        return (
            f"{facts['bin_short_label']} Rack - {grid} ({bins} bin"
            f"{'s' if bins != 1 else ''}) - Under-Rim Rails, "
            f"{'Stackable, ' if opt['stackable'] else ''}Support-Free STL + 3MF"
        )

    def listing_body(self, opt: dict[str, Any], result: BuildResult) -> list[str]:
        facts = result.facts
        paragraphs = [
            f"A {opt['columns']} x {opt['rows']} rack that holds "
            f"{facts['capacity']} {facts['bin_short_label']} bins. Each bin hangs "
            "from a pair of rails that catch it under the rim along its two "
            "long sides, so there is no shelf beneath the bin and nothing to "
            "clean out: every bin pulls straight toward you and lifts free.",
            "The rails set their spacing from the bin's width just below the "
            "rim. Because the bin's walls taper toward the base, the fit is "
            "self-correcting - a slightly wide span lets the bin settle until "
            "the taper wedges, a slightly narrow one lets it ride on the rim, "
            "and either way it is carried on a continuous bearing surface "
            "down both sides.",
            "It prints standing up in one piece with no support material. "
            "Rail undersides are cut back at 45 degrees, the rail mouths "
            "flare open at the front so bins guide themselves in, and the "
            "stacking ribs are chamfered so they self-align.",
        ]
        if not facts["bin_fully_measured"]:
            paragraphs.append(
                "Fit note: the bin's outside dimensions come from the "
                "manufacturer's published specification, but its rim overhang "
                "and wall draft are estimated. Print the matching fit gauge "
                "first if you want the rails set to your own measurements - "
                "it takes a few minutes and turns the estimate into a number."
            )
        return paragraphs


# ---------------------------------------------------------------------------
# bin resolution and validation
# ---------------------------------------------------------------------------


def resolve_bin(opt: dict[str, Any], report: Report) -> BinSpec:
    """Start from a preset and fold in any explicit overrides."""
    spec = get_bin(opt["bin"])
    overrides = {
        "length": opt.get("bin_length"),
        "width": opt.get("bin_width"),
        "height": opt.get("bin_height"),
        "lip_overhang": opt.get("lip_overhang"),
        "lip_thickness": opt.get("lip_thickness"),
        "taper_deg": opt.get("bin_taper"),
    }
    changes = {k: v for k, v in overrides.items() if v is not None}
    if changes:
        report.note(
            "Using measured overrides for: " + ", ".join(sorted(changes))
        )
    return spec.replace(**changes)


def _validate(spec: BinSpec, opt: dict[str, Any], report: Report) -> None:
    if spec.lip_overhang <= 0:
        raise ValueError(
            "This rack carries the bin under its rim, so the bin needs a rim "
            "that stands proud of its wall. Set --lip-overhang to a positive "
            "measurement."
        )

    needed_rail = spec.lip_overhang - opt["side_clearance"] + RIM_SIDE_GAP
    if opt["rail_width"] < needed_rail:
        raise ValueError(
            f"rail_width of {opt['rail_width']:.1f} mm is too narrow for a "
            f"{spec.lip_overhang:.1f} mm rim overhang: the bin's rim would "
            f"foul the side panels. Use at least {needed_rail:.1f} mm."
        )

    if spec.hang_depth <= 0:
        raise ValueError(
            "lip_thickness cannot be as tall as the whole bin; the bin has to "
            "hang below its own rim."
        )

    if opt["back"] == "open" and not (
        opt["base"] == "plate" and opt["top"] == "plate"
    ):
        raise ValueError(
            "With --back open there is nothing joining the two side panels, so "
            "the rack would print as two loose halves. Use --back windowed or "
            "--back panel, or brace it top and bottom with --base plate "
            "--top plate."
        )

    if opt["wall_mount"]:
        if opt["back"] != "panel":
            opt["back"] = "panel"
            report.note(
                "wall_mount needs something to put the keyholes in, so the "
                "back was switched to a full panel."
            )
        if opt["stackable"]:
            report.warn(
                "wall_mount and stackable together: the hanger flange stands "
                "above the top of the rack, so another rack cannot sit on it. "
                "Turn one of the two off unless you want the flange purely as "
                "a backstop."
            )


def _check_fit(spec: BinSpec, layout: Layout, opt: dict[str, Any],
               report: Report) -> None:
    if layout.bearing < MIN_BEARING:
        report.warn(
            f"Only {layout.bearing:.2f} mm of the rim would land on each rail. "
            "Reduce --side-clearance, or measure the rim overhang with the fit "
            "gauge before printing the whole rack."
        )
    if layout.rim_side_gap < RIM_SIDE_GAP:
        report.warn(
            f"Only {layout.rim_side_gap:.2f} mm of air between the bin's rim "
            "and the side panels. Widen --rail-width for an easier drop-in."
        )

    if opt["front_stop"] != "none":
        lift = opt["label_height"] if opt["front_stop"] == "label" else opt["stop_height"]
        if opt["headroom"] < lift + 2.0:
            report.warn(
                f"Front stops stand {lift:.1f} mm proud but there is only "
                f"{opt['headroom']:.1f} mm above each bin's rim, so a bin has to "
                "be tilted rather than lifted straight out. Raise --headroom to "
                f"at least {lift + 2.0:.0f} mm, or lower --stop-height."
            )

    if opt["rail_style"] == "pads" and opt["pad_length"] * 2 > layout.cavity_len:
        report.warn(
            "Rail pads are long enough to meet in the middle; --rail-style "
            "full would use no more plastic."
        )

    bed = (opt["bed_x"], opt["bed_y"], opt["bed_z"])
    size = (layout.width, layout.depth, layout.height)
    over = [
        f"{axis} {value:.0f} mm > {limit:.0f} mm"
        for axis, value, limit in zip("XYZ", size, bed)
        if value > limit
    ]
    if over:
        advice = (
            "Print it as shorter stackable modules and stack them"
            if opt["stackable"]
            else "Reduce --rows, or turn on --stackable and print modules"
        )
        report.warn(
            "Bigger than the bed you specified (" + "; ".join(over) + "). "
            + advice
            + "."
        )


# ---------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------


def bin_solids(spec: BinSpec, layout: Layout,
               opt: dict[str, Any]) -> list[geom.Solid]:
    """Every bin, sitting where the rails put it.

    Its rim underside rests on the rail tops and it is centred in its bay, so
    intersecting these against the rack is a direct test of whether the rack
    actually clears the bins it claims to hold.
    """
    bin_solid = spec.solid()
    y_center = layout.cavity_y0 + layout.cavity_len / 2.0
    return [
        bin_solid.translate([
            layout.cell_center(column),
            y_center,
            rail_top - spec.hang_depth,
        ])
        for column in range(opt["columns"])
        for rail_top in layout.rail_tops
    ]


def _assemble(spec: BinSpec, layout: Layout, opt: dict[str, Any]) -> geom.Solid:
    solids: list[geom.Solid] = []
    solids += _side_panels(layout, opt)
    solids += _rails(layout, opt)
    solids += _back_panel(layout, opt)
    solids += _front_stops(spec, layout, opt)
    solids += _base_plate(layout, opt)
    solids += _top_plate(layout, opt)
    solids += _mount_flange(layout, opt)
    if opt["stackable"]:
        solids += _stack_ribs(layout, opt)

    body = geom.union(solids)

    cutters: list[geom.Solid] = []
    if opt["back"] == "windowed":
        cutters += _back_windows(spec, layout, opt)
    if opt["sides"] == "windowed":
        cutters += _side_windows(spec, layout, opt)
    if opt["stackable"]:
        cutters += _stack_sockets(layout, opt)
    if opt["wall_mount"]:
        cutters += _keyholes(layout, opt)
    if opt["front_stop"] == "label":
        cutters += _label_recesses(layout, opt)
    cutters += _corner_chamfers(layout, opt)

    solid = geom.difference(body, cutters)
    _assert_one_piece(solid)
    return solid


def _assert_one_piece(solid: geom.Solid) -> None:
    """A rack that comes apart in the slicer is scrap, so prove it never does.

    Cheap to check and easy to break: several options remove cross members,
    and losing the last one leaves two side assemblies floating next to each
    other rather than a rack.
    """
    pieces = len(solid.decompose())
    if pieces != 1:
        raise ValueError(
            f"the rack came out as {pieces} disconnected pieces, which means "
            "no member ties the side panels together. This is a bug in the "
            "option combination you chose; please report the options used."
        )


def _side_panels(layout: Layout, opt: dict[str, Any]) -> list[geom.Solid]:
    """The vertical plates. Everything else hangs off these."""
    return [
        geom.box(
            [opt["wall"], layout.depth, layout.body_height],
            at=[layout.panel_x0(i), 0.0, 0.0],
        )
        for i in range(opt["columns"] + 1)
    ]


def _rails(layout: Layout, opt: dict[str, Any]) -> list[geom.Solid]:
    out: list[geom.Solid] = []
    thickness = opt["rail_thickness"]
    reach = opt["rail_width"]
    # The flare shifts the rail mouth outward into the side panel, so it
    # must not be able to reach the panel's outer face.
    lead = min(opt["rail_lead_in"], max(opt["wall"] - 0.4, 0.0))

    for column in range(opt["columns"]):
        left_face = layout.cell_x0(column)                      # panel inner face
        right_face = left_face + layout.cell_inner
        for rail_top in layout.rail_tops:
            z0, z1 = rail_top - thickness, rail_top
            chamfer = min(thickness, reach) * 0.999
            # Left rail: solid from the panel face inward, undercut at 45.
            left_profile = [
                (left_face, z1),
                (left_face + reach, z1),
                (left_face + reach - chamfer, z1 - chamfer),
                (left_face, z0),
            ]
            right_profile = [
                (right_face, z1),
                (right_face, z0),
                (right_face - reach + chamfer, z1 - chamfer),
                (right_face - reach, z1),
            ]
            for profile, direction in ((left_profile, 1.0), (right_profile, -1.0)):
                out.extend(
                    _rail_runs(profile, direction, layout, opt, lead, z0, z1)
                )
    return out


def _rail_runs(profile, direction: float, layout: Layout, opt: dict[str, Any],
               lead: float, z0: float, z1: float) -> list[geom.Solid]:
    """One rail, optionally split into end pads, with a flared mouth."""
    segments: list[tuple[float, float]] = []
    if opt["rail_style"] == "pads":
        pad = min(opt["pad_length"], layout.depth / 2.0)
        segments = [(0.0, pad), (layout.depth - pad, layout.depth)]
    else:
        segments = [(0.0, layout.depth)]

    solids = [geom.prism_y(profile, y0, y1) for y0, y1 in segments]

    if lead > 0:
        # Flare the mouth: hull a thin slice of the rail at the front, shifted
        # outward, to a slice at lead-in depth in its true position. A bin
        # nudged off-centre is steered in instead of catching the rail tip.
        depth = max(2.5 * lead, 6.0)
        slice_thickness = 0.4
        mouth = geom.prism_y(profile, 0.0, slice_thickness).translate(
            [-direction * lead, 0.0, 0.0]
        )
        inner = geom.prism_y(profile, depth, depth + slice_thickness)
        solids.append(geom.Solid.batch_hull([mouth, inner]))
    return solids


def _back_panel(layout: Layout, opt: dict[str, Any]) -> list[geom.Solid]:
    """The back is the rack's spine.

    It is the only member that crosses from one side panel to the other, it
    prints as a plain vertical wall with nothing to bridge, and it doubles as
    the backstop that sets every bin to the same depth.
    """
    if opt["back"] == "open":
        return []
    return [
        geom.box(
            [layout.width, layout.rear_t, layout.body_height],
            at=[0.0, layout.depth - layout.rear_t, 0.0],
        )
    ]


def _back_windows(spec: BinSpec, layout: Layout,
                  opt: dict[str, Any]) -> list[geom.Solid]:
    """Slots that take most of the weight out of the back panel.

    Each slot is a rectangle with its corners taken off at 45 degrees. The top
    corners are the reason: a plain rectangular window leaves its whole top
    edge bridging across open air part-way up a wall, while 45-degree corners
    reduce that to a short flat span any slicer bridges without support.
    """
    margin_x, margin_z, rib = 9.0, 8.0, 8.0
    min_rect = 8.0
    y0 = layout.depth - layout.rear_t - 1.0
    y1 = layout.depth + 1.0

    out = []
    for column in range(opt["columns"]):
        x_left = layout.cell_x0(column) + margin_x
        available = layout.cell_inner - 2 * margin_x
        if available <= 12.0:
            continue
        for rail_top in layout.rail_tops:
            z_bottom = rail_top - spec.hang_depth + margin_z
            z_apex = rail_top - margin_z
            height = z_apex - z_bottom
            if height <= min_rect + 4.0:
                continue
            count, slot_w = _slot_layout(available, height, rib, min_rect)
            if count == 0:
                continue
            for index in range(count):
                x0 = x_left + index * (slot_w + rib)
                out.append(
                    geom.prism_y(
                        _window_profile(x0, x0 + slot_w, z_bottom, z_apex),
                        y0, y1,
                    )
                )
    return out



def _window_profile(a0: float, a1: float, b0: float, b1: float) -> list:
    """A rectangle with 45-degree corners, in whichever plane the caller uses."""
    width, height = a1 - a0, b1 - b0
    top = max((width - MAX_WINDOW_BRIDGE) / 2.0, 0.0)
    top = min(top, height * 0.45, width * 0.45)
    bottom = min(top * 0.6, height * 0.25)
    return [
        (a0 + bottom, b0),
        (a1 - bottom, b0),
        (a1, b0 + bottom),
        (a1, b1 - top),
        (a1 - top, b1),
        (a0 + top, b1),
        (a0, b1 - top),
        (a0, b0 + bottom),
    ]


def _side_windows(spec: BinSpec, layout: Layout,
                  opt: dict[str, Any]) -> list[geom.Solid]:
    """The same gabled slots down the side panels.

    Solid sides are most of the plastic in a rack this shape, and most of that
    plastic is doing nothing: the load runs straight down the panel edges. The
    slots sit in the band beside each bin's body, clear of the rails above them,
    and leave upright ribs between the levels to carry the weight.
    """
    margin_y = 8.0
    # Stay clear of the rail's 45-degree underside, which reaches one rail
    # thickness below its bearing surface.
    margin_z = max(8.0, opt["rail_thickness"] + 4.0)
    rib, min_rect = 9.0, 10.0
    available = layout.depth - 2 * margin_y - layout.rear_t
    if available <= 14.0:
        return []

    out = []
    for index in range(opt["columns"] + 1):
        x0 = layout.panel_x0(index) - 1.0
        x1 = x0 + opt["wall"] + 2.0
        for rail_top in layout.rail_tops:
            z_bottom = rail_top - spec.hang_depth + margin_z
            z_apex = rail_top - margin_z
            height = z_apex - z_bottom
            if height <= min_rect + 4.0:
                continue
            count, slot_w = _slot_layout(available, height, rib, min_rect)
            if count == 0:
                continue
            for slot in range(count):
                y0 = margin_y + slot * (slot_w + rib)
                out.append(
                    geom.prism_x(
                        _window_profile(y0, y0 + slot_w, z_bottom, z_apex),
                        x0, x1,
                    )
                )
    return out


def _slot_layout(available: float, height: float, rib: float,
                 min_rect: float) -> tuple[int, float]:
    """Fit as many ~30 mm slots across `available` as leave a usable opening."""
    target = 30.0
    count = max(1, round(available / (target + rib))) or 1
    for _ in range(8):
        slot_w = (available - (count - 1) * rib) / count
        if slot_w <= 0:
            return 0, 0.0
        if slot_w >= min_rect and height >= min_rect:
            return count, slot_w
        count -= 1
        if count < 1:
            return 0, 0.0
    return 0, 0.0


def _front_stops(spec: BinSpec, layout: Layout,
                 opt: dict[str, Any]) -> list[geom.Solid]:
    """What keeps a bin from walking out of the front."""
    style = opt["front_stop"]
    if style == "none":
        return []
    out = []
    y0, y1 = 0.0, layout.front_t
    height = opt["label_height"] if style == "label" else opt["stop_height"]

    for column in range(opt["columns"]):
        left_face = layout.cell_x0(column)
        right_face = left_face + layout.cell_inner
        for rail_top in layout.rail_tops:
            if style == "tabs":
                spans = (
                    (left_face, left_face + opt["rail_width"]),
                    (right_face - opt["rail_width"], right_face),
                )
            else:
                spans = ((left_face, right_face),)
            for x0, x1 in spans:
                out.append(
                    geom.box([x1 - x0, y1 - y0, height], at=[x0, y0, rail_top])
                )
    return out


def _label_recesses(layout: Layout, opt: dict[str, Any]) -> list[geom.Solid]:
    """A shallow pocket in the front plate to drop a stick-on label into."""
    inset_x, inset_z, depth = 5.0, 3.0, 0.8
    out = []
    for column in range(opt["columns"]):
        left_face = layout.cell_x0(column)
        right_face = left_face + layout.cell_inner
        for rail_top in layout.rail_tops:
            out.append(
                geom.box(
                    [
                        (right_face - left_face) - 2 * inset_x,
                        depth,
                        opt["label_height"] - 2 * inset_z,
                    ],
                    at=[left_face + inset_x, -0.01, rail_top + inset_z],
                )
            )
    return out


def _base_plate(layout: Layout, opt: dict[str, Any]) -> list[geom.Solid]:
    if opt["base"] != "plate":
        return []
    return [geom.box([layout.width, layout.depth, layout.base_t])]


def _top_plate(layout: Layout, opt: dict[str, Any]) -> list[geom.Solid]:
    if opt["top"] != "plate":
        return []
    return [
        geom.box(
            [layout.width, layout.depth, layout.top_t],
            at=[0.0, 0.0, layout.body_height - layout.top_t],
        )
    ]


def _stack_ribs(layout: Layout, opt: dict[str, Any]) -> list[geom.Solid]:
    """A chamfered rib along each panel top that drops into the rack above."""
    height = opt["stack_rib_height"]
    wall = opt["wall"]
    rib_w = max(wall - 2 * RIB_FIT_GAP - 0.4, 0.8)
    chamfer = min(height * 0.5, rib_w * 0.35)
    inset = 8.0
    y0, y1 = inset, max(layout.depth - inset, inset + 4.0)
    # Sink the rib slightly into the panel. Two solids that merely share a face
    # can survive a union as separate shells; a real overlap always fuses.
    z0 = layout.body_height - RIB_EMBED
    out = []
    for index in range(opt["columns"] + 1):
        x_center = layout.panel_x0(index) + wall / 2.0
        profile = geom.chamfered_rect(
            x_center - rib_w / 2.0, x_center + rib_w / 2.0,
            z0, z0 + height + RIB_EMBED, chamfer_top=chamfer,
        )
        out.append(geom.prism_y(profile, y0, y1))
    return out


def _stack_sockets(layout: Layout, opt: dict[str, Any]) -> list[geom.Solid]:
    """Grooves under each panel that swallow the ribs of the rack below."""
    height = opt["stack_rib_height"]
    wall = opt["wall"]
    rib_w = max(wall - 2 * RIB_FIT_GAP - 0.4, 0.8)
    slot_w = rib_w + 2 * RIB_FIT_GAP
    inset = 8.0
    y0, y1 = inset - RIB_FIT_GAP, layout.depth - inset + RIB_FIT_GAP
    depth = height + 0.4
    out = []
    for index in range(opt["columns"] + 1):
        x_center = layout.panel_x0(index) + wall / 2.0
        out.append(
            geom.box(
                [slot_w, y1 - y0, depth],
                at=[x_center - slot_w / 2.0, y0, -0.01],
            )
        )
    return out


def _mount_flange(layout: Layout, opt: dict[str, Any]) -> list[geom.Solid]:
    """A tab above the rack for the keyholes to live in.

    It sits above the top bin rather than beside it, which is the only place on
    a rack this shape with room for a keyhole and clearance for the screw head
    that ends up behind it.
    """
    if not opt["wall_mount"]:
        return []
    thickness = _flange_thickness(opt)
    flange = geom.box(
        [layout.width, thickness, layout.flange_height],
        at=[0.0, layout.depth - thickness, layout.body_height],
    )
    # The flange is thicker than the back panel below it, so its inner face
    # would otherwise start in mid-air. Run a 45-degree gusset under it.
    step = thickness - layout.rear_t
    if step <= geom.EPS:
        return [flange]
    y_inner = layout.depth - thickness
    gusset = geom.prism_x(
        [
            (y_inner, layout.body_height),
            (y_inner + step, layout.body_height),
            (y_inner + step, layout.body_height - step),
        ],
        0.0, layout.width,
    )
    return [flange, gusset]


def _flange_thickness(opt: dict[str, Any]) -> float:
    return max(opt["wall"], FLANGE_MIN_THICKNESS)


def _keyholes(layout: Layout, opt: dict[str, Any]) -> list[geom.Solid]:
    """A round mouth over a narrow slot, cut clean through the flange.

    The screw head passes through the mouth, then the rack drops so the shank
    rides in the slot and the head is trapped behind it. Nothing is
    counterbored: the plastic around the slot is what carries the rack, and
    the head ends up in the empty space above the top bin.
    """
    head_d = opt["keyhole_head"]
    shank_d = opt["keyhole_screw"]
    if shank_d >= head_d - 1.0:
        raise ValueError(
            f"keyhole_head ({head_d:.1f} mm) must be at least 1 mm larger than "
            f"keyhole_screw ({shank_d:.1f} mm), or the head cannot pass through."
        )

    thickness = _flange_thickness(opt)
    y0, y1 = layout.depth - thickness - 1.0, layout.depth + 1.0

    top = layout.body_height + layout.flange_height
    z_entry = top - head_d / 2.0 - 4.0
    drop = max(head_d * 1.1, 8.0)
    z_rest = z_entry - drop
    if z_rest < layout.body_height + 3.0:
        raise ValueError(
            "mount_flange_height leaves no room for a keyhole. Raise it to at "
            f"least {drop + head_d + 10:.0f} mm."
        )

    out = []
    for fraction in (0.25, 0.75):
        x = layout.width * fraction
        out.append(geom.cylinder_y(head_d / 2.0, y0, y1, at_xz=(x, z_entry)))
        out.append(geom.cylinder_y(shank_d / 2.0, y0, y1, at_xz=(x, z_rest)))
        out.append(
            geom.box([shank_d, y1 - y0, drop], at=[x - shank_d / 2.0, y0, z_rest])
        )
    return out


def _corner_chamfers(layout: Layout, opt: dict[str, Any]) -> list[geom.Solid]:
    """Break the four outer vertical corners so the rack is pleasant to handle."""
    chamfer = opt["chamfer"]
    if chamfer <= 0:
        return []
    top = layout.height + 1.0
    x_left, x_right = 0.0, layout.width
    y_front, y_back = 0.0, layout.depth
    corners = [
        [(x_left, y_front), (x_left + chamfer, y_front), (x_left, y_front + chamfer)],
        [(x_right, y_front), (x_right, y_front + chamfer), (x_right - chamfer, y_front)],
        [(x_left, y_back), (x_left, y_back - chamfer), (x_left + chamfer, y_back)],
        [(x_right, y_back), (x_right - chamfer, y_back), (x_right, y_back - chamfer)],
    ]
    return [geom.prism_z(points, -1.0, top) for points in corners]


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------


def _part_name(spec: BinSpec, opt: dict[str, Any]) -> str:
    return f"bin-rack_{spec.key}_{opt['columns']}x{opt['rows']}"


def _facts(spec: BinSpec, layout: Layout, opt: dict[str, Any]) -> dict[str, Any]:
    return {
        "bin_key": spec.key,
        "bin_label": spec.label,
        "bin_short_label": spec.short_label,
        "bin_source": spec.source,
        "bin_fully_measured": spec.fully_measured,
        "bin_measured_fields": list(spec.measured_fields),
        "bin_estimated_fields": list(spec.estimated_fields),
        "bin_notes": spec.notes,
        "bin_outside_mm": [
            round(spec.length, 2), round(spec.width, 2), round(spec.height, 2)
        ],
        "capacity": layout.capacity,
        "columns": opt["columns"],
        "rows": opt["rows"],
        "outside_mm": [
            round(layout.width, 2), round(layout.depth, 2), round(layout.height, 2)
        ],
        "rail_span_mm": round(layout.span, 2),
        "rail_bearing_per_side_mm": round(layout.bearing, 2),
        "rim_side_gap_mm": round(layout.rim_side_gap, 2),
        "level_pitch_mm": round(layout.pitch_z, 2),
        "rail_tops_mm": [round(z, 2) for z in layout.rail_tops],
        "bin_drop_below_rail_mm": round(spec.hang_depth, 2),
        "supports_required": False,
    }


def _highlights(spec: BinSpec, layout: Layout, opt: dict[str, Any],
                size: tuple[float, float, float]) -> list[str]:
    # Quote the envelope the slicer will report, not the nominal body height:
    # stacking ribs and the hanger flange both stand outside it.
    width, depth, height = size
    items = [
        f"Holds {layout.capacity} bins in a {opt['columns']} x {opt['rows']} grid",
        f"Outside size {mm_in(width)} wide x {mm_in(depth)} deep "
        f"x {mm_in(height)} tall",
        f"Rails set {mm_in(layout.span)} apart, carrying "
        f"{layout.bearing:.1f} mm of rim on each side",
        "Prints upright in one piece, no supports",
    ]
    if opt["sides"] == "windowed":
        items.append("Cut-away sides: lighter, faster to print, contents visible")
    if opt["stackable"]:
        items.append("Ribs and sockets let racks stack and stay put")
    if opt["wall_mount"]:
        items.append("Keyhole flange for hanging on two screws")
    if opt["front_stop"] == "label":
        items.append("Recessed label panel across the front of every level")
    elif opt["front_stop"] != "none":
        items.append("Front stops keep bins from walking out")
    if opt["back"] == "panel":
        items.append("Solid back panel doubling as the bin backstop")
    elif opt["back"] == "windowed":
        items.append("Cut-away back panel: rigid, light, and a bin backstop")
    return items


def _print_notes(layout: Layout, opt: dict[str, Any]) -> list[str]:
    notes = [
        "Print in the orientation supplied: standing up, front face toward you.",
        "No support material. Every rail underside is cut back at 45 degrees.",
        "0.2 mm layers, 3 perimeters and 20% infill is plenty; the load path is "
        "straight down the side panels.",
        "Brim is worth it on tall configurations - the footprint is narrow for "
        "the height.",
    ]
    if opt["front_stop"] in ("lip", "label"):
        notes.append(
            f"The front {opt['front_stop']} bridges {layout.span:.0f} mm across "
            "each bay at every level. Any slicer handles it, but choose "
            "--front-stop tabs if your bridging is unhappy."
        )
    if opt["top"] == "plate":
        notes.append(
            f"The top plate bridges {layout.cell_inner:.0f} mm across each bay."
        )
    if opt["stackable"]:
        notes.append(
            f"Stacking ribs are sized with {RIB_FIT_GAP:.2f} mm of clearance per "
            "side. If your printer runs wide, a quick pass with a knife on the "
            "rib is easier than reprinting."
        )
    return notes


register(BinShelfGenerator())
