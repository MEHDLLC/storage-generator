"""Advent calendar: numbered snap-lid boxes that clip together into one piece.

What it makes
-------------
One box design, printed once per day. A lid per day with that day's number
on it, raised or recessed, inside a motif -- a circle, a star, a tree. Keys
that clip neighbouring boxes together on any side. And flat panels for the
outside faces, so once the calendar is assembled every joint is hidden and
the outside is a plain wall, or brick, or a pattern.

How the boxes join
------------------
Every side of every box carries the same dovetail slot, open at the top. Two
boxes are joined by a double-dovetail key -- a small bow-tie -- dropped into
the pair of facing slots. Because every side is the same, any side meets any
side, and a slot on the outside of the finished calendar takes the tab on the
back of a skin panel instead of a key. Nothing is glued and nothing is
permanent: pull the keys and the calendar is a box of boxes again.

How the lid holds
-----------------
The lid is a flat plate. It drops into the top of the box, past a short lip
on the inside of the rim, and lands on a ledge. The lip only runs along the
middle of each side, where the walls can bow a little to let the plate past;
at the corners, where they cannot, there is no lip. A tab on the front edge
sits in a notch in the rim so a small finger can pull the lid straight up.

A flat plate is the point. Anything with a skirt underneath has to print
upside down, and then whatever is raised on top prints as loose islands with
the whole lid bridged over them. A plate prints top-up, so the numbers, the
motif and the Lego studs all print exactly as drawn.

The number on the lid
---------------------
There is no font library here. The digits are a small stroke alphabet -- ten
polylines on a grid, drawn with round-ended strokes -- so they are a
few-dozen-line function rather than a dependency, and they come out looking
like the numbers on a children's clock, which is about right.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

from .. import geom, patterns
from ..generator import BuildResult, Generator, register
from ..mesh_io import Part, PartSet
from ..options import Option, OptionSet, Report
from ..units import mm_in

Point = tuple[float, float]

# Fits and clearances, per side unless stated.
KEY_FIT = 0.15            # dovetail key / tab to slot
SEAM = 0.6                # gap between two joined boxes: the key's neck
LID_GAP = 0.15            # lid plate to cavity wall
LIP = 0.4                 # how far the rim lip reaches in over the lid
LIP_H = 1.0               # height of that lip
LID_PLAY = 0.3            # headroom over the lid plate under the lip
SEAT = 1.0                # how far the ledge under the lid steps in
DOVETAIL_DEG = 15.0       # flank angle of the dovetail from its axis
SLOT_MOUTH = 5.0          # dovetail slot width at the face
SLOT_DEPTH = 1.8          # how far the slot goes into the wall
RELIEF_UP = 1.0           # raised decoration height
RELIEF_DOWN = 0.8         # recessed decoration depth
RING_W = 1.6              # width of a motif outline
LEGO_PITCH = 8.0          # stud pitch, the real thing
LEGO_STUD_D = 4.8
LEGO_STUD_H = 1.7
LEGO_BORDER = LEGO_STUD_D / 2.0 + 2.0   # first stud centre in from the edge
TAB_W = 8.0               # pull tab width
TAB_T = 1.4               # pull tab thickness
EMBED = 0.5               # overlap between solids that have to weld into one


OPTIONS = OptionSet([
    Option("days", 25, "How many boxes", kind="int", minimum=1, maximum=31,
           group="Calendar"),
    Option("start", 1, "The number on the first lid", kind="int", minimum=0,
           maximum=99, group="Calendar"),
    Option("arrangement", "tree", "How the boxes are laid out", kind="choice",
           choices=("tree", "grid", "row"), group="Calendar"),
    Option("numbering", "ordered", "Order of the numbers across the layout",
           kind="choice", choices=("ordered", "reversed", "scattered"),
           group="Calendar",
           default_note="ordered reads top row first; reversed puts the last "
                        "day at the top, where a tree has its star"),

    Option("shape", "box", "Footprint of each box", kind="choice",
           choices=("box", "hexagon", "triangle", "cylinder"), group="Box"),
    Option("width", 48.0, "Outside width of a box (across flats, or diameter)",
           unit=" mm", minimum=25, maximum=150, group="Box"),
    Option("length", 48.0, "Outside length of a box; box shape only",
           unit=" mm", minimum=25, maximum=150, group="Box"),
    Option("height", 40.0, "Outside height of a box", unit=" mm", minimum=15,
           maximum=150, group="Box"),
    Option("wall", 2.4, "Wall thickness", unit=" mm", minimum=1.6,
           maximum=6.0, group="Box"),
    Option("floor", 2.0, "Floor thickness", unit=" mm", minimum=1.2,
           maximum=6.0, group="Box"),

    Option("lid_thickness", 2.4, "Lid plate thickness", unit=" mm",
           minimum=1.6, maximum=5.0, group="Lid"),
    Option("frame", "tree", "Motif drawn round the number", kind="choice",
           choices=("none", "circle", "square", "star", "tree", "heart",
                    "snowflake"), group="Lid"),
    Option("number", "raised", "How the number stands", kind="choice",
           choices=("raised", "recessed"), group="Lid"),
    Option("lego", False, "Lego-compatible studs on the lid, round the motif",
           kind="bool", group="Lid"),
    Option("pull_tab", True, "A tab on the lid's front edge to lift it by",
           kind="bool", group="Lid"),

    Option("skin", "brick", "Finish on the outside panels", kind="choice",
           choices=("plain", "brick") + patterns.PATTERNS, group="Outside"),
    Option("skin_thickness", 2.0, "Outside panel thickness", unit=" mm",
           minimum=1.2, maximum=5.0, group="Outside"),

    Option("material", "pla", "Filament, for the weight estimate only",
           kind="choice", choices=("pla", "petg", "abs", "asa"),
           group="Output"),
    Option("bed_x", 256.0, "Printer bed width", unit=" mm", minimum=50,
           maximum=1200, group="Output", listed=False),
    Option("bed_y", 256.0, "Printer bed depth", unit=" mm", minimum=50,
           maximum=1200, group="Output", listed=False),
])


# ---------------------------------------------------------------------------
# a small stroke alphabet
# ---------------------------------------------------------------------------
#
# Each digit is drawn on a 10 x 16 grid as one or two polylines. Rendering
# them as round-ended strokes is what makes them read as a friendly numeral
# rather than a seven-segment display.

DIGITS: dict[str, list[list[Point]]] = {
    "0": [[(3, 1), (7, 1), (9, 3), (9, 13), (7, 15), (3, 15), (1, 13), (1, 3),
           (3, 1)]],
    "1": [[(2, 12), (5, 15), (5, 1)]],
    "2": [[(1, 12), (3, 15), (7, 15), (9, 12), (9, 10), (1, 2), (1, 1),
           (9, 1)]],
    "3": [[(1, 14), (9, 14), (4, 9), (7, 9), (9, 7), (9, 3), (7, 1), (3, 1),
           (1, 3)]],
    "4": [[(7, 1), (7, 15), (1, 5), (9, 5)]],
    "5": [[(9, 15), (1, 15), (1, 8), (6, 8), (9, 6), (9, 3), (7, 1), (3, 1),
           (1, 3)]],
    "6": [[(8, 15), (4, 15), (1, 12), (1, 3), (3, 1), (7, 1), (9, 3), (9, 6),
           (7, 8), (1, 8)]],
    "7": [[(1, 15), (9, 15), (4, 1)]],
    "8": [[(3, 8), (1, 10), (1, 13), (3, 15), (7, 15), (9, 13), (9, 10),
           (7, 8), (3, 8)],
          [(3, 8), (1, 6), (1, 3), (3, 1), (7, 1), (9, 3), (9, 6), (7, 8)]],
    "9": [[(2, 1), (6, 1), (9, 4), (9, 13), (7, 15), (3, 15), (1, 13),
           (1, 10), (3, 8), (9, 8)]],
}
GLYPH_W, GLYPH_H, STROKE = 10.0, 16.0, 2.4


def number_polygons(text: str, height: float,
                    centre: Point = (0.0, 0.0)) -> geom.Polygons:
    """The digits of `text`, `height` mm tall, centred on `centre`."""
    scale = height / GLYPH_H
    advance = (GLYPH_W + 2.0) * scale
    total = advance * len(text) - 2.0 * scale
    x = centre[0] - total / 2.0
    lines: list[list[Point]] = []
    for ch in text:
        for line in DIGITS[ch]:
            lines.append([(x + px * scale, centre[1] + (py - GLYPH_H / 2.0) * scale)
                          for px, py in line])
        x += advance
    return geom.stroke(lines, STROKE * scale)


# ---------------------------------------------------------------------------
# motifs
# ---------------------------------------------------------------------------
#
# Each motif is a unit shape about a centimetre wide when drawn at size 1;
# `scale` says how tall the number inside it may be as a fraction of the
# motif's size, and `drop` where that number's centre sits, so the number in
# a tree sits in the tree rather than in its star.

def _star(points: int = 5, inner: float = 0.42) -> list[Point]:
    out = []
    for i in range(points * 2):
        r = 0.5 if i % 2 == 0 else 0.5 * inner
        a = math.pi / 2.0 + i * math.pi / points
        out.append((r * math.cos(a), r * math.sin(a)))
    return out


def _heart(steps: int = 48) -> list[Point]:
    pts = []
    for i in range(steps):
        t = 2.0 * math.pi * i / steps
        x = 16.0 * math.sin(t) ** 3
        y = (13.0 * math.cos(t) - 5.0 * math.cos(2 * t) - 2.0 * math.cos(3 * t)
             - math.cos(4 * t))
        pts.append((x / 34.0, (y + 3.0) / 34.0))
    return pts[::-1]          # the parametric form runs clockwise


TREE: list[Point] = [
    (-0.08, -0.5), (0.08, -0.5), (0.08, -0.38), (0.5, -0.38), (0.24, -0.1),
    (0.42, -0.1), (0.18, 0.16), (0.32, 0.16), (0.0, 0.5), (-0.32, 0.16),
    (-0.18, 0.16), (-0.42, -0.1), (-0.24, -0.1), (-0.5, -0.38), (-0.08, -0.38),
]


@dataclass(frozen=True)
class Motif:
    outline: list[Point]      # unit shape, or [] for a stroke motif
    scale: float              # number height as a fraction of the motif size
    drop: float               # number centre, as a fraction of the size
    strokes: tuple = ()       # for the snowflake: polylines instead of a ring


def _snowflake() -> tuple:
    arms = []
    for k in range(6):
        a = math.radians(90.0 + 60.0 * k)
        ux, uy = math.cos(a), math.sin(a)
        arms.append([(0.24 * ux, 0.24 * uy), (0.5 * ux, 0.5 * uy)])
        for side in (-1.0, 1.0):
            b = a + side * math.radians(55.0)
            root = (0.36 * ux, 0.36 * uy)
            arms.append([root, (root[0] + 0.13 * math.cos(b),
                                root[1] + 0.13 * math.sin(b))])
    return tuple(arms)


MOTIFS: dict[str, Motif] = {
    "none": Motif([], 0.55, 0.0),
    "circle": Motif(geom.circle_profile(0.5, segments=64), 0.46, 0.0),
    "square": Motif([(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)],
                    0.5, 0.0),
    "star": Motif(_star(inner=0.48), 0.2, -0.03),
    "tree": Motif(TREE, 0.28, -0.06),
    "heart": Motif(_heart(), 0.34, 0.06),
    "snowflake": Motif([], 0.3, 0.0, _snowflake()),
}


def motif_polygons(name: str, size: float, ring: float,
                   centre: Point = (0.0, 0.0)) -> geom.Polygons:
    """The motif drawn `size` across, as the polygons of its relief."""
    motif = MOTIFS[name]
    if motif.strokes:
        lines = [[(centre[0] + x * size, centre[1] + y * size) for x, y in line]
                 for line in motif.strokes]
        return geom.stroke(lines, ring)
    if not motif.outline:
        return []
    shape = [(centre[0] + x * size, centre[1] + y * size)
             for x, y in motif.outline]
    return geom.ring(shape, ring, rounded=(name == "circle"))


def motif_inside(name: str, size: float, centre: Point = (0.0, 0.0)) -> geom.Polygons:
    """The clear space inside the motif, where the number may go."""
    motif = MOTIFS[name]
    if motif.outline:
        shape = [(centre[0] + x * size, centre[1] + y * size)
                 for x, y in motif.outline]
        return geom.offset_polygon(shape, -(RING_W + 0.8))
    if motif.strokes:
        return [geom.circle_profile(0.24 * size - RING_W / 2.0 - 0.8, centre)]
    return []


def _place_number(name: str, size: float, text: str,
                  centre: Point = (0.0, 0.0)) -> tuple[float, Point]:
    """Where the number goes: the biggest it can be inside the motif, and
    as close to the middle as that size allows.

    A fixed spot cannot work. The tree is narrow at the top, notched at
    every tier and has a trunk at the bottom; the star has five points and
    a small middle; and on a Lego lid the whole motif shrinks while the
    outline stays 1.6 mm wide, so whatever room there was closes up. So the
    number is tried at a range of sizes, largest first, and at a range of
    heights, most central first, and the first fit wins.
    """
    motif = MOTIFS[name]
    inside = motif_inside(name, size, centre)
    if not inside:
        return size * motif.scale, (centre[0], centre[1] + size * motif.drop)
    room = geom.flat(inside)
    prefer = centre[1] + size * motif.drop
    shifts = sorted((k * 0.03 * size for k in range(-10, 11)), key=abs)
    width_per_h = (len(text) * (GLYPH_W + 2.0) - 2.0) / GLYPH_H
    for h in [size * (0.5 - 0.025 * i) for i in range(17)]:
        half_w, half_h = width_per_h * h / 2.0 + STROKE * h / GLYPH_H / 2.0, h / 2.0
        for dy in shifts:
            cy = prefer + dy
            rect = [(centre[0] - half_w, cy - half_h), (centre[0] + half_w, cy - half_h),
                    (centre[0] + half_w, cy + half_h), (centre[0] - half_w, cy + half_h)]
            if (geom.flat([rect]) - room).area() < 1e-6:
                return h, (centre[0], cy)
    return size * 0.1, (centre[0], prefer)


def motif_clear(name: str, size: float, centre: Point = (0.0, 0.0)) -> list[Point]:
    """The outer boundary of the motif, for keeping other things off it."""
    motif = MOTIFS[name]
    if motif.outline:
        return [(centre[0] + x * size, centre[1] + y * size)
                for x, y in motif.outline]
    r = 0.5 * size if motif.strokes else 0.0
    return geom.circle_profile(r, centre) if r else []


# ---------------------------------------------------------------------------
# footprints
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Side:
    """One flat face that can take a connector."""
    mid: Point
    normal: Point
    length: float
    label: str            # which skin panel fits it


def _rot(v: Point, deg: float) -> Point:
    a = math.radians(deg)
    return (v[0] * math.cos(a) - v[1] * math.sin(a),
            v[0] * math.sin(a) + v[1] * math.cos(a))


def _regular(n: int, circumradius: float, start_deg: float) -> list[Point]:
    return [(circumradius * math.cos(math.radians(start_deg + 360.0 * i / n)),
             circumradius * math.sin(math.radians(start_deg + 360.0 * i / n)))
            for i in range(n)]


class Footprint:
    """Outline, cavity and connector faces for one box shape."""

    def __init__(self, opt: dict[str, Any]):
        shape, w, length = opt["shape"], opt["width"], opt["length"]
        self.shape = shape
        self.lug = 0.0
        if shape == "box":
            self.outline = [(-w / 2, -length / 2), (w / 2, -length / 2),
                            (w / 2, length / 2), (-w / 2, length / 2)]
            labels = ["w", "l", "w", "l"]
        elif shape == "hexagon":
            self.outline = _regular(6, w / math.sqrt(3.0), -90.0)
            labels = ["s"] * 6
        elif shape == "triangle":
            self.outline = _regular(3, w / math.sqrt(3.0), 90.0)
            labels = ["s"] * 3
        else:
            self.outline = geom.circle_profile(w / 2.0, segments=72)
            labels = []

        if shape == "cylinder":
            r = w / 2.0
            self.lug = 1.5
            lug_w = SLOT_MOUTH + 2 * SLOT_DEPTH * math.tan(
                math.radians(DOVETAIL_DEG)) + 4.0
            lugs = []
            self.sides = []
            for k in range(4):
                n = _rot((1.0, 0.0), 90.0 * k)
                t = (n[1], -n[0])
                far = r + self.lug
                lugs.append([
                    (n[0] * (r - 2.0) + t[0] * lug_w / 2, n[1] * (r - 2.0) + t[1] * lug_w / 2),
                    (n[0] * far + t[0] * lug_w / 2, n[1] * far + t[1] * lug_w / 2),
                    (n[0] * far - t[0] * lug_w / 2, n[1] * far - t[1] * lug_w / 2),
                    (n[0] * (r - 2.0) - t[0] * lug_w / 2, n[1] * (r - 2.0) - t[1] * lug_w / 2),
                ])
                self.sides.append(Side((n[0] * far, n[1] * far), n, lug_w, "s"))
            merged = geom.polygons_of(geom.flat([self.outline] + lugs))
            self.body = merged
            self.cavity = geom.offset_polygon(self.outline, -opt["wall"], rounded=True)
        else:
            self.body = [self.outline]
            self.cavity = geom.offset_polygon(self.outline, -opt["wall"])
            self.sides = []
            pts = self.outline
            for i, (p, q) in enumerate(zip(pts, pts[1:] + pts[:1])):
                mid = ((p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0)
                dx, dy = q[0] - p[0], q[1] - p[1]
                ln = math.hypot(dx, dy)
                normal = (dy / ln, -dx / ln)
                self.sides.append(Side(mid, normal, ln, labels[i]))

        # Overall size of the footprint, for pitch and for the bed check.
        xs = [x for poly in self.body for x, _ in poly]
        ys = [y for poly in self.body for _, y in poly]
        self.size = (max(xs) - min(xs), max(ys) - min(ys))
        self.cavity_poly = self.cavity[0] if self.cavity else []

    def side_lengths(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for s in self.sides:
            out.setdefault(s.label, s.length)
        return out

    def notch_frame(self) -> tuple[Point, Point, Point]:
        """Where the pull tab goes: (centre on the outer face, tangent, normal).

        On a polygon it sits on the first side, beside the slot rather than
        on it. On a cylinder the lugs are too narrow, so it sits on the rim
        between two of them.
        """
        if self.shape == "cylinder":
            n = _rot((1.0, 0.0), -60.0)
            r = self.size[0] / 2.0 - self.lug
            return ((n[0] * r, n[1] * r), (n[1], -n[0]), n)
        s = self.sides[0]
        t = (s.normal[1], -s.normal[0])
        along = SLOT_MOUTH / 2.0 + 2.0 + TAB_W / 2.0 + 0.5
        return ((s.mid[0] + t[0] * along, s.mid[1] + t[1] * along), t, s.normal)


# ---------------------------------------------------------------------------
# derived numbers
# ---------------------------------------------------------------------------

class Layout:
    def __init__(self, opt: dict[str, Any]):
        self.o = opt
        self.foot = Footprint(opt)
        self.h = opt["height"]
        self.wall = opt["wall"]
        self.floor = opt["floor"]
        self.plate = opt["lid_thickness"]
        self.skin_t = opt["skin_thickness"]

        self.slot_back = SLOT_MOUTH + 2.0 * SLOT_DEPTH * math.tan(
            math.radians(DOVETAIL_DEG))
        # Where the lid lands: lip above it, ledge below.
        self.seat_z = self.h - LIP_H - self.plate - LID_PLAY
        self.slot_z0 = self.floor
        self.key_h = self.h - self.floor - 1.0

        w, d = self.foot.size
        self.pitch = (w + SEAM, d + SEAM)
        lid = self.lid_outline()
        xs = [x for x, _ in lid]
        ys = [y for _, y in lid]
        self.lid_size = (max(xs) - min(xs), max(ys) - min(ys))

    def lid_outline(self) -> list[Point]:
        polys = geom.offset_polygon(self.foot.cavity_poly, -LID_GAP)
        return polys[0] if polys else []

    @property
    def interior_ml(self) -> float:
        inner = geom.offset_polygon(self.foot.cavity_poly, -SEAT)
        area = geom.flat(inner).area() if inner else 0.0
        return area * (self.seat_z - self.floor) / 1000.0


# ---------------------------------------------------------------------------
# the box
# ---------------------------------------------------------------------------

def _slot_polygon(side: Side, fit: float = 0.0, extra_depth: float = 0.0,
                  out: float = 0.5) -> list[Point]:
    """Dovetail profile at a side: the slot itself, or a tab to fit it."""
    t = (side.normal[1], -side.normal[0])
    n = side.normal
    mw = SLOT_MOUTH / 2.0 - fit
    bw = (SLOT_MOUTH + 2.0 * (SLOT_DEPTH - fit) * math.tan(
        math.radians(DOVETAIL_DEG))) / 2.0 - fit
    depth = SLOT_DEPTH - fit + extra_depth
    m = side.mid
    return [
        (m[0] - n[0] * depth - t[0] * bw, m[1] - n[1] * depth - t[1] * bw),
        (m[0] - n[0] * depth + t[0] * bw, m[1] - n[1] * depth + t[1] * bw),
        (m[0] + n[0] * out + t[0] * mw, m[1] + n[1] * out + t[1] * mw),
        (m[0] + n[0] * out - t[0] * mw, m[1] + n[1] * out - t[1] * mw),
    ]


def _rect_at(centre: Point, t: Point, n: Point, along: float,
             across: float) -> list[Point]:
    a, b = along / 2.0, across / 2.0
    return [
        (centre[0] - t[0] * a - n[0] * b, centre[1] - t[1] * a - n[1] * b),
        (centre[0] + t[0] * a - n[0] * b, centre[1] + t[1] * a - n[1] * b),
        (centre[0] + t[0] * a + n[0] * b, centre[1] + t[1] * a + n[1] * b),
        (centre[0] - t[0] * a + n[0] * b, centre[1] - t[1] * a + n[1] * b),
    ]


def _box(lay: Layout) -> geom.Solid:
    foot, h = lay.foot, lay.h
    body = geom.extrude(foot.body, 0.0, h)

    # A wider cavity above the seat, a narrower one below: the step between
    # them is the ledge the lid lands on.
    upper = geom.extrude(foot.cavity, lay.seat_z, h + 1.0)
    lower_poly = geom.offset_polygon(foot.cavity_poly, -SEAT)
    lower = geom.extrude(lower_poly, lay.floor, lay.seat_z + EMBED)
    body = geom.difference(body, [upper, lower])

    # The lip that holds the lid down, only along the middle of each side.
    lip_ring = geom.extrude(geom.ring(foot.cavity_poly, LIP + EMBED), h - LIP_H, h)
    lip_ring = lip_ring.translate([0.0, 0.0, 0.0])
    keep = []
    for s in foot.sides:
        t = (s.normal[1], -s.normal[0])
        span = s.length * 0.55 if foot.shape != "cylinder" else lay.foot.size[0] * 0.3
        keep.append(geom.prism_z(_rect_at(s.mid, t, s.normal, span,
                                          2.0 * (lay.wall + SEAT + 2.0)),
                                 h - LIP_H - 1.0, h + 1.0))
    lip = geom.intersection([lip_ring, geom.union(keep)])
    body = geom.union([body, lip])

    # Dovetail slots, open at the top, closed above the floor.
    slots = [geom.prism_z(_slot_polygon(s), lay.slot_z0, h + 1.0)
             for s in foot.sides]

    # Notch for the pull tab: through the wall, deep enough for a fingertip.
    cutters = slots
    if lay.o["pull_tab"]:
        centre, t, n = foot.notch_frame()
        cutters.append(geom.prism_z(
            _rect_at(centre, t, n, TAB_W + 1.0, 2.0 * (lay.wall + SEAT + 1.0)),
            lay.seat_z - 4.0, h + 1.0))
    return geom.difference(body, cutters)


# ---------------------------------------------------------------------------
# the lid
# ---------------------------------------------------------------------------

def _lid(lay: Layout, number: int, frame: str | None = None) -> geom.Solid:
    opt = lay.o
    frame = frame or opt["frame"]
    outline = lay.lid_outline()
    plate_t = lay.plate
    plate = geom.extrude([outline], 0.0, plate_t)

    if opt["pull_tab"]:
        centre, t, n = lay.foot.notch_frame()
        # From 1 mm inside the plate edge out to just short of the outer face.
        outer = 0.4
        inner = lay.wall + SEAT + LID_GAP + 1.0
        tab_centre = (centre[0] - n[0] * (outer + inner) / 2.0,
                      centre[1] - n[1] * (outer + inner) / 2.0)
        tab = geom.prism_z(_rect_at(tab_centre, t, n, TAB_W, inner - outer),
                           plate_t - TAB_T, plate_t)
        plate = geom.union([plate, tab])

    # Decoration: the motif ring and the number, raised or recessed. With
    # studs on, the motif gives up a border one stud wide all round. It is
    # sized by trying: a motif that fits a square plate by its bounding box
    # pokes its corners through a round or triangular one.
    margin = LEGO_BORDER + 2.0 if opt["lego"] else 3.0
    room = geom.flat(geom.offset_polygon(outline, -margin))
    motif = MOTIFS[frame]
    centre = (0.0, 0.0)
    size = min(lay.lid_size) - 2.0 * margin
    for _ in range(30):
        relief = motif_polygons(frame, size, RING_W, centre)
        num_h, num_c = _place_number(frame, size, str(number), centre)
        relief += number_polygons(str(number), num_h, num_c)
        if (geom.flat(relief) - room).area() < 1e-6:
            break
        size *= 0.95
    # And never past the plate edge, whatever the loop settled on.
    relief = geom.polygons_of(geom.flat(relief) ^ geom.flat(
        geom.offset_polygon(outline, -0.6)))

    if opt["number"] == "raised":
        deco = geom.extrude(relief, plate_t - EMBED, plate_t + RELIEF_UP)
        plate = geom.union([plate, deco])
    else:
        deco = geom.extrude(relief, plate_t - RELIEF_DOWN, plate_t + 1.0)
        plate = geom.difference(plate, [deco])

    if opt["lego"]:
        plate = geom.union([plate, _studs(lay, outline, frame, size,
                                          num_h, num_c)])
    return plate


def _studs(lay: Layout, outline: list[Point], frame: str, size: float,
           num_h: float, num_c: Point) -> geom.Solid:
    """A grid of studs over the lid, kept off the motif and the number."""
    plate_t = lay.plate
    inner = geom.flat(geom.offset_polygon(outline, -(LEGO_STUD_D / 2.0 + 0.8)))
    clear = motif_clear(frame, size)
    if not clear:
        w = num_h * (GLYPH_W + 2.0) / GLYPH_H * 2.0
        clear = [(num_c[0] - w / 2, num_c[1] - num_h / 2 - 1),
                 (num_c[0] + w / 2, num_c[1] - num_h / 2 - 1),
                 (num_c[0] + w / 2, num_c[1] + num_h / 2 + 1),
                 (num_c[0] - w / 2, num_c[1] + num_h / 2 + 1)]
    forbidden = geom.flat(geom.offset_polygon(clear, LEGO_STUD_D / 2.0 + 0.6,
                                              rounded=True))
    allowed = inner - forbidden

    # The grid starts one stud in from the edge rather than at the centre,
    # so a lid always gets its outer ring of studs whatever its size.
    studs = []
    w, d = lay.lid_size
    xs = [-w / 2.0 + LEGO_BORDER + i * LEGO_PITCH
          for i in range(int((w - 2 * LEGO_BORDER) // LEGO_PITCH) + 1)]
    ys = [-d / 2.0 + LEGO_BORDER + j * LEGO_PITCH
          for j in range(int((d - 2 * LEGO_BORDER) // LEGO_PITCH) + 1)]
    xs = [x - (xs[0] + xs[-1]) / 2.0 for x in xs]
    ys = [y - (ys[0] + ys[-1]) / 2.0 for y in ys]
    for x in xs:
        for y in ys:
            probe = geom.flat([geom.circle_profile(0.3, (x, y), 8)])
            # `^` is intersection in this binding, not exclusive-or.
            if (allowed ^ probe).area() > 0.9 * probe.area():
                studs.append(geom.circle_profile(LEGO_STUD_D / 2.0, (x, y), 32))
    if not studs:
        return geom.empty()
    return geom.extrude(studs, plate_t - EMBED, plate_t + LEGO_STUD_H)


# ---------------------------------------------------------------------------
# keys and skins
# ---------------------------------------------------------------------------

def _key(lay: Layout) -> geom.Solid:
    """A double dovetail, lying on one of its wide faces to print."""
    fit = KEY_FIT
    mw = SLOT_MOUTH / 2.0 - fit
    bw = (SLOT_MOUTH + 2.0 * (SLOT_DEPTH - fit) * math.tan(
        math.radians(DOVETAIL_DEG))) / 2.0 - fit
    d = SLOT_DEPTH - fit
    g = SEAM / 2.0
    profile = [
        (g + d, -bw), (g + d, bw), (g, mw), (-g, mw),
        (-g - d, bw), (-g - d, -bw), (-g, -mw), (g, -mw),
    ]
    standing = geom.prism_z(profile, 0.0, lay.key_h)
    # Rotate so a tail's back face is on the bed and the length runs along Y.
    return standing.rotate([0.0, 90.0, 0.0]).translate([g + d, 0.0, 0.0])


def _skin(lay: Layout, label: str, ends: str) -> geom.Solid:
    """One outside panel, face down, tab up, ends cut for their corners.

    `ends` is two letters, one per end: m for an outer mitre (the panel runs
    on past the box corner and meets its neighbour at 45 degrees), s for a
    square cut, n for an inner mitre at a concave corner.
    """
    length = lay.foot.side_lengths()[label]
    t = lay.skin_t
    half = length / 2.0

    def end(kind: str, sign: float) -> tuple[float, float]:
        # (x at the back face, x at the front face)
        if kind == "m":
            return sign * half, sign * (half + t)
        if kind == "n":
            return sign * half, sign * (half - t)
        return sign * half, sign * half

    lb, lf = end(ends[0], -1.0)
    rb, rf = end(ends[1], 1.0)
    # Local frame: x along the face, y outward (front face at y = t).
    outline = [(lb, 0.0), (rb, 0.0), (rf, t), (lf, t)]
    panel = geom.prism_z(outline, 0.0, lay.h)

    # The tab is a slot's negative, so it is drawn as a slot whose "wall" is
    # the air behind the panel: its mouth is buried in the panel by EMBED and
    # its tail reaches out toward the box.
    side = Side((0.0, 0.0), (0.0, 1.0), length, label)
    tab = geom.prism_z(_slot_polygon(side, KEY_FIT, 0.0, out=EMBED),
                       lay.slot_z0 + 0.4, lay.h)
    panel = geom.union([panel, tab])

    panel = geom.difference(panel, _skin_relief(lay, length, ends))
    # Face down for printing: the front (y = t) becomes z = 0, tab up.
    return panel.rotate([-90.0, 0.0, 0.0]).translate([0.0, 0.0, t])


def _skin_relief(lay: Layout, length: float, ends: str) -> list[geom.Solid]:
    """Grooves in the front face: mortar lines, or a pattern as pockets."""
    style = lay.o["skin"]
    t = lay.skin_t
    depth = min(0.6, t - 0.8)
    if style == "plain" or depth <= 0.2:
        return []
    half = length / 2.0
    y0, y1 = t - depth, t + 1.0
    cutters: list[geom.Solid] = []
    if style == "brick":
        brick_l, brick_h, mortar = 12.0, 6.0, 1.0
        z = brick_h
        row = 0
        while z < lay.h:
            cutters.append(geom.box([length + 2 * t + 2, depth + 1.0, mortar],
                                    at=[-half - t - 1, y0, z - mortar / 2]))
            z += brick_h
        z = 0.0
        while z < lay.h:
            x = -half - t + (brick_l / 2.0 if row % 2 else 0.0)
            while x < half + t:
                cutters.append(geom.box([mortar, depth + 1.0, brick_h],
                                        at=[x - mortar / 2, y0, z]))
                x += brick_l
            z += brick_h
            row += 1
        return cutters
    margin = 4.0
    rect = (-half + margin, margin, half - margin, lay.h - margin)
    cell = min(patterns.default_cell(style), 10.0)
    rib = max(2.0, patterns.default_rib(style) * 0.6)
    for poly in patterns.tile(style, rect, cell, rib):
        cutters.append(geom.prism_y([(a, b) for a, b in poly], y0, y1))
    return cutters


# ---------------------------------------------------------------------------
# arrangement
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Cell:
    ix: int
    iy: int          # row index, 0 at the top
    number: int
    flip: bool = False


def _rows_for(opt: dict[str, Any]) -> list[int]:
    n, style = opt["days"], opt["arrangement"]
    if style == "row":
        return [n]
    if style == "tree":
        rows, total, width = [], 0, 1
        while total < n:
            take = min(width, n - total)
            rows.append(take)
            total += take
            width += 2
        return rows
    cols = math.ceil(math.sqrt(n))
    for c in range(cols, 2 * cols + 1):
        if n % c == 0:
            cols = c
            break
    rows = []
    left = n
    while left > 0:
        rows.append(min(cols, left))
        left -= cols
    return rows


def _cells(opt: dict[str, Any]) -> list[Cell]:
    rows = _rows_for(opt)
    widest = max(rows)
    cells: list[Cell] = []
    for iy, count in enumerate(rows):
        # Centre every row on whole cells so a grid stays a grid.
        offset = (widest - count) // 2
        for i in range(count):
            cells.append(Cell(offset + i, iy, 0))
    numbers = list(range(opt["start"], opt["start"] + len(cells)))
    if opt["numbering"] == "reversed":
        numbers.reverse()
    elif opt["numbering"] == "scattered":
        random.Random(opt["days"] * 31 + opt["start"]).shuffle(numbers)
    return [Cell(c.ix, c.iy, num, flip=(c.ix + c.iy) % 2 == 1)
            for c, num in zip(cells, numbers)]


def _position(lay: Layout, cell: Cell, widest: int, nrows: int) -> Point:
    """Where a cell's box sits, in mm, with row 0 at the top."""
    px, py = lay.pitch
    shape = lay.foot.shape
    x = (cell.ix - (widest - 1) / 2.0) * px
    y = ((nrows - 1) / 2.0 - cell.iy) * py
    if shape == "hexagon":
        py = lay.foot.size[1] * 0.75 + SEAM
        y = ((nrows - 1) / 2.0 - cell.iy) * py
        # Every other row is staggered by half a hexagon.
        x += (px / 2.0 if cell.iy % 2 else 0.0)
    if shape == "triangle":
        x = (cell.ix - (widest - 1) / 2.0) * (px / 2.0 + SEAM / 2.0)
    return (x, y)


