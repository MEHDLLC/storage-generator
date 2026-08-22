"""Render the fold, one frame per stage, into a single sheet.

Used for the image in the README and in docs/folding-bin.md. Run it with
`make fold`.

The order the frames are in is the order the bin is actually erected, and it
matters: the long walls come up first because folded they are the pair lying on
top, and the short ones close the corners after. Rendering it any other way
would show a state the mechanism never passes through.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from storagegen import preview                      # noqa: E402
from storagegen.generators import folding_bin as fb  # noqa: E402
from storagegen.mesh_io import Part                  # noqa: E402

# (label, side wall angle, end wall angle)
STAGES = (
    ("folded", 0.0, 0.0),
    ("long walls up", 45.0, 0.0),
    ("long walls square", 90.0, 0.0),
    ("short walls up", 90.0, 45.0),
    ("erect", 90.0, 90.0),
)
VIEW = (34.0, 24.0)


def main(out: Path = ROOT / "docs" / "images" / "folding-bin-fold.png") -> Path:
    generator = fb.FoldingBinGenerator()
    opt = dict(generator.options.defaults())
    layout = fb.Layout(opt)
    base = Part("base", fb._base(layout, opt))

    frames = []
    for label, side, end in STAGES:
        walls = fb.walls_at(layout, opt, side, end)
        frames.append(preview.scene_pixels(
            [base], [Part(k, v) for k, v in walls.items()],
            size=440, azimuth=VIEW[0], elevation=VIEW[1]))
        print(f"  {label:<20} side {side:>5.0f} deg   end {end:>5.0f} deg")

    out.parent.mkdir(parents=True, exist_ok=True)
    preview.write_sheet(out, [frames])
    print(f"wrote {out}")
    return out


if __name__ == "__main__":
    main()
