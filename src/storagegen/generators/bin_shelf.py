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

from .. import geom, patterns
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
# Two solids that meet on exactly the same plane give the boolean nothing to
# cut against, and it emits slivers along the seam. Everything that joins
# something else is sunk into it by this much instead.
EMBED = 0.5
FLANGE_MIN_THICKNESS = 4.0  # the hanger flange carries the whole rack
# The widest flat span left at the top of a window. Short enough that every
# slicer bridges it cleanly, long enough that the window is not a triangle.
MAX_WINDOW_BRIDGE = 12.0
# Every surface reads the same way: nothing there, solid, or cut with the
# chosen pattern.
SURFACES = ("cut", "solid", "open")
# Material kept around a cut-out region, so the pattern never runs into a
# rail, a corner or an edge.
PATTERN_MARGIN = 9.0
_SURFACE_NAMES = ("sides", "back", "base", "top")


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
    Option("back", "cut",
           "Back of the rack. This is the member that ties the two sides "
           "together and stops the bins at a consistent depth.",
           kind="choice", choices=SURFACES, group="Structure"),
    Option("back_thickness", 2.4, "Back panel thickness", unit=" mm",
           minimum=1.2, maximum=12, group="Structure"),
    Option("sides", "cut", "Side panels", kind="choice", choices=("cut", "solid"),
           group="Structure"),
    Option("front_stop", "tabs",
           "Front retention: none, corner tabs, a full lip, or a label plate",
           kind="choice", choices=("none", "tabs", "lip", "label"),
           group="Structure"),
    Option("stop_height", 5.0, "How high the front and back stops stand",
           unit=" mm", minimum=1.0, maximum=60, group="Structure"),
    Option("label_height", 18.0, "Height of the front plate when front_stop=label",
           unit=" mm", minimum=6, maximum=80, group="Structure"),
    Option("base", "open", "Bottom of the rack", kind="choice",
           choices=SURFACES, group="Structure"),
    Option("base_thickness", 3.0, "Floor thickness, if there is a floor",
           unit=" mm", minimum=1.2, maximum=15, group="Structure"),
    Option("floor_gap", 4.0, "Clearance beneath the lowest bin", unit=" mm",
           minimum=0.0, maximum=100, group="Structure"),
    Option("top", "open", "Top of the rack", kind="choice", choices=SURFACES,
           group="Structure"),
    Option("top_thickness", 3.0, "Top plate thickness, if there is a top",
           unit=" mm", minimum=1.2, maximum=15, group="Structure"),

    # ---- what the cut-outs look like -------------------------------------
    Option("pattern", "windows",
           "Shape cut into every surface set to 'cut'", kind="choice",
           choices=patterns.PATTERNS, group="Pattern"),
    Option("pattern_cell", None, "Size of one cut-out", unit=" mm",
           minimum=4, maximum=90, group="Pattern",
           default_note="whatever suits the chosen pattern"),
    Option("pattern_rib", None,
           "Material left between neighbouring cut-outs", unit=" mm",
           minimum=1.2, maximum=40, group="Pattern",
           default_note="whatever suits the chosen pattern"),
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
        self.pattern_margin_z = max(PATTERN_MARGIN, opt["rail_thickness"] + 4.0)
        self.rear_t = opt["back_thickness"] if opt["back"] != "open" else 0.0
        self.cavity_len = spec.length + opt["depth_clearance"]
        self.depth = self.front_t + self.cavity_len + self.rear_t
        self.cavity_y0 = self.front_t
        self.cavity_y1 = self.front_t + self.cavity_len

        # --- up the rack -------------------------------------------------
        self.base_t = opt["base_thickness"] if opt["base"] != "open" else 0.0
        self.top_t = opt["top_thickness"] if opt["top"] != "open" else 0.0
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
            f"_{opt['pattern']}_{opt['front_stop']}-front"
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

    if opt["back"] == "open" and "open" in (opt["base"], opt["top"]):
        raise ValueError(
            "With --back open there is nothing joining the two side panels, so "
            "the rack would print as two loose halves. Use --back cut or "
            "--back solid, or brace it top and bottom with --base solid "
            "--top solid."
        )

    if opt["wall_mount"]:
        if opt["back"] != "solid":
            opt["back"] = "solid"
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

    cell, rib = _pattern_size(opt)
    for surface, count in _pattern_counts(spec, layout, opt).items():
        if opt[surface] == "cut" and count == 0:
            report.warn(
                f"No {opt['pattern']} cut-out fits the {surface}, so that "
                f"surface came out solid. Reduce --pattern-cell (currently "
                f"{cell:.0f} mm) or --pattern-rib (currently {rib:.0f} mm)."
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
    cutters += _rail_lead_ins(layout, opt)
    cutters += _back_cutters(spec, layout, opt)
    cutters += _side_cutters(spec, layout, opt)
    cutters += _plate_cutters(spec, layout, opt, "base", -1.0,
                              layout.base_t + 1.0)
    cutters += _plate_cutters(
        spec, layout, opt, "top",
        layout.body_height - layout.top_t - 1.0, layout.body_height + 1.0,
    )
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


def _rail_profile(layout: Layout, opt: dict[str, Any], column: int,
                  rail_top: float, side: str,
                  stop_height: float = 0.0) -> list[tuple[float, float]]:
    """(x, z) cross-section of one rail, optionally carrying a front stop.

    The underside is taken back at 45 degrees, which is what lets a ledge
    cantilever into the opening with nothing beneath it. The rail reaches
    EMBED into its side panel rather than stopping on the panel's face, so the
    boolean has something to cut against instead of two coincident planes.

    `stop_height` raises the same profile into a front stop. Building the stop
    as part of the rail rather than as a box sitting on it matters: a separate
    box wide enough to catch the bin's rim meets the rail's tip along exactly
    one line, and an edge shared by four triangles is non-manifold the moment
    anything welds vertices by position -- which every slicer does.
    """
    thickness = opt["rail_thickness"]
    reach = opt["rail_width"]
    chamfer = min(thickness, reach)
    low = rail_top - thickness
    high = rail_top + stop_height

    if side == "left":
        outer = layout.cell_x0(column) - EMBED
        tip = layout.cell_x0(column) + reach
        profile = [(outer, high), (tip, high)]
        if stop_height > 0:
            profile.append((tip, rail_top))
        profile += [(tip - chamfer, rail_top - chamfer), (outer, low)]
        return profile

    outer = layout.cell_x0(column) + layout.cell_inner + EMBED
    tip = layout.cell_x0(column) + layout.cell_inner - reach
    profile = [(outer, high), (outer, low), (tip + chamfer, rail_top - chamfer)]
    if stop_height > 0:
        profile.append((tip, rail_top))
    profile.append((tip, high))
    return profile


def _rails(layout: Layout, opt: dict[str, Any]) -> list[geom.Solid]:
    """The pair of ledges each bin hangs from, one down each side of a bay."""
    out: list[geom.Solid] = []
    for column in range(opt["columns"]):
        for rail_top in layout.rail_tops:
            for side in ("left", "right"):
                profile = _rail_profile(layout, opt, column, rail_top, side)
                out.extend(_rail_runs(profile, layout, opt))
    return out


def _rail_runs(profile, layout: Layout,
               opt: dict[str, Any]) -> list[geom.Solid]:
    """One rail, either continuous or reduced to a pad at each end."""
    if opt["rail_style"] == "pads":
        pad = min(opt["pad_length"], layout.depth / 2.0)
        segments = [(0.0, pad), (layout.depth - pad, layout.depth)]
    else:
        segments = [(0.0, layout.depth)]
    return [geom.prism_y(profile, y0, y1) for y0, y1 in segments]


def _rail_lead_ins(layout: Layout, opt: dict[str, Any]) -> list[geom.Solid]:
    """Open the mouth of every rail so a bin steers itself in.

    Taken out of the rail rather than added to it. Growing the flare as a
    convex hull and unioning it on met neighbouring solids along single edges
    and left pinches in the mesh; a wedge subtracted from a plain prism cannot.
    """
    lead = min(opt["rail_lead_in"], max(opt["wall"] - 0.4, 0.0))
    if lead <= geom.EPS:
        return []
    depth = max(2.5 * lead, 6.0)
    thickness = opt["rail_thickness"]
    reach = opt["rail_width"]

    out = []
    for column in range(opt["columns"]):
        left_tip = layout.cell_x0(column) + reach
        right_tip = layout.cell_x0(column) + layout.cell_inner - reach
        wedges = (
            [(left_tip - lead, 0.0), (left_tip, 0.0), (left_tip, depth)],
            [(right_tip + lead, 0.0), (right_tip, depth), (right_tip, 0.0)],
        )
        for rail_top in layout.rail_tops:
            for wedge in wedges:
                out.append(
                    geom.prism_z(wedge, rail_top - thickness - 1.0,
                                 rail_top + EMBED)
                )
    return out


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


def _bay_bands(spec: BinSpec, layout: Layout,
               opt: dict[str, Any]) -> list[tuple[float, float]]:
    """The clear vertical band beside each bin, one per level.

    A band runs from a margin above the rail below it to a margin below its own
    rail, so every rail keeps solid material behind its 45-degree underside and
    the cut-outs get the whole span in between -- including the gap under the
    bin, which is air anyway.

    The lowest band stops above the floor instead, clear of the base plate and
    of the stacking sockets cut into the panel bottoms.
    """
    margin = layout.pattern_margin_z
    floor = layout.base_t
    if opt["stackable"]:
        floor = max(floor, opt["stack_rib_height"] + 0.4)

    bands = []
    for index, rail_top in enumerate(layout.rail_tops):
        low = layout.rail_tops[index - 1] + margin if index else floor + margin
        high = rail_top - margin
        if high - low > patterns.MIN_HOLE:
            bands.append((low, high))
    return bands


def _pattern_size(opt: dict[str, Any]) -> tuple[float, float]:
    """Cell and rib, falling back to whatever suits the chosen pattern."""
    style = opt["pattern"]
    cell, rib = opt["pattern_cell"], opt["pattern_rib"]
    return (
        patterns.default_cell(style) if cell is None else cell,
        patterns.default_rib(style) if rib is None else rib,
    )


def _cut(opt: dict[str, Any], rect) -> list[list[tuple[float, float]]]:
    cell, rib = _pattern_size(opt)
    return patterns.tile(opt["pattern"], rect, cell, rib, MAX_WINDOW_BRIDGE)


def _bay_span(layout: Layout, column: int) -> tuple[float, float]:
    left = layout.cell_x0(column) + PATTERN_MARGIN
    return left, layout.cell_x0(column) + layout.cell_inner - PATTERN_MARGIN


def _depth_span(layout: Layout) -> tuple[float, float]:
    return PATTERN_MARGIN, layout.depth - layout.rear_t - PATTERN_MARGIN


def _cut_regions(spec: BinSpec, layout: Layout,
                 opt: dict[str, Any]) -> dict[str, list[tuple]]:
    """The rectangles each patterned surface gets to fill.

    One place decides where cut-outs may go, so the geometry and the check
    that the pattern actually fits cannot disagree. Side regions are listed
    once even though every panel gets them, since all panels are identical.
    """
    bands = _bay_bands(spec, layout, opt)
    front, back = _depth_span(layout)
    bays = [_bay_span(layout, column) for column in range(opt["columns"])]

    regions: dict[str, list[tuple]] = {name: [] for name in _SURFACE_NAMES}
    if opt["sides"] == "cut":
        regions["sides"] = [(front, low, back, high) for low, high in bands]
    if opt["back"] == "cut":
        regions["back"] = [
            (x0, low, x1, high) for x0, x1 in bays for low, high in bands
        ]
    for plate in ("base", "top"):
        if opt[plate] == "cut":
            regions[plate] = [(x0, front, x1, back) for x0, x1 in bays]
    return regions


def _pattern_counts(spec: BinSpec, layout: Layout,
                    opt: dict[str, Any]) -> dict[str, int]:
    """How many cut-outs each surface would actually get."""
    return {
        name: sum(len(_cut(opt, rect)) for rect in rects)
        for name, rects in _cut_regions(spec, layout, opt).items()
    }


def _back_cutters(spec: BinSpec, layout: Layout,
                  opt: dict[str, Any]) -> list[geom.Solid]:
    """Pattern the back panel, in the (x, z) plane of that wall."""
    y0, y1 = layout.depth - layout.rear_t - 1.0, layout.depth + 1.0
    return [
        geom.prism_y(profile, y0, y1)
        for rect in _cut_regions(spec, layout, opt)["back"]
        for profile in _cut(opt, rect)
    ]


def _side_cutters(spec: BinSpec, layout: Layout,
                  opt: dict[str, Any]) -> list[geom.Solid]:
    """Pattern the side panels, in the (y, z) plane of those walls.

    Solid sides are most of the plastic in a rack this shape, and most of that
    plastic is doing nothing: the load runs straight down the panel edges.
    """
    regions = _cut_regions(spec, layout, opt)["sides"]
    out = []
    for index in range(opt["columns"] + 1):
        x0 = layout.panel_x0(index) - 1.0
        x1 = x0 + opt["wall"] + 2.0
        for rect in regions:
            for profile in _cut(opt, rect):
                out.append(geom.prism_x(profile, x0, x1))
    return out


def _plate_cutters(spec: BinSpec, layout: Layout, opt: dict[str, Any],
                   surface: str, z0: float, z1: float) -> list[geom.Solid]:
    """Pattern a horizontal plate, in the (x, y) plane, one bay at a time."""
    return [
        geom.prism_z(profile, z0, z1)
        for rect in _cut_regions(spec, layout, opt)[surface]
        for profile in _cut(opt, rect)
    ]


def _front_stops(spec: BinSpec, layout: Layout,
                 opt: dict[str, Any]) -> list[geom.Solid]:
    """What keeps a bin from walking out of the front."""
    style = opt["front_stop"]
    if style == "none":
        return []
    height = opt["label_height"] if style == "label" else opt["stop_height"]
    y0, y1 = 0.0, layout.front_t

    out = []
    for column in range(opt["columns"]):
        for rail_top in layout.rail_tops:
            if style == "tabs":
                # The stop is the rail, run up taller over its first few
                # millimetres, so there is no seam between the two.
                for side in ("left", "right"):
                    out.append(geom.prism_y(
                        _rail_profile(layout, opt, column, rail_top, side,
                                      stop_height=height),
                        y0, y1,
                    ))
                continue
            # A continuous lip or label plate spans the whole bay, which buries
            # both rail tips inside it rather than touching them.
            left = layout.cell_x0(column)
            out.append(geom.box(
                [layout.cell_inner, y1 - y0, height + EMBED],
                at=[left, y0, rail_top - EMBED],
            ))
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
    if opt["base"] == "open":
        return []
    return [geom.box([layout.width, layout.depth, layout.base_t])]


def _top_plate(layout: Layout, opt: dict[str, Any]) -> list[geom.Solid]:
    if opt["top"] == "open":
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
        [layout.width, thickness, layout.flange_height + EMBED],
        at=[0.0, layout.depth - thickness, layout.body_height - EMBED],
    )
    # The flange is thicker than the back panel below it, so its inner face
    # would otherwise start in mid-air. Run a 45-degree gusset under it.
    step = thickness - layout.rear_t
    if step <= geom.EPS:
        return [flange]
    # Run the gusset EMBED past the back panel's inner face rather than
    # stopping on it, so the two overlap instead of sharing a plane.
    y_inner = layout.depth - thickness
    reach = step + EMBED
    gusset = geom.prism_x(
        [
            (y_inner, layout.body_height),
            (y_inner + reach, layout.body_height),
            (y_inner + reach, layout.body_height - reach),
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
        "pattern": opt["pattern"],
        "pattern_cell_mm": round(_pattern_size(opt)[0], 2),
        "pattern_rib_mm": round(_pattern_size(opt)[1], 2),
        "patterned_surfaces": [
            name for name in _SURFACE_NAMES if opt[name] == "cut"
        ],
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
    if "cut" in (opt["sides"], opt["back"], opt["base"], opt["top"]):
        cell, rib = _pattern_size(opt)
        items.append(patterns.describe(opt["pattern"], cell, rib,
                                       MAX_WINDOW_BRIDGE)
                     + " through " + _cut_surface_list(opt))
    if opt["stackable"]:
        items.append("Ribs and sockets let racks stack and stay put")
    if opt["wall_mount"]:
        items.append("Keyhole flange for hanging on two screws")
    if opt["front_stop"] == "label":
        items.append("Recessed label panel across the front of every level")
    elif opt["front_stop"] != "none":
        items.append("Front stops keep bins from walking out")
    if opt["back"] != "open":
        items.append("Back panel doubling as the bin backstop")
    return items


def _cut_surface_list(opt: dict[str, Any]) -> str:
    named = [name for name in _SURFACE_NAMES if opt[name] == "cut"]
    if len(named) == 1:
        return "the " + named[0]
    return "the " + ", ".join(named[:-1]) + " and " + named[-1]


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
    if opt["top"] != "open":
        notes.append(
            f"The top plate bridges {layout.cell_inner:.0f} mm across each bay."
            + (" Cutting a pattern into it leaves less for the bridge to land "
               "on, so use --top solid if your bridging is marginal."
               if opt["top"] == "cut" else "")
        )
    if opt["stackable"]:
        notes.append(
            f"Stacking ribs are sized with {RIB_FIT_GAP:.2f} mm of clearance per "
            "side. If your printer runs wide, a quick pass with a knife on the "
            "rib is easier than reprinting."
        )
    return notes


register(BinShelfGenerator())