def _tiles_on_grid(shape: str) -> bool:
    return shape in ("box", "cylinder")


def _perimeter(lay: Layout, cells: list[Cell]) -> tuple[dict[tuple[str, str], int], int]:
    """Count skin panels by variant, and keys, for a grid arrangement."""
    occupied = {(c.ix, c.iy) for c in cells}
    panels: dict[tuple[str, str], int] = {}
    keys = 0
    for c in cells:
        for s in lay.foot.sides:
            d = (round(s.normal[0]), -round(s.normal[1]))   # row index grows downward
            across = (c.ix + d[0], c.iy + d[1])
            if across in occupied:
                # Each joint counted once, from the cell on its low side.
                if (d[0], d[1]) in ((1, 0), (0, 1)):
                    keys += 1
                continue
            t = (d[1], -d[0])
            kinds = []
            for sign in (-1, 1):
                beside = (c.ix + sign * t[0], c.iy + sign * t[1])
                diagonal = (beside[0] + d[0], beside[1] + d[1])
                if beside not in occupied:
                    kinds.append("m")
                elif diagonal in occupied:
                    kinds.append("n")
                else:
                    kinds.append("s")
            key = (s.label, kinds[0] + kinds[1])
            panels[key] = panels.get(key, 0) + 1
    return panels, keys


