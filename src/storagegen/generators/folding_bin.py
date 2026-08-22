"""Folding bin: a bin whose four walls pivot flat onto its own floor.

How it goes together
--------------------
The base is a floor with a rim around it and a post at each corner. Every wall
carries a pivot pin at each end that snaps down into a socket in those posts.
Erecting it is two motions: the long side walls come up first, then the short
end walls come up outside them and close the corners. Collapsing it is the
reverse, and the walls end up lying flat inside the rim, one pair on top of the
other.

Why the pins are not round
--------------------------
A wall prints lying flat, so its hinge axis lies *in* the bed plane. A round
pin is then a horizontal cylinder -- the underside is an overhang that no
slicer prints cleanly without support. An eight-sided pin has a flat first
layer, a short bridge on top, and side faces no shallower than 45 degrees, so
it prints unsupported; in a round socket it rotates on its corners with about
0.19 mm of wobble on a 5 mm pin. Six sides is safer still at 60 degrees, ten is
already too shallow at 36. The socket stays round, because a socket is a valley
and valleys print fine.

Why the two pairs pivot at different heights
--------------------------------------------
Both pairs fold onto the same floor, so one pair has to lie on top of the
other. The side walls pivot one wall thickness higher than the end walls, which
lets them fold over the top of the already-folded end walls instead of into
them. Erecting is that sequence run backwards -- the pair lying on top has to
move first -- so the side walls rise first and the end walls close last, which
is why it is the end walls that are long enough to wrap the corners.
"""

from __future__ import annotations

import math
from typing import Any

from .. import geom, patterns
from ..generator import BuildResult, Generator, register
from ..mesh_io import Part, PartSet
from ..options import Option, OptionSet, Report
from ..presets import get_bin
from ..units import mm_in

# Printed plastic needs room to move. These are per-side unless stated.
PIN_GAP = 0.35              # pin corner to socket bore
FOLD_GAP = 0.6              # between the two folded wall layers
CORNER_GAP = 0.3            # between a wall edge and the wall it meets
MAX_PRINTABLE_FACETS = 8    # beyond this a flat-lying pin needs support
EMBED = 0.6                 # overlap between solids that have to weld into one


OPTIONS = OptionSet([
    Option("preset", "custom", "Where the size comes from", kind="choice",
           choices=("custom", "greenmade-rack"), group="Size"),
    Option("width", 220.0, "Inside width, the long axis", unit=" mm",
           minimum=60, maximum=600, group="Size"),
    Option("depth", 150.0, "Inside depth", unit=" mm", minimum=60,
           maximum=600, group="Size"),
    Option("height", 70.0, "Wall height above the floor", unit=" mm",
           minimum=20, maximum=300, group="Size"),
    Option("wall", 2.8, "Wall thickness", unit=" mm", minimum=1.6, maximum=10,
           group="Size"),
    Option("floor", 3.0, "Floor thickness", unit=" mm", minimum=1.6,
           maximum=12, group="Size"),

    Option("pivot_across", 6.4, "Across-flats size of the pivot pins",
           unit=" mm", minimum=3, maximum=14, group="Hinge"),
    Option("pivot_facets", 8, "Sides on the pivot pins", kind="int",
           minimum=4, maximum=16, group="Hinge"),
    Option("pivot_length", 5.0, "How far each pin reaches into its socket",
           unit=" mm", minimum=2.5, maximum=20, group="Hinge"),
    Option("snap_grip", 0.55,
           "How far the socket mouth closes over the pin, the snap",
           unit=" mm", minimum=0.0, maximum=2.0, group="Hinge"),
    Option("socket_wall", 3.2, "Material around each socket", unit=" mm",
           minimum=1.6, maximum=10, group="Hinge"),

    Option("rim_flange", 0.0,
           "Ledge round the top of the walls, for hanging on rails",
           unit=" mm", minimum=0.0, maximum=12.0, group="Size",
           default_note="none; the walls finish flush"),

    Option("pattern", "none",
           "Cut-out pattern for the walls and floor", kind="choice",
           choices=("none",) + patterns.PATTERNS, group="Pattern"),
    Option("pattern_cell", None, "Size of one cut-out", unit=" mm",
           minimum=4, maximum=90, group="Pattern",
           default_note="whatever suits the chosen pattern"),
    Option("pattern_rib", None, "Material between neighbouring cut-outs",
           unit=" mm", minimum=1.2, maximum=40, group="Pattern",
           default_note="whatever suits the chosen pattern"),
    Option("pattern_floor", True, "Also pattern the floor", kind="bool",
           group="Pattern"),

    Option("material", "petg", "Filament, for the weight estimate only",
           kind="choice", choices=("pla", "petg", "abs", "asa"),
           group="Output"),
    Option("bed_x", 256.0, "Printer bed width", unit=" mm", minimum=50,
           maximum=1200, group="Output", listed=False),
    Option("bed_y", 256.0, "Printer bed depth", unit=" mm", minimum=50,
           maximum=1200, group="Output", listed=False),
    Option("bed_z", 256.0, "Printer build height", unit=" mm", minimum=50,
           maximum=1200, group="Output", listed=False),
])


