"""Measured (and estimated) shapes of the bins these racks are built around.

Honesty about provenance matters more here than anywhere else in the repo.
A rack that misses the lip by a millimetre is scrap, so every field records
whether it came from a published specification or from an estimate that the
printed fit gauge is meant to replace.  `confidence` is carried all the way
into the manifest and the listing.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from .units import inch


@dataclass(frozen=True)
class BinSpec:
    """The handful of bin measurements a hanging rack actually depends on.

    Dimensions are the *outside* of the bin at its widest point, which for a
    tapered tote is the rim.  `length` is the long axis; the rack's rails run
    along it, so the bin is carried on its two long sides.
    """

    key: str
    label: str
    short_label: str
    length: float                 # mm, long axis (front to back in the rack)
    width: float                  # mm, short axis (rail to rail)
    height: float                 # mm, rim top to base
    lip_overhang: float           # mm, how far the rim flange stands proud of the wall
    lip_thickness: float          # mm, vertical thickness of that flange
    taper_deg: float              # degrees per side, rim to base
    source: str = ""
    measured_fields: tuple[str, ...] = ()
    estimated_fields: tuple[str, ...] = ()
    notes: str = ""

    @property
    def body_width(self) -> float:
        """Outside width just below the rim -- the part that passes between rails."""
        return self.width - 2.0 * self.lip_overhang

    @property
    def hang_depth(self) -> float:
        """How far the bin hangs below the surface its rim rests on."""
        return self.height - self.lip_thickness

    @property
    def base_width(self) -> float:
        """Outside width at the bottom, after taper."""
        return self.body_width - 2.0 * self.hang_depth * math.tan(
            math.radians(self.taper_deg)
        )

    @property
    def fully_measured(self) -> bool:
        return not self.estimated_fields

    def solid(self):
        """A simplified solid of the bin, for clearance checks and previews.

        Tapered body, flange around the rim, square corners. Real totes have
        radiused corners and a rolled rim, so this model is slightly *larger*
        than the bin it stands for -- which is the safe direction for a
        clearance test.
        """
        from . import geom

        body_l, body_w = self.length - 2.0 * self.lip_overhang, self.body_width
        shrink = self.hang_depth * math.tan(math.radians(self.taper_deg))
        base_l, base_w = body_l - 2.0 * shrink, body_w - 2.0 * shrink
        if min(base_l, base_w) <= 0:
            raise ValueError("taper_deg is steep enough to close the bin's base")

        slice_h = 0.01
        base = geom.box([base_w, base_l, slice_h],
                        at=[-base_w / 2.0, -base_l / 2.0, 0.0])
        shoulder = geom.box(
            [body_w, body_l, slice_h],
            at=[-body_w / 2.0, -body_l / 2.0, self.hang_depth - slice_h],
        )
        body = geom.Solid.batch_hull([base, shoulder])
        rim = geom.box(
            [self.width, self.length, self.lip_thickness],
            at=[-self.width / 2.0, -self.length / 2.0, self.hang_depth],
        )
        return geom.union([body, rim])

    def to_dict(self) -> dict:
        data = asdict(self)
        data["body_width"] = round(self.body_width, 3)
        data["hang_depth"] = round(self.hang_depth, 3)
        return data

    def replace(self, **changes) -> "BinSpec":
        from dataclasses import replace as _replace

        if not changes:
            return self
        touched = tuple(k for k in changes if k in _DIMENSION_FIELDS)
        spec = _replace(self, **changes)
        if touched:
            spec = _replace(
                spec,
                key=spec.key if spec.key == "custom" else spec.key + "-modified",
                measured_fields=tuple(
                    f for f in spec.measured_fields if f not in touched
                ),
                estimated_fields=tuple(
                    dict.fromkeys(
                        [f for f in spec.estimated_fields if f not in touched]
                        + ["user-supplied: " + f for f in touched]
                    )
                ),
            )
        return spec


_DIMENSION_FIELDS = {
    "length",
    "width",
    "height",
    "lip_overhang",
    "lip_thickness",
    "taper_deg",
}


GREENMADE_MINI = BinSpec(
    key="greenmade-mini",
    label="GreenMade Mini Bin (Compact Stackable Storage Set)",
    short_label="GreenMade Mini Bin",
    # Retail listings give 4.8 x 3.3 x 2.4 in for this bin.
    length=inch(4.8),
    width=inch(3.3),
    height=inch(2.4),
    # The rim flange and the draft angle are not published anywhere.  These are
    # typical values for a small injection-moulded stackable tote; the printed
    # fit gauge exists to replace them with your own two measurements.
    lip_overhang=2.5,
    lip_thickness=3.0,
    taper_deg=3.0,
    source=(
        "Outside dimensions from retail listings for the GreenMade Mini Bin "
        "(mfr# 844916 / Costco 'Mini Bin Compact Stackable Storage Set'): "
        "4.8 in long x 3.3 in wide x 2.4 in tall."
    ),
    measured_fields=("length", "width", "height"),
    estimated_fields=("lip_overhang", "lip_thickness", "taper_deg"),
    notes=(
        "The rails are forgiving by design: the bin's walls taper inward, so a "
        "rail span that is slightly wide simply lets the bin settle a little "
        "lower until the taper wedges, and a span that is slightly narrow lets "
        "it ride on the rim. Print the fit gauge first if you want it exact."
    ),
)


GENERIC_TOTE = BinSpec(
    key="generic-tote",
    label="Generic rimmed tote (placeholder to be overridden)",
    short_label="Rimmed tote",
    length=150.0,
    width=100.0,
    height=75.0,
    lip_overhang=3.0,
    lip_thickness=3.0,
    taper_deg=3.0,
    source="Not a real product. A neutral starting point for --bin custom.",
    measured_fields=(),
    estimated_fields=("length", "width", "height", "lip_overhang",
                      "lip_thickness", "taper_deg"),
    notes="Supply every dimension yourself when using this preset.",
)


BIN_PRESETS: dict[str, BinSpec] = {
    spec.key: spec for spec in (GREENMADE_MINI, GENERIC_TOTE)
}

DEFAULT_BIN = GREENMADE_MINI.key


def get_bin(key: str) -> BinSpec:
    try:
        return BIN_PRESETS[key]
    except KeyError:
        raise KeyError(
            f"unknown bin preset {key!r}; known presets: "
            + ", ".join(sorted(BIN_PRESETS))
        ) from None


def preset_keys() -> tuple[str, ...]:
    return tuple(BIN_PRESETS)