# ---------------------------------------------------------------------------
# the generator
# ---------------------------------------------------------------------------

class AdventCalendarGenerator(Generator):
    key = "advent-calendar"
    title = "Advent calendar"
    summary = (
        "Numbered snap-lid boxes that clip together on every side into one "
        "calendar, with outside panels that hide every joint."
    )
    tags = ("advent calendar", "christmas", "countdown", "storage boxes",
            "snap lid", "modular", "parametric", "no supports", "kids")
    options = OPTIONS

    def build(self, opt: dict[str, Any]) -> BuildResult:
        report = Report()
        opt = dict(opt)
        lay = Layout(opt)
        _validate(lay, report)
        cells = _cells(opt)
        rows = _rows_for(opt)
        widest, nrows = max(rows), len(rows)

        parts = PartSet()
        box = _box(lay)
        parts.add("box", box, copies=opt["days"],
                  note="One per day. Prints open side up.")

        # The box at the tip of a tree gets a star instead of another tree.
        tip = cells[0].number if (opt["arrangement"] == "tree"
                                  and opt["frame"] == "tree") else None
        lids = {}
        for c in sorted(cells, key=lambda c: c.number):
            frame = "star" if c.number == tip else None
            lids[c.number] = _lid(lay, c.number, frame)
            parts.add(f"lid-{c.number:02d}", lids[c.number],
                      note=f"Lid for day {c.number}. Prints face up."
                      + (" This one sits at the top of the tree, so it "
                         "carries the star." if frame else ""))

        key = _key(lay)
        if _tiles_on_grid(opt["shape"]):
            panels, n_keys = _perimeter(lay, cells)
        else:
            panels, n_keys = {(lbl, "ss"): 0 for lbl in lay.foot.side_lengths()}, 0
            report.note(
                f"{opt['shape'].capitalize()} boxes tile in offset rows, so "
                "the number of keys and outside panels depends on how you "
                "put them together. One square-ended panel is included; "
                "print as many as your outside has faces, plus a key per "
                "joint.")
        parts.add("key", key, copies=max(n_keys, 1),
                  note="Double dovetail. Drops into two facing slots to join "
                       "a pair of boxes. Prints lying flat.")
        skins = {}
        for (label, ends), count in sorted(panels.items()):
            name = f"skin-{label}-{ends}"
            skins[(label, ends)] = _skin(lay, label, ends)
            parts.add(name, skins[(label, ends)], copies=max(count, 1),
                      note=_skin_note(label, ends))

        _lay_out_on_plate(parts, lay)

        assembly = _assembly(lay, cells, lids, skins, widest, nrows)
        facts = _facts(lay, opt, cells, n_keys, panels, assembly)
        return BuildResult(
            parts=parts,
            effective_options=opt,
            context_parts=[Part("assembled", assembly)],
            report=report,
            facts=facts,
            highlights=_highlights(lay, opt, facts),
            print_notes=_print_notes(lay, opt, facts),
        )

    def slug(self, opt: dict[str, Any]) -> str:
        return (f"advent-calendar_{opt['days']}x{opt['shape']}_"
                f"{opt['width']:.0f}x{opt['length']:.0f}x{opt['height']:.0f}_"
                f"{opt['frame']}")