class Layout:
    """Every derived dimension, worked out once.

    The rim sets everything else. A folded wall lies one pin radius below its
    own axis, so putting the low axis one radius above the rim top drops that
    wall flat onto the rim; the high axis sits a wall thickness further up so
    the second pair folds over the first. Each wall then runs from its own
    axis down to the rim top, which is why an erect wall meets the rim edge to
    edge with nothing to escape through underneath.
    """

    def __init__(self, opt: dict[str, Any]):
        self.o = opt
        self.wall_t = opt["wall"]
        self.floor_t = opt["floor"]
        self.inner_x = opt["width"]
        self.inner_y = opt["depth"]

        self.pin_across = opt["pivot_across"]
        self.pin_r = self.pin_across / 2.0
        # The socket has to clear the pin's corners, not its flats.
        self.pin_circum = self.pin_r / math.cos(math.pi / opt["pivot_facets"])
        self.bore_r = self.pin_circum + PIN_GAP
        self.reach = opt["pivot_length"]

        # A rim runs right round the floor at one height, inside and out.
        self.rim_h = max(2.0, self.wall_t)
        self.rim_top = self.floor_t + self.rim_h
        self.rim_t = max(2.0, self.wall_t * 0.8)

        # A flange stands proud of the wall's outer face, and folded that face
        # is uppermost -- so the pair underneath needs the flange's height as
        # headroom on top of its own thickness.
        self.flange = opt["rim_flange"]
        self.flange_t = max(2.4, self.wall_t)
        self.z_end = self.rim_top + self.pin_r
        self.z_side = self.z_end + self.wall_t + self.flange + FOLD_GAP
        self.skirt_end = self.z_end - self.rim_top
        self.skirt_side = self.z_side - self.rim_top

        # A pin's flat face sits flush with the wall's inner face, so the axis
        # lies one pin radius outboard of it. Erect, that puts the wall
        # exactly outside the inner footprint.
        self.y_axis = self.inner_y / 2.0 + self.pin_r
        self.x_axis = self.inner_x / 2.0 + self.pin_r

        # A post has to be deep enough to swallow a whole pin. Failing that,
        # the width is a choice: folded, the part of a wall below its axis
        # swings out past that axis, and padding the posts out to cover it
        # keeps the folded bin inside its own outline. A bin meant to hang
        # gives that up -- there the flange has to be the widest thing on it,
        # so the body can drop between the rails it hangs from.
        self.post_t = max(self.reach + opt["socket_wall"], self.wall_t + 1.0)
        if self.flange <= 0.0:
            self.post_t = max(self.post_t, self.pin_r + self.skirt_side + 1.0)
        self.swing_side = self.y_axis + self.skirt_side
        self.swing_end = self.x_axis + self.skirt_end
        self.outer_x = self.inner_x + 2 * self.post_t
        self.outer_y = self.inner_y + 2 * self.post_t

        # What actually passes between a pair of rails, and how far the flange
        # stands out past it.
        self.body_x = self.outer_x
        self.body_y = self.outer_y
        self.flange_x = self.inner_x + 2.0 * (self.wall_t + self.flange)
        self.flange_y = self.inner_y + 2.0 * (self.wall_t + self.flange)
        self.overhang = (self.flange_y - self.body_y) / 2.0
        self.hangs = self.flange > 0.0 and self.overhang >= 1.0

        self.top_z = self.floor_t + opt["height"]
        self.h_end = self.top_z - self.z_end
        self.h_side = self.top_z - self.z_side

        # The side walls fold last, on top, so they are also the pair that
        # rises first and they run the full width. The end walls fold
        # underneath, and their pins are pulled in far enough that they never
        # cross the side pins in the corner post -- the post fills in what
        # they give up, so the inside of the bin stays square.
        self.socket_x = self.inner_x / 2.0 - CORNER_GAP
        self.socket_y = min(self.inner_y / 2.0 - CORNER_GAP,
                            self.y_axis - self.pin_circum - self.reach - 1.0)
        self.len_side = 2.0 * self.socket_x
        self.len_end = 2.0 * self.socket_y

        self.post_from_x = self.inner_x / 2.0
        self.post_from_y = self.socket_y
        # Nothing folded ever reaches the corners, so the posts are free to
        # carry on up. Height there is worth having: it is the only thing a
        # stop lug can hang off, and a stop close to the hinge is a stop with
        # no leverage.
        self.post_top = max(self.z_side + self.bore_r + opt["socket_wall"],
                            self.floor_t + opt["height"] * 0.3)
        self.lug = min(6.0, self.post_t - self.pin_r - 1.0,
                       (self.post_top - self.z_side - 1.0) / 2.0)

        # Above the posts the end walls widen back out to full span and close
        # the corner the rest of the way up. The ears start beyond the
        # farthest corner of the post, so they swing over it, never into it.
        self.ear_from = math.hypot(self.post_t - self.pin_r,
                                   self.post_top - self.z_end) + 1.0
        self.ear_y = self.inner_y / 2.0 - CORNER_GAP
        self.has_ears = (self.ear_y > self.socket_y + 0.2
                         and self.ear_from < self.h_end - 2.0)

    def skirt_of(self, kind: str) -> float:
        """How far a wall reaches below its own pivot axis."""
        return self.skirt_side if kind == "side" else self.skirt_end

    def axis_of(self, kind: str) -> float:
        """Distance from the middle out to a pair's hinge axis."""
        return self.y_axis if kind == "side" else self.x_axis

    def height_of(self, kind: str) -> float:
        return self.h_side if kind == "side" else self.h_end

    def length_of(self, kind: str) -> float:
        return self.len_side if kind == "side" else self.len_end

    def z_of(self, kind: str) -> float:
        return self.z_side if kind == "side" else self.z_end

    @property
    def fold_limit_end(self) -> float:
        """How tall an end wall may be before the folded pair collide."""
        return self.x_axis - CORNER_GAP / 2.0

    @property
    def fold_limit_side(self) -> float:
        return self.y_axis - CORNER_GAP / 2.0

    @property
    def folded_height(self) -> float:
        return self.z_side - self.pin_r + self.wall_t


