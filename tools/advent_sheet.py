"""Render the advent calendar's lids and parts into a sheet for the docs.

Run it with `make advent`. Two rows of lids, one of each motif and a couple
of Lego ones, then the box, a key and a panel. The lids are lit from a low
angle on purpose: straight down, a raised numeral is the same colour as the
plate it stands on and disappears.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from storagegen import preview                          # noqa: E402
from storagegen.generators import advent_calendar as ac  # noqa: E402
from storagegen.mesh_io import Part                      # noqa: E402

LIDS = (
    ("tree", 25, {}), ("circle", 7, {}), ("star", 12, {}), ("heart", 14, {}),
    ("snowflake", 3, {}), ("square", 18, {"number": "recessed"}),
    ("none", 9, {"lego": True}), ("circle", 24, {"lego": True}),
)


def main(out: Path = ROOT / "docs" / "images" / "advent-calendar-parts.png") -> Path:
    base = dict(ac.AdventCalendarGenerator().options.defaults())

    def lid(frame, day, **extra):
        opt = dict(base, frame=frame, **extra)
        return Part(f"lid-{day}", ac._lid(ac.Layout(opt), day))

    tiles = [preview.scene_pixels([lid(f, n, **kw)], size=300, azimuth=15,
                                  elevation=58) for f, n, kw in LIDS]
    lay = ac.Layout(base)
    parts = [
        (Part("box", ac._box(lay)), 25, 55),
        (Part("box", ac._box(lay)), 200, 30),
        (Part("key", ac._key(lay)), 30, 35),
        (Part("skin", ac._skin(lay, "w", "mm")), 30, 40),
    ]
    tiles += [preview.scene_pixels([p], size=300, azimuth=az, elevation=el)
              for p, az, el in parts]
    out.parent.mkdir(parents=True, exist_ok=True)
    preview.write_sheet(out, [tiles[:4], tiles[4:8], tiles[8:]])
    print(f"wrote {out}")
    return out


if __name__ == "__main__":
    main()