def _skin_note(label: str, ends: str) -> str:
    where = {"w": "a long side", "l": "a short side", "s": "a side"}[label]
    cut = {"m": "mitred for an outside corner", "s": "square",
           "n": "mitred for an inside corner"}
    return (f"Outside panel for {where}; left end {cut[ends[0]]}, right end "
            f"{cut[ends[1]]}. Prints face down.")


def _validate(lay: Layout, report: Report) -> None:
    opt = lay.o
    if opt["shape"] != "box" and abs(opt["length"] - opt["width"]) > 1e-9:
        report.note("Only the box shape has a separate length; the other "
                    "shapes are set by --width alone.")
    if opt["shape"] == "cylinder" and opt["lego"]:
        pass
    inner = min(lay.lid_size)
    if inner < 22.0:
        report.warn(
            f"The lid is only {inner:.0f} mm across inside the walls, which "
            "leaves a very small number. 30 mm or more reads much better.")
    if lay.seat_z - lay.floor < 8.0:
        report.warn(
            "There is under 8 mm of room inside each box under the lid. "
            "Increase --height.")
    if opt["lego"] and min(lay.lid_size) < LEGO_PITCH * 3:
        report.warn("The lid is too small to carry a useful ring of studs.")
    for s in lay.foot.sides:
        if s.length < lay.slot_back + 4.0:
            report.warn(
                f"A {s.length:.0f} mm side barely fits its dovetail slot. "
                "Increase --width.")
            break