class FoldingBinGenerator(Generator):
    key = "folding-bin"
    title = "Folding bin"
    summary = (
        "A bin whose four walls pivot down flat onto its own floor, so it "
        "stores in a fraction of the space it works in."
    )
    tags = ("storage", "folding bin", "collapsible crate", "parametric",
            "snap together", "no supports", "print flat")
    options = OPTIONS

    def build(self, opt: dict[str, Any]) -> BuildResult:
        report = Report()
        opt = dict(opt)
        _apply_preset(opt, report)
        _validate(opt, report)
        layout = Layout(opt)
        _check_fit(layout, opt, report)

        parts = PartSet()
        parts.add("base", _base(layout, opt),
                  note="Floor, rim and four corner posts. Prints flat.")
        parts.add("wall-side", _wall_flat(layout, opt, "side"), copies=2,
                  note="Long wall. Raise these first; they fold on top.")
        parts.add("wall-end", _wall_flat(layout, opt, "end"), copies=2,
                  note="Short wall. Raise these last; they close the corners.")

        erect = _assembly(layout, opt, angle=90.0)
        folded = _assembly(layout, opt, angle=0.0)
        facts = _facts(layout, opt, erect, folded)
        return BuildResult(
            parts=parts,
            effective_options=opt,
            context_parts=[Part("erected", erect)],
            report=report,
            facts=facts,
            highlights=_highlights(layout, opt, facts),
            print_notes=_print_notes(layout, opt),
        )

    def slug(self, opt: dict[str, Any]) -> str:
        return (f"folding-bin_{opt['width']:.0f}x{opt['depth']:.0f}"
                f"x{opt['height']:.0f}_{opt['pattern']}")


# ---------------------------------------------------------------------------
# validation and reporting
# ---------------------------------------------------------------------------


# A small bin wants a small hinge: the corner posts are what the flange has
# to stand out past, and every millimetre of post is a millimetre of flange.
_RACK_HINGE = {"wall": 2.4, "floor": 2.4, "pivot_across": 4.5,
               "pivot_facets": 8, "pivot_length": 3.0, "socket_wall": 2.0}


def _apply_preset(opt: dict[str, Any], report: Report) -> None:
    """Size the bin to hang from the same rails a GreenMade Mini hangs from.

    The rack carries a bin under its rim, so the two numbers that matter are
    the width that has to pass between the rails and the width of the flange
    that lands on them. Match those and the folding bin drops into a rack
    built for the moulded bin, in the same cell, at the same height.
    """
    if opt["preset"] != "greenmade-rack":
        return
    spec = get_bin("greenmade-mini")
    opt.update(_RACK_HINGE)

    post = max(opt["pivot_length"] + opt["socket_wall"], opt["wall"] + 1.0)
    opt["rim_flange"] = round(post - opt["wall"] + spec.lip_overhang, 2)
    opt["width"] = round(spec.length - 2.0 * spec.lip_overhang - 2.0 * post, 1)
    opt["depth"] = round(spec.body_width - 2.0 * post, 1)

    # Folded, each pair meets in the middle, so a wall can be no longer than
    # its own half of the bin. The moulded bin is deeper than that allows.
    wanted = spec.height - opt["floor"]
    probe = Layout(dict(opt, height=wanted))
    cap = min(probe.z_side - opt["floor"] + probe.fold_limit_side,
              probe.z_end - opt["floor"] + probe.fold_limit_end)
    opt["height"] = round(min(wanted, cap), 1)

    report.note(
        f"Preset greenmade-rack: {opt['width']:.0f} x {opt['depth']:.0f} x "
        f"{opt['height']:.0f} mm inside, with a "
        f"{opt['rim_flange']:.1f} mm flange. Body "
        f"{spec.body_width:.1f} mm across the rails and {spec.width:.1f} mm "
        "over the flange, the same as the bin the rack was built for."
    )
    if opt["height"] < wanted - 0.5:
        report.note(
            f"Walls are capped at {opt['height']:.0f} mm rather than the "
            f"{wanted:.0f} mm the moulded bin gives you: any taller and the "
            "two long walls would meet in the middle when folded. The bin "
            "hangs at the same height, it is just shallower."
        )


