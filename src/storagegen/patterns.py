"""Cut-out patterns for panels and plates.

A panel with holes in it is lighter, faster to print and easier to see
through, and the holes are most of what the finished thing looks like. This
module turns a rectangular region into a list of closed 2-D profiles to
subtract from it.

Everything here is chosen so a *vertical* panel still prints without support.
The rule that matters is that no cut may leave a surface above it shallower
than 45 degrees, so:

- hexagons sit flat-top, not point-top. A point-top hexagon's upper edges lie
  at 30 degrees from horizontal, which is an overhang no printer will hold; a
  flat-top hexagon's are at 60 degrees, and its one horizontal span is capped
  at `max_bridge`.
- diamonds are square-on-corner, so their upper edges sit at exactly the
  45-degree limit.
- triangles point up, never down.
- squares and slots get their top corners taken off at 45 degrees, leaving a
  flat span no longer than `max_bridge`.
- circles close over gradually and are left alone; keep them modest.

The profiles come back in whatever plane the caller is working in: `(x, z)`
for a back panel, `(y, z)` for a side, `(x, y)` for a plate. The second
coordinate is the one that must point up for the overhang rules to hold,
which is true for every panel and does not matter for a flat plate.
"""

from __future__ import annotations

import math
from typing import Callable, Iterable, Sequence

Point2 = tuple[float, float]
Rect = tuple[float, float, float, float]      # a0, b0, a1, b1

PATTERNS: tuple[str, ...] = (
    "windows", "grid", "honeycomb", "diamond", "round", "triangle",
)

# The longest flat span a cut may leave above itself. Short enough that any
# slicer bridges it without thinking about it.
MAX_BRIDGE = 12.0

# Below this a hole stops being a hole and starts being a defect.
MIN_HOLE = 4.0

EPS = 1e-9
SQRT3 = math.sqrt(3.0)


# Each pattern reads best at its own scale, so `cell` and `rib` default per
# pattern rather than sharing one number that suits none of them.
DEFAULT_CELL: dict[str, float] = {
    "windows": 28.0, "grid": 15.0, "honeycomb": 14.0,
    "diamond": 16.0, "round": 14.0, "triangle": 20.0,
}
DEFAULT_RIB: dict[str, float] = {
    "windows": 8.0, "grid": 5.0, "honeycomb": 5.0,
    "diamond": 6.0, "round": 5.0, "triangle": 5.0,
}


def default_cell(style: str) -> float:
    return DEFAULT_CELL.get(style, 16.0)


def default_rib(style: str) -> float:
    return DEFAULT_RIB.get(style, 5.0)


def tile(style: str, rect: Rect, cell: float, rib: float,
         max_bridge: float = MAX_BRIDGE) -> list[list[Point2]]:
    """Fill `rect` with `style` cut-outs of about `cell` across, `rib` apart.

    Only whole cells are placed, and the result is centred in the region, so
    a pattern never trails off into slivers at the edge. An empty list means
    nothing fitted and the caller should leave the surface solid.
    """
    try:
        builder = _BUILDERS[style]
    except KeyError:
        raise ValueError(
            f"unknown pattern {style!r}; available: " + ", ".join(PATTERNS)
        ) from None

    a0, b0, a1, b1 = rect
    if a1 - a0 < MIN_HOLE or b1 - b0 < MIN_HOLE:
        return []
    if cell < MIN_HOLE or rib <= 0:
        return []

    return _recentre(builder(rect, cell, rib, max_bridge), rect)


def describe(style: str, cell: float, rib: float,
             max_bridge: float = MAX_BRIDGE) -> str:
    """One line about the pattern, for the listing."""
    if style == "honeycomb":
        side = min(cell / SQRT3, max_bridge)
        return (
            f"Honeycomb, {side * SQRT3:.0f} mm across the flats with "
            f"{rib:.0f} mm webs"
        )
    if style == "windows":
        return (
            f"Large windows about {cell:.0f} mm across with {rib:.0f} mm webs"
        )
    noun = {"grid": "Square holes", "diamond": "Diamonds",
            "round": "Round holes", "triangle": "Triangles"}[style]
    return f"{noun} about {cell:.0f} mm across with {rib:.0f} mm webs"


# ---------------------------------------------------------------------------
# the patterns
# ---------------------------------------------------------------------------


def _windows(rect: Rect, cell: float, rib: float,
             max_bridge: float) -> list[list[Point2]]:
    """A few large openings running the full height of the region.

    Not a texture: one opening per bin's worth of panel, corners taken off.
    """
    a0, b0, a1, b1 = rect
    width = a1 - a0
    count = max(1, round(width / (cell + rib)))
    while count >= 1:
        opening = (width - (count - 1) * rib) / count
        if opening >= MIN_HOLE:
            break
        count -= 1
    else:
        return []
    return [
        _chamfered_rect(
            a0 + index * (opening + rib), b0,
            a0 + index * (opening + rib) + opening, b1, max_bridge,
        )
        for index in range(count)
    ]


def _grid(rect: Rect, cell: float, rib: float,
          max_bridge: float) -> list[list[Point2]]:
    pitch = cell + rib
    return [
        _chamfered_rect(a - cell / 2, b - cell / 2,
                        a + cell / 2, b + cell / 2, max_bridge)
        for a, b in _lattice(rect, pitch, pitch, cell, cell)
    ]