def _lay_out_on_plate(parts: PartSet, lay: Layout) -> None:
    """Spread the parts out so the preview reads as a plate of parts.

    The STL writer drops every part to the origin regardless, and the 3MF
    lays them out for itself, so this only affects the picture.
    """
    gap = 6.0
    x = y = 0.0
    row_h = 0.0
    per_row = 6
    count = 0
    for part in parts.parts:
        b = part.solid.bounding_box()
        w, d = b[3] - b[0], b[4] - b[1]
        if count and count % per_row == 0:
            x = 0.0
            y -= row_h + gap
            row_h = 0.0
        part.solid = part.solid.translate([x - b[0], y - b[4], -b[2]])
        x += w + gap
        row_h = max(row_h, d)
        count += 1


def _assembly(lay: Layout, cells: list[Cell], lids: dict[int, geom.Solid],
              skins: dict, widest: int, nrows: int) -> geom.Solid:
    """The calendar put together and stood up, as it would hang on a wall."""
    box = _box(lay)
    pieces = []
    for c in cells:
        x, y = _position(lay, c, widest, nrows)
        rot = 180.0 if (c.flip and lay.foot.shape == "triangle") else 0.0
        lid = lids[c.number].translate([0.0, 0.0, lay.h - LIP_H - lay.plate - LID_PLAY / 2.0])
        one = geom.union([box, lid]).rotate([0.0, 0.0, rot]).translate([x, y, 0.0])
        pieces.append(one)

    if _tiles_on_grid(lay.foot.shape) and skins:
        occupied = {(c.ix, c.iy): c for c in cells}
        for c in cells:
            x, y = _position(lay, c, widest, nrows)
            for s in lay.foot.sides:
                d = (round(s.normal[0]), -round(s.normal[1]))
                if (c.ix + d[0], c.iy + d[1]) in occupied:
                    continue
                t = (d[1], -d[0])
                kinds = ""
                for sign in (-1, 1):
                    beside = (c.ix + sign * t[0], c.iy + sign * t[1])
                    diagonal = (beside[0] + d[0], beside[1] + d[1])
                    kinds += ("m" if beside not in occupied
                              else "n" if diagonal in occupied else "s")
                panel = skins.get((s.label, kinds))
                if panel is None:
                    continue
                # Undo the print pose, then turn it to face outward.
                upright = panel.translate([0.0, 0.0, -lay.skin_t]).rotate([90.0, 0.0, 0.0])
                angle = math.degrees(math.atan2(-s.normal[0], s.normal[1]))
                placed = upright.rotate([0.0, 0.0, angle]).translate(
                    [x + s.mid[0] + s.normal[0] * SEAM / 2.0,
                     y + s.mid[1] + s.normal[1] * SEAM / 2.0, 0.0])
                pieces.append(placed)

    flat = geom.union(pieces)
    # Stand it up: rows that ran along Y now run up Z, lids facing -Y, and
    # set it back a little so the plate of parts lies in front of it.
    b = flat.bounding_box()
    return flat.rotate([90.0, 0.0, 0.0]).translate([0.0, 24.0, -b[1]])