def _validate(opt: dict[str, Any], report: Report) -> None:
    if opt["pivot_facets"] > MAX_PRINTABLE_FACETS:
        report.warn(
            f"{opt['pivot_facets']} facets puts the pin's lower faces at "
            f"{360.0 / opt['pivot_facets']:.0f} degrees from horizontal, "
            "shallower than the 45 a flat-lying pin can hold. It will need "
            "support. Eight facets is the smoothest that prints clean."
        )
    if opt["pivot_across"] < opt["wall"]:
        report.warn(
            f"A {opt['pivot_across']:.1f} mm pin on a {opt['wall']:.1f} mm "
            "wall makes the hinge the weakest part of the bin, and the hinge "
            "is what takes the load every time it folds. Match the pin to "
            "the wall or go a little over."
        )


def _check_fit(layout: Layout, opt: dict[str, Any], report: Report) -> None:
    if layout.socket_y < layout.pin_circum + 2.0:
        raise ValueError(
            f"There is nowhere to put the end walls' pins. They have to stop "
            f"{layout.y_axis - layout.socket_y:.1f} mm short of the side "
            "walls' own pins, and on a bin this narrow that leaves nothing. "
            "Increase --depth, or use a shorter --pivot-length."
        )
    if layout.h_end > layout.fold_limit_end:
        report.warn(
            f"End walls are {layout.h_end:.0f} mm tall but only "
            f"{layout.fold_limit_end:.0f} mm fits: folded, the pair would meet "
            "in the middle. Reduce --height or increase --width."
        )
    if layout.h_side > layout.fold_limit_side:
        report.warn(
            f"Side walls are {layout.h_side:.0f} mm tall but only "
            f"{layout.fold_limit_side:.0f} mm fits: folded, the pair would "
            "meet in the middle. Reduce --height or increase --depth."
        )

    if layout.flange > 0.0 and not layout.hangs:
        report.warn(
            f"A {layout.flange:.1f} mm flange only stands "
            f"{layout.overhang:.1f} mm proud of the corner posts, which are "
            f"{layout.post_t:.1f} mm deep. It will not sit on a rail. Use at "
            f"least {layout.post_t - layout.wall_t + 1.0:.1f} mm, or a "
            "shorter pin and a thinner socket wall."
        )

    bed = (opt["bed_x"], opt["bed_y"], opt["bed_z"])
    biggest = (layout.outer_x, layout.outer_y, layout.folded_height)
    over = [f"{axis} {value:.0f} mm > {limit:.0f} mm"
            for axis, value, limit in zip("XYZ", biggest, bed) if value > limit]
    if over:
        report.warn(
            "The base is bigger than the bed you specified ("
            + "; ".join(over) + "). Reduce --width or --depth."
        )


def _facts(layout: Layout, opt: dict[str, Any], erect: geom.Solid,
           folded: geom.Solid) -> dict[str, Any]:
    e, f = erect.bounding_box(), folded.bounding_box()
    erect_h = e[5] - e[2]
    folded_h = f[5] - f[2]
    return {
        "inside_mm": [round(layout.inner_x, 1), round(layout.inner_y, 1),
                      round(opt["height"], 1)],
        "outside_mm": [round(e[3] - e[0], 1), round(e[4] - e[1], 1),
                       round(erect_h, 1)],
        "folded_mm": [round(f[3] - f[0], 1), round(f[4] - f[1], 1),
                      round(folded_h, 1)],
        "collapse_ratio": round(erect_h / folded_h, 2),
        "capacity_litres": round(
            layout.inner_x * layout.inner_y * opt["height"] / 1e6, 2),
        "body_across_rails_mm": [round(layout.body_x, 1),
                                 round(layout.body_y, 1)],
        "flange_mm": round(layout.flange, 2),
        "flange_overhang_mm": round(layout.overhang, 2) if layout.flange else 0,
        "hangs_on_rails": layout.hangs,
        "fold_clearance_mm": [round(2.0 * layout.swing_end, 1),
                              round(2.0 * layout.swing_side, 1)],
        "pivot_facets": opt["pivot_facets"],
        "pin_across_mm": round(layout.pin_across, 2),
        "parts_to_print": 5,
        "pattern": opt["pattern"],
        "supports_required": False,
    }


