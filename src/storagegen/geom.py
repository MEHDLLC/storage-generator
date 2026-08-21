"""Solid-geometry helpers on top of manifold3d.

manifold3d is used rather than a mesh library with bolted-on booleans because
it guarantees the result of every operation is watertight and manifold.  That
matters here: the files this repo produces are handed straight to a slicer by
someone who has no way to repair them.

Coordinate convention used by every generator in this package:

    +X  width   (left to right across the front of the part)
    +Y  depth   (front to back)
    +Z  height  (up; Z=0 is the print bed)
"""

from __future__ import annotations

from typing import Iterable, Sequence

import manifold3d as m3

Solid = m3.Manifold
Point2 = tuple[float, float]

EPS = 1e-6


def box(size: Sequence[float], at: Sequence[float] = (0.0, 0.0, 0.0)) -> Solid:
    """Axis-aligned box whose minimum corner sits at `at`."""
    sx, sy, sz = size
    if min(sx, sy, sz) <= 0:
        return empty()
    return Solid.cube([sx, sy, sz]).translate(list(at))


def prism_y(profile: Iterable[Point2], y0: float, y1: float) -> Solid:
    """Extrude a closed (x, z) profile along +Y from y0 to y1.

    Used for anything that runs front-to-back: rails, ledges, chamfered
    shelf noses.
    """
    length = y1 - y0
    if length <= EPS:
        return empty()
    cross = m3.CrossSection([_ensure_ccw(profile)])
    return cross.extrude(length).rotate([90, 0, 0]).translate([0, y1, 0])


def prism_x(profile: Iterable[Point2], x0: float, x1: float) -> Solid:
    """Extrude a closed (y, z) profile along +X from x0 to x1.

    Used for anything that runs left-to-right: front stops, back braces,
    stacking ribs.
    """
    length = x1 - x0
    if length <= EPS:
        return empty()
    # Extruding then rotating about Y maps the profile's first coordinate to Z
    # and its second to Y, so swap the pair.  Reversing the point order at the
    # same time keeps the polygon counter-clockwise: swapping alone mirrors it,
    # and a clockwise loop reads as a hole.
    swapped = [(b, a) for (a, b) in reversed(list(profile))]
    cross = m3.CrossSection([_ensure_ccw(swapped)])
    return cross.extrude(length).rotate([0, -90, 0]).translate([x1, 0, 0])


def prism_z(profile: Iterable[Point2], z0: float, z1: float) -> Solid:
    """Extrude a closed (x, y) profile along +Z from z0 to z1."""
    height = z1 - z0
    if height <= EPS:
        return empty()
    cross = m3.CrossSection([_ensure_ccw(profile)])
    return cross.extrude(height).translate([0, 0, z0])


def cylinder_y(radius: float, y0: float, y1: float, at_xz: Point2 = (0.0, 0.0),
               segments: int = 48) -> Solid:
    """Horizontal cylinder along +Y -- screw holes through a back panel."""
    length = y1 - y0
    if length <= EPS or radius <= EPS:
        return empty()
    solid = Solid.cylinder(length, radius, radius, circular_segments=segments)
    # Rotating -90 about X sends the extrusion axis from +Z to +Y.
    return solid.rotate([-90, 0, 0]).translate([at_xz[0], y0, at_xz[1]])


def union(*solids: Solid | Iterable[Solid]) -> Solid:
    """Union of everything passed, flattening one level of iterables."""
    parts = list(_flatten(solids))
    if not parts:
        return empty()
    return Solid.batch_boolean(parts, m3.OpType.Add)


def difference(base: Solid, *cutters: Solid | Iterable[Solid]) -> Solid:
    """Subtract every cutter from `base`."""
    parts = list(_flatten(cutters))
    if not parts:
        return base
    return base - union(parts)


def intersection(*solids: Solid | Iterable[Solid]) -> Solid:
    parts = list(_flatten(solids))
    if not parts:
        return empty()
    return Solid.batch_boolean(parts, m3.OpType.Intersect)


def empty() -> Solid:
    return Solid()