def _honeycomb(rect: Rect, cell: float, rib: float,
               max_bridge: float) -> list[list[Point2]]:
    """Flat-top hexagons.

    `cell` is the distance across the flats. The hexagon shrinks if that would
    make its flat top longer than a comfortable bridge.
    """
    side = min(cell / SQRT3, max_bridge)
    across = side * SQRT3
    pitch = across + rib
    half = side / 2.0
    profiles = []
    for a, b in _lattice(rect, pitch * SQRT3 / 2.0, pitch, 2 * side, across,
                         col_shift=0.5):
        profiles.append([
            (a - side, b),
            (a - half, b - across / 2.0),
            (a + half, b - across / 2.0),
            (a + side, b),
            (a + half, b + across / 2.0),
            (a - half, b + across / 2.0),
        ])
    return profiles


def _diamond(rect: Rect, cell: float, rib: float,
             max_bridge: float) -> list[list[Point2]]:
    """Squares stood on a corner: upper edges at exactly 45 degrees."""
    half = cell / 2.0
    return [
        [(a, b - half), (a + half, b), (a, b + half), (a - half, b)]
        for a, b in _lattice(rect, cell + rib, cell + rib, cell, cell)
    ]


def _round(rect: Rect, cell: float, rib: float,
           max_bridge: float) -> list[list[Point2]]:
    radius = cell / 2.0
    segments = max(16, int(cell * 2))
    pitch = cell + rib
    profiles = []
    for a, b in _lattice(rect, pitch, pitch * SQRT3 / 2.0, cell, cell,
                         row_shift=0.5):
        profiles.append([
            (
                a + radius * math.cos(2 * math.pi * i / segments),
                b + radius * math.sin(2 * math.pi * i / segments),
            )
            for i in range(segments)
        ])
    return profiles


def _triangle(rect: Rect, cell: float, rib: float,
              max_bridge: float) -> list[list[Point2]]:
    """Equilateral triangles, apex up. A downward apex would be a flat roof."""
    height = cell * SQRT3 / 2.0
    half = cell / 2.0
    return [
        [(a - half, b - height / 2.0), (a + half, b - height / 2.0),
         (a, b + height / 2.0)]
        for a, b in _lattice(rect, cell + rib, height + rib, cell, height,
                             row_shift=0.5)
    ]


_BUILDERS: dict[str, Callable[[Rect, float, float, float], list[list[Point2]]]] = {
    "windows": _windows,
    "grid": _grid,
    "honeycomb": _honeycomb,
    "diamond": _diamond,
    "round": _round,
    "triangle": _triangle,
}


# ---------------------------------------------------------------------------
# placement
# ---------------------------------------------------------------------------


def _lattice(rect: Rect, dx: float, dy: float, width: float, height: float,
             row_shift: float = 0.0, col_shift: float = 0.0
             ) -> list[tuple[float, float]]:
    """Centres of every cell that fits whole inside `rect`.

    `row_shift` offsets alternate rows along `a`, `col_shift` offsets alternate
    columns along `b`; between them they cover both ways of interlocking a
    staggered pattern.
    """
    if dx <= EPS or dy <= EPS:
        return []
    # Anchoring on the region's centre puts a cell *at* the centre, so an even
    # number of rows or columns can never fit. Try the half-step phases too and
    # keep whichever packs the most cells.
    best: list[tuple[float, float]] = []
    for phase_a in (0.0, 0.5):
        for phase_b in (0.0, 0.5):
            found = _lattice_phase(rect, dx, dy, width, height,
                                   row_shift, col_shift, phase_a, phase_b)
            if len(found) > len(best):
                best = found
    return best


def _lattice_phase(rect: Rect, dx: float, dy: float, width: float,
                   height: float, row_shift: float, col_shift: float,
                   phase_a: float, phase_b: float) -> list[tuple[float, float]]:
    a0, b0, a1, b1 = rect
    centre_a = (a0 + a1) / 2.0 + phase_a * dx
    centre_b = (b0 + b1) / 2.0 + phase_b * dy
    reach_i = int((a1 - a0) / dx) + 2
    reach_j = int((b1 - b0) / dy) + 2

    out = []
    for j in range(-reach_j, reach_j + 1):
        for i in range(-reach_i, reach_i + 1):
            a = centre_a + i * dx + (row_shift * dx if j % 2 else 0.0)
            b = centre_b + j * dy + (col_shift * dy if i % 2 else 0.0)
            if (a - width / 2.0 >= a0 - EPS and a + width / 2.0 <= a1 + EPS
                    and b - height / 2.0 >= b0 - EPS
                    and b + height / 2.0 <= b1 + EPS):
                out.append((a, b))
    return sorted(out)


def _recentre(profiles: Sequence[Sequence[Point2]],
              rect: Rect) -> list[list[Point2]]:
    """Nudge the whole pattern so its spare room is shared evenly.

    Staggered rows do not land symmetrically about the region's centre on
    their own, and a pattern crowded against one edge reads as a mistake.
    """
    if not profiles:
        return []
    points = [point for profile in profiles for point in profile]
    lo_a = min(p[0] for p in points)
    hi_a = max(p[0] for p in points)
    lo_b = min(p[1] for p in points)
    hi_b = max(p[1] for p in points)
    a0, b0, a1, b1 = rect
    shift_a = ((a0 + a1) - (lo_a + hi_a)) / 2.0
    shift_b = ((b0 + b1) - (lo_b + hi_b)) / 2.0
    return [
        [(a + shift_a, b + shift_b) for a, b in profile] for profile in profiles
    ]


def _chamfered_rect(a0: float, b0: float, a1: float, b1: float,
                    max_bridge: float) -> list[Point2]:
    """A rectangle with 45-degree corners.

    The top corners are the point: a plain rectangle leaves its whole top edge
    bridging across open air part-way up a wall, and taking the corners off at
    45 degrees reduces that to a short flat span.
    """
    width, height = a1 - a0, b1 - b0
    top = max((width - max_bridge) / 2.0, 0.0)
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