def _highlights(layout: Layout, opt: dict[str, Any],
                facts: dict[str, Any]) -> list[str]:
    w, d, h = facts["outside_mm"]
    items = [
        f"Holds {facts['capacity_litres']:.1f} litres: inside "
        f"{mm_in(layout.inner_x)} x {mm_in(layout.inner_y)} x "
        f"{mm_in(opt['height'])}",
        f"Folds from {mm_in(h)} tall to {mm_in(facts['folded_mm'][2])} - "
        f"{facts['collapse_ratio']:.1f} times flatter to store",
        "Five parts, all flat on the bed, no supports anywhere",
        "Walls clip in by hand; no screws, no pins to lose",
    ]
    if layout.hangs:
        items.append(
            f"Hangs on rails like the bin it replaces: {mm_in(layout.body_y)} "
            f"between the rails, {mm_in(layout.flange_y)} over the flange")
    if opt["pattern"] != "none":
        cell, rib = _pattern_size(opt)
        items.append(patterns.describe(opt["pattern"], cell, rib)
                     + " through the walls"
                     + (" and floor" if opt["pattern_floor"] else ""))
    return items


def _print_notes(layout: Layout, opt: dict[str, Any]) -> list[str]:
    return [
        "Every part prints flat in the orientation supplied. No supports.",
        f"Print the base once and each wall twice: {5} parts in total.",
        "PETG is the better choice here. The pins take the load every time "
        "the bin is folded, and PETG is far less brittle than PLA at a hinge.",
        "0.2 mm layers with 4 perimeters. The walls are thin, so perimeters "
        "do the work rather than infill.",
        "To assemble, hold a wall at about half travel, line its pins up with "
        "the angled entry in each corner post and press down and in until "
        "they seat. The entry runs up and outward at 45 degrees, which is the "
        "one direction a wall never swings through, so a seated pin has no "
        "way back out of it at any angle the bin is used at.",
        "Raise the two long walls first and the two short ones after: folded, "
        "the long pair lies on top, and it has to move first.",
        f"Folding needs a little more room than the bin itself takes: "
        f"{mm_in(2.0 * layout.swing_end)} by "
        f"{mm_in(2.0 * layout.swing_side)} while the walls come down, since "
        "each one swings its bottom edge out as its top comes in.",
        "The walls stop dead at square against the lugs on the corner posts. "
        "They fold inwards freely from there, which is the only direction "
        "they need to go.",
    ]


# ---------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------


def _pin_profile(layout: Layout, opt: dict[str, Any]) -> list:
    """Pin cross-section, flat face down in the print orientation."""
    return geom.ngon_profile(layout.pin_across, opt["pivot_facets"],
                             centre=(0.0, layout.pin_r))


def _wall_flat(layout: Layout, opt: dict[str, Any], kind: str) -> geom.Solid:
    """One wall in its print pose: lying flat, hinge along +X at y=0.

    Local +y is distance out from the hinge, so the body runs from -skirt (the
    part that reaches down to the rim when the wall is up) to the full height,
    and the pins stick out past each end of the length. Everything sits on z=0,
    so it prints exactly as it is built.
    """
    length = layout.length_of(kind)
    height = layout.height_of(kind)
    thickness = layout.wall_t
    reach = layout.reach
    skirt = layout.skirt_of(kind)

    # Above the corner posts an end wall widens back out to full span, which
    # is what closes the corner over the post. The step starts far enough out
    # from the hinge to swing clear over the post rather than into it, so the
    # outline is a T rather than a rectangle -- drawn in one piece, because
    # two overlapping boxes leave slivers along every shared face.
    mid = length / 2.0
    if kind == "end" and layout.has_ears:
        ear, up = layout.ear_y, layout.ear_from
        outline = [(0.0, -skirt), (length, -skirt), (length, up),
                   (mid + ear, up), (mid + ear, height), (mid - ear, height),
                   (mid - ear, up), (0.0, up)]
    else:
        outline = [(0.0, -skirt), (length, -skirt),
                   (length, height), (0.0, height)]
    parts = [geom.prism_z(outline, 0.0, thickness)]

    # The flange is a rib along the top edge, standing off the face that ends
    # up outboard. Printed flat it is simply a taller strip; erect it is the
    # ledge the bin hangs by.
    if layout.flange > 0.0:
        wide = layout.ear_y if (kind == "end" and layout.has_ears) else None
        x0 = (mid - wide if wide else 0.0) + EMBED
        span = (2.0 * wide if wide else length) - 2.0 * EMBED
        # Held back a hair from each end: a flange that stopped exactly on the
        # wall's own end faces would leave a sliver of zero-width triangles
        # down every shared plane, and it has nothing to do out there anyway.
        parts.append(geom.box(
            [span, layout.flange_t, layout.flange + EMBED],
            at=[x0, height - layout.flange_t, thickness - EMBED]))

    # The pins reach a little way back into the wall. Sharing one face with
    # it is not enough: manifold3d will happily hand back two shells that
    # touch, and the slicer would print a wall with its pins lying beside it.
    profile = _pin_profile(layout, opt)
    pins = [
        geom.prism_x(profile, -reach, EMBED),
        geom.prism_x(profile, length - EMBED, length + reach),
    ]
    # A fillet where each pin meets the wall would be ideal; a small gusset
    # block does the same job and stays printable. It has to stay inside the
    # socket bore, since it turns with the pin: anything taller would have to
    # be cut out of the post, and that is material the socket needs to hold
    # the pin down.
    gusset = math.sqrt(max(0.0, layout.bore_r ** 2 - layout.pin_r ** 2))
    gusset = min(gusset - CORNER_GAP, thickness * 2.0)
    gussets = [
        geom.box([reach, gusset, thickness], at=[-reach, 0.0, 0.0]),
        geom.box([reach, gusset, thickness], at=[length, 0.0, 0.0]),
    ] if gusset > 0.5 else []
    solid = geom.union(parts, pins, gussets)

    if opt["pattern"] != "none":
        solid = geom.difference(solid,
                                _wall_cutters(layout, opt, length, height))
    return solid