def bounds(solid: Solid) -> tuple[float, float, float, float, float, float]:
    """(x0, y0, z0, x1, y1, z1)."""
    return tuple(solid.bounding_box())


def size_of(solid: Solid) -> tuple[float, float, float]:
    x0, y0, z0, x1, y1, z1 = bounds(solid)
    return (x1 - x0, y1 - y0, z1 - z0)


def signed_area(profile: Iterable[Point2]) -> float:
    """Twice the signed area of a closed polygon; positive means counter-clockwise."""
    points = list(profile)
    total = 0.0
    for index, (x0, y0) in enumerate(points):
        x1, y1 = points[(index + 1) % len(points)]
        total += x0 * y1 - x1 * y0
    return total / 2.0


def _ensure_ccw(profile: Iterable[Point2]) -> list[Point2]:
    """Return the polygon wound counter-clockwise.

    A clockwise loop is a *hole* to manifold's cross-section code, so extruding
    one yields an empty solid rather than an error.  That failure is silent and
    looks exactly like a part that was never added, so every extrusion helper
    normalises the winding here instead of trusting its caller.
    """
    points = _dedupe([(float(x), float(y)) for x, y in profile])
    if len(points) < 3:
        raise ValueError(f"a profile needs at least 3 points, got {len(points)}")
    area = signed_area(points)
    if abs(area) < EPS:
        raise ValueError("degenerate profile: the outline encloses no area")
    return points if area > 0 else points[::-1]


def _flatten(items) -> Iterable[Solid]:
    for item in items:
        if isinstance(item, Solid):
            if not item.is_empty():
                yield item
        elif item is None:
            continue
        else:
            yield from _flatten(item)


def chamfered_rect(x0: float, x1: float, z0: float, z1: float,
                   chamfer_bottom: float = 0.0,
                   chamfer_top: float = 0.0,
                   chamfer_side: str = "both") -> list[Point2]:
    """A rectangle profile with 45-degree chamfers, as an (x, z) point list.

    45 degrees is not decoration.  A ledge that cantilevers into the bin
    opening is an overhang; taking its underside back at 45 degrees is what
    lets the whole rack print with no support material.

    `chamfer_side` selects which vertical edges get chamfered: "both",
    "left", "right", or "none".
    """
    left = chamfer_side in ("both", "left")
    right = chamfer_side in ("both", "right")
    cb, ct = max(chamfer_bottom, 0.0), max(chamfer_top, 0.0)

    points: list[Point2] = []
    # bottom edge, left to right
    points.append((x0 + (cb if left else 0.0), z0))
    points.append((x1 - (cb if right else 0.0), z0))
    # right edge, bottom to top
    if right and cb > EPS:
        points.append((x1, z0 + cb))
    else:
        points[-1] = (x1, z0)
    points.append((x1, z1 - (ct if right else 0.0)))
    if right and ct > EPS:
        points.append((x1 - ct, z1))
    else:
        points.append((x1, z1))
    # top edge, right to left
    points.append((x0 + (ct if left else 0.0), z1))
    # left edge, top to bottom
    if left and ct > EPS:
        points.append((x0, z1 - ct))
    if left and cb > EPS:
        points.append((x0, z0 + cb))
    elif left:
        points.append((x0, z0))
    else:
        points.append((x0, z0))
    return _dedupe(points)


def _dedupe(points: Sequence[Point2]) -> list[Point2]:
    """Drop repeated points, including the wrap-around from last back to first.

    A chamfer that shrinks to nothing leaves two coincident corners. Extruding
    that gives a zero-area sliver triangle: harmless to look at, but it fails
    every mesh validator and there is no reason to ship one.
    """
    out: list[Point2] = []
    for p in points:
        if not out or abs(p[0] - out[-1][0]) > EPS or abs(p[1] - out[-1][1]) > EPS:
            out.append((float(p[0]), float(p[1])))
    while len(out) > 1 and abs(out[0][0] - out[-1][0]) < EPS and abs(out[0][1] - out[-1][1]) < EPS:
        out.pop()
    return out