def _facts(lay: Layout, opt: dict[str, Any], cells: list[Cell], n_keys: int,
           panels: dict, assembly: geom.Solid) -> dict[str, Any]:
    b = assembly.bounding_box()
    rows = _rows_for(opt)
    return {
        "days": opt["days"],
        "numbers": [c.number for c in cells],
        "rows": rows,
        "box_outside_mm": [round(lay.foot.size[0], 1), round(lay.foot.size[1], 1),
                           round(lay.h, 1)],
        "box_inside_ml": round(lay.interior_ml, 1),
        "calendar_mm": [round(b[3] - b[0], 1), round(b[5] - b[2], 1),
                        round(b[4] - b[1], 1)],
        "outside_mm": [round(b[3] - b[0], 1), round(b[4] - b[1], 1),
                       round(b[5] - b[2], 1)],
        "keys": n_keys,
        "panels": {f"{k[0]}-{k[1]}": v for k, v in panels.items()},
        "panels_total": sum(panels.values()),
        "parts_to_print": opt["days"] * 2 + n_keys + sum(panels.values()),
        "frame": opt["frame"],
        "number": opt["number"],
        "lego": opt["lego"],
        "supports_required": False,
    }


def _highlights(lay: Layout, opt: dict[str, Any], facts: dict[str, Any]) -> list[str]:
    w, h, d = facts["calendar_mm"]
    rows = facts["rows"]
    shape = {"tree": "a tree", "grid": "a grid", "row": "a single row"}[opt["arrangement"]]
    items = [
        f"{opt['days']} boxes, {mm_in(lay.foot.size[0])} x "
        f"{mm_in(lay.foot.size[1])} x {mm_in(lay.h)} each, about "
        f"{facts['box_inside_ml']:.0f} ml inside",
        f"Assembled as {shape} of {len(rows)} rows: {mm_in(w)} wide by "
        f"{mm_in(h)} tall",
        "Lids snap in and pull out by a tab; the number is "
        + ("raised" if opt["number"] == "raised" else "recessed")
        + (f" inside a {opt['frame']}" if opt["frame"] != "none" else ""),
        "Every side of every box takes the same dovetail, so any box joins "
        "any box and the outside panels hide every joint",
        "Prints flat with no supports, in as many colours as you have days",
    ]
    if opt["lego"]:
        items.append("Lego-compatible studs on every lid")
    return items


def _print_notes(lay: Layout, opt: dict[str, Any], facts: dict[str, Any]) -> list[str]:
    notes = [
        f"Boxes print open side up, lids face up, keys and panels flat as "
        f"supplied. No supports anywhere.",
        f"Print {opt['days']} boxes, one of each lid, {facts['keys']} keys and "
        f"{facts['panels_total']} outside panels: "
        f"{facts['parts_to_print']} parts in all.",
        "To join two boxes, hold them face to face and drop a key into the "
        "pair of slots from the top. To fit a panel, slide its tab down an "
        "outside slot the same way.",
        "The lid drops in and clicks under the lip on each side. Lift it by "
        "the tab at the front.",
        "0.2 mm layers. Two perimeters are plenty for the boxes; the lids "
        "look best with the top surface ironed if your slicer offers it.",
    ]
    if opt["number"] == "raised":
        notes.append("A colour change at the height of the lid plate puts "
                     "the numbers in a second colour with no extra work.")
    return notes


register(AdventCalendarGenerator())