def _wall_cutters(layout: Layout, opt: dict[str, Any], length: float,
                  height: float) -> list[geom.Solid]:
    """Pattern the wall. Printed flat, a hole is just a hole -- no overhangs."""
    margin = 10.0
    rect = (margin, margin, length - margin, height - margin)
    cell, rib = _pattern_size(opt)
    return [
        geom.prism_z(profile, -1.0, layout.wall_t + 1.0)
        for profile in patterns.tile(opt["pattern"], rect, cell, rib)
    ]


def _pattern_size(opt: dict[str, Any]) -> tuple[float, float]:
    style = opt["pattern"]
    cell, rib = opt["pattern_cell"], opt["pattern_rib"]
    return (patterns.default_cell(style) if cell is None else cell,
            patterns.default_rib(style) if rib is None else rib)


def _slot_profile(centre, angle_deg: float, width: float,
                  length: float) -> list:
    """A rectangular slot running out from `centre` at `angle_deg`."""
    rad = math.radians(angle_deg)
    dx, dy = math.cos(rad), math.sin(rad)
    nx, ny = -dy * width / 2.0, dx * width / 2.0
    cx, cy = centre
    tip = (cx + dx * length, cy + dy * length)
    return [
        (cx + nx, cy + ny),
        (cx - nx, cy - ny),
        (tip[0] - nx, tip[1] - ny),
        (tip[0] + nx, tip[1] + ny),
    ]


def _socket_cutters(layout: Layout, opt: dict[str, Any]) -> list[geom.Solid]:
    """Bore and entry slot for all eight sockets.

    The entry faces up and outward at 135 degrees rather than straight up. A
    wall only sweeps between flat-inward and vertical, so nothing passes 135
    degrees in normal use: the pin is captured at every working angle and comes
    out only when the wall is deliberately tilted out past vertical to clip it
    in. That removes the need for a snap lip the wall has to flex past on every
    fold, and keeps the bore a valley, which prints without support.
    """
    bore = geom.circle_profile(layout.bore_r)
    mouth = 2.0 * (layout.pin_circum + PIN_GAP) - opt["snap_grip"]
    out: list[geom.Solid] = []

    for sign in (-1.0, 1.0):
        # side walls: axis along X at y = +/- y_axis, z = z_side
        centre = (sign * layout.y_axis, layout.z_side)
        slot = _slot_profile(centre, 135.0 if sign < 0 else 45.0,
                             mouth, layout.post_t * 3.0)
        for end in (-1.0, 1.0):
            x0 = end * (layout.socket_x - EMBED - CORNER_GAP)
            x1 = end * (layout.socket_x + opt["pivot_length"] + 1.0)
            lo, hi = min(x0, x1), max(x0, x1)
            shifted = [(a + centre[0], b + centre[1]) for a, b in bore]
            out.append(geom.prism_x(shifted, lo, hi))
            out.append(geom.prism_x(slot, lo, hi))

        # end walls: axis along Y at x = +/- x_axis, z = z_end
        centre = (sign * layout.x_axis, layout.z_end)
        slot = _slot_profile(centre, 135.0 if sign < 0 else 45.0,
                             mouth, layout.post_t * 3.0)
        for end in (-1.0, 1.0):
            y0 = end * (layout.socket_y - EMBED - CORNER_GAP)
            y1 = end * (layout.socket_y + opt["pivot_length"] + 1.0)
            lo, hi = min(y0, y1), max(y0, y1)
            shifted = [(a + centre[0], b + centre[1]) for a, b in bore]
            out.append(geom.prism_y(shifted, lo, hi))
            out.append(geom.prism_y(slot, lo, hi))
    return out


