"""Render one rack per pattern into a single comparison sheet.

Used for the image in the README. Run it with `make patterns`.

The view is dead-on from the side on purpose. Tilt the camera even a few
degrees and the far side panel, ninety-odd millimetres away, creeps up behind
the near panel's cut-outs and makes every hole look squashed.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from storagegen import generator as registry     # noqa: E402
from storagegen import patterns, preview         # noqa: E402
from storagegen.generators import bin_shelf      # noqa: E402


def main(destination: Path = ROOT / "docs" / "images" / "patterns.png",
         columns: int = 3, rows_of_bins: int = 2, size: int = 560) -> Path:
    generator = registry.get("bin-shelf")
    tiles = []
    for style in patterns.PATTERNS:
        options = generator.options.resolve(
            {"pattern": style, "rows": rows_of_bins}
        )
        result = generator.build(options)
        cell, rib = bin_shelf._pattern_size(options)
        print(f"{style:10s} {patterns.describe(style, cell, rib)}")
        tiles.append(
            preview.scene_pixels(result.parts.parts, size=size,
                                 azimuth=90.0, elevation=0.0)
        )

    grid = [tiles[i:i + columns] for i in range(0, len(tiles), columns)]
    preview.write_sheet(destination, grid)
    print(f"wrote {destination}")
    return destination


if __name__ == "__main__":
    main()