def _swept_rects(layout: Layout, kind: str, t0: float, t1: float,
                 step: float = 3.0, out: float = 0.0) -> list:
    """The wall's cross-section, drawn again at every angle it turns through.

    A sector would be the tidy way to write this, but a wall is a slab and not
    a pie slice: near the hinge its own thickness puts it at angles a sector
    from the axis never reaches. Stepping the real rectangle round costs a few
    dozen extra polygons and is right by construction. `t0` and `t1` are
    distances out from the hinge, so passing the ears their own range keeps
    them from carving the posts the rest of the wall never touches.
    """
    # Travel runs from flat to square and no further at either end. Past
    # square is the stop; past flat is nothing at all, since the wall is lying
    # on the rim by then -- and a long wall tipped even a few degrees below
    # flat would have its far edge carving a trench through the floor.
    gap = CORNER_GAP / 2.0
    a0 = layout.pin_r - layout.wall_t - out - gap
    a1 = layout.pin_r + gap
    lo, hi = t0 - (gap if t0 < 0 else 0.0), t1
    rects = []
    steps = int(math.ceil(90.0 / step))
    for i in range(steps + 1):
        angle = math.radians(90.0 * i / steps)
        n = (math.sin(angle), -math.cos(angle))
        u = (math.cos(angle), math.sin(angle))
        rects.append([(a * n[0] + t * u[0], a * n[1] + t * u[1])
                      for a, t in ((a0, lo), (a1, lo), (a1, hi), (a0, hi))])
    return rects


def _sweep_reliefs(layout: Layout, opt: dict[str, Any]) -> list[geom.Solid]:
    """Everything each wall passes through on its way up, cut out of the base.

    Carving the base with the motion itself is what makes the mechanism
    trustworthy: any rim, post or socket lip that would foul a wall at some
    angle is removed by construction rather than by a clearance somebody
    remembered to leave. Travel stops dead at square, and that is what gives
    the bin its stop: everything a wall would have to pass through to lean out
    any further is still standing.
    """
    out: list[geom.Solid] = []
    for kind in ("side", "end"):
        axis = layout.axis_of(kind)
        z = layout.z_of(kind)
        half = layout.length_of(kind) / 2.0
        skirt = layout.skirt_of(kind)
        height = layout.height_of(kind)
        # A side wall swings in the YZ plane, an end wall in the XZ plane.
        prism = geom.prism_x if kind == "side" else geom.prism_y
        runs = [(-skirt, height, half, 0.0)]
        if kind == "end" and layout.has_ears:
            runs.append((layout.ear_from, height, layout.ear_y, 0.0))
        if layout.flange > 0.0:
            wide = layout.ear_y if (kind == "end" and layout.has_ears) else half
            runs.append((height - layout.flange_t, height, wide,
                         layout.flange))
        for sign in (-1.0, 1.0):
            # A wall folds inwards, so its travel opens toward the middle of
            # the bin: the same shape, mirrored for the wall on the far side.
            inward = -sign
            for t0, t1, extent, proud in runs:
                for rect in _swept_rects(layout, kind, t0, t1, out=proud):
                    profile = [(sign * axis + inward * pa, z + pb)
                               for pa, pb in rect]
                    out.append(prism(profile, -extent, extent))
    return out


def _stop_lugs(layout: Layout) -> list[geom.Solid]:
    """What a wall runs into if it tries to keep going past square.

    Above its own hinge a wall's outer face never gets further out than it is
    at square, whatever angle it is at -- so the sliver of space just beyond
    that face is the one place nothing ever sweeps, and the one place a stop
    can live. Each lug hangs off a corner post, reaches back in over the end
    of the wall, and is ramped at 45 degrees underneath so it prints off the
    post without support.
    """
    if layout.lug < 1.0:
        return []
    lug = layout.lug
    # Just clear of the wall's outer face, not of the hinge axis: on a thin
    # wall with a fat pin those are millimetres apart, and a lug set out at
    # the axis would sit too far back for the wall ever to reach it.
    face = layout.pin_r - layout.wall_t - CORNER_GAP
    out: list[geom.Solid] = []
    for kind in ("side", "end"):
        axis = layout.axis_of(kind) - face
        z_lo = layout.z_of(kind) + 1.0
        along = layout.length_of(kind) / 2.0
        post = layout.post_from_x if kind == "side" else layout.post_from_y
        far = (layout.outer_y if kind == "side" else layout.outer_x) / 2.0
        for sign in (-1.0, 1.0):
            for end in (-1.0, 1.0):
                # Reach into the post rather than stopping on its face:
                # solids that only share a plane do not reliably weld.
                p0, p1 = end * (post + EMBED), end * (along - lug)
                profile = [(p0, z_lo), (p0, layout.post_top),
                           (p1, layout.post_top), (p1, z_lo + lug)]
                lo, hi = sorted((sign * axis, sign * far))
                # A side wall is caught by a lug reaching along X; an end wall
                # by one reaching along Y.
                prism = geom.prism_y if kind == "side" else geom.prism_x
                out.append(prism(profile, lo, hi))
    return out


def _base(layout: Layout, opt: dict[str, Any]) -> geom.Solid:
    """Floor, a rim at one height all round, corner posts -- then carved.

    Everything is built solid first and only afterwards cut back by what the
    walls sweep through and by the pin bores. What survives is by definition
    the material that is never in the way. The rim ends up doing three jobs at
    once: an erect wall lands on it, meets its edge so nothing escapes
    underneath, and cannot lean out past square because the rim is there.
    """
    half_x, half_y = layout.outer_x / 2.0, layout.outer_y / 2.0
    floor = geom.box([layout.outer_x, layout.outer_y, layout.floor_t],
                     at=[-half_x, -half_y, 0.0])

    ring = geom.box([layout.outer_x, layout.outer_y, layout.rim_h],
                    at=[-half_x, -half_y, layout.floor_t])
    well_x = layout.inner_x - 2.0 * layout.rim_t
    well_y = layout.inner_y - 2.0 * layout.rim_t
    well = geom.box([well_x, well_y, layout.rim_h + 2.0],
                    at=[-well_x / 2.0, -well_y / 2.0, layout.floor_t])
    rim = geom.difference(ring, [well])

    posts = []
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            x0, x1 = sorted((sx * layout.post_from_x, sx * half_x))
            y0, y1 = sorted((sy * layout.post_from_y, sy * half_y))
            posts.append(geom.box(
                [x1 - x0, y1 - y0, layout.post_top - layout.rim_top],
                at=[x0, y0, layout.rim_top]))

    solid = geom.union([floor, rim], posts, _stop_lugs(layout))

    cutters = _sweep_reliefs(layout, opt) + _socket_cutters(layout, opt)
    if opt["pattern"] != "none" and opt["pattern_floor"]:
        cutters += _floor_cutters(layout, opt)
    return geom.difference(solid, cutters)


def _floor_cutters(layout: Layout, opt: dict[str, Any]) -> list[geom.Solid]:
    margin = 12.0
    rect = (-layout.inner_x / 2.0 + margin, -layout.inner_y / 2.0 + margin,
            layout.inner_x / 2.0 - margin, layout.inner_y / 2.0 - margin)
    cell, rib = _pattern_size(opt)
    return [
        geom.prism_z(profile, -1.0, layout.floor_t + 1.0)
        for profile in patterns.tile(opt["pattern"], rect, cell, rib)
    ]


def _place(wall: geom.Solid, layout: Layout, which: str,
           angle: float) -> geom.Solid:
    """Move a wall from its print pose into the assembly at `angle` degrees."""
    s = wall.translate([0.0, 0.0, -layout.pin_r]).rotate([angle, 0.0, 0.0])
    if which == "side-neg":
        return s.translate([-layout.len_side / 2.0, -layout.y_axis,
                            layout.z_side])
    if which == "side-pos":
        return s.rotate([0.0, 0.0, 180.0]).translate(
            [layout.len_side / 2.0, layout.y_axis, layout.z_side])
    if which == "end-pos":
        return s.rotate([0.0, 0.0, 90.0]).translate(
            [layout.x_axis, -layout.len_end / 2.0, layout.z_end])
    if which == "end-neg":
        return s.rotate([0.0, 0.0, -90.0]).translate(
            [-layout.x_axis, layout.len_end / 2.0, layout.z_end])
    raise ValueError(f"unknown wall position {which!r}")


def walls_at(layout: Layout, opt: dict[str, Any], angle: float,
             end_angle: float | None = None) -> dict[str, geom.Solid]:
    """Every wall placed at an angle: 0 is folded flat, 90 is erect.

    `angle` drives the side walls and `end_angle` the end walls, so the two
    can be moved independently -- which is how the erection sequence is
    checked, since the real bin never raises both pairs at once.
    """
    if end_angle is None:
        end_angle = angle
    side = _wall_flat(layout, opt, "side")
    end = _wall_flat(layout, opt, "end")
    return {
        "side-neg": _place(side, layout, "side-neg", angle),
        "side-pos": _place(side, layout, "side-pos", angle),
        "end-pos": _place(end, layout, "end-pos", end_angle),
        "end-neg": _place(end, layout, "end-neg", end_angle),
    }


def _assembly(layout: Layout, opt: dict[str, Any],
              angle: float) -> geom.Solid:
    return geom.union([_base(layout, opt)],
                      list(walls_at(layout, opt, angle).values()))


register(FoldingBinGenerator())
