import math
import unittest

from _support import SRC  # noqa: F401

import manifold3d as m3

from storagegen import geom, patterns

# A wall band roughly the shape the rack actually offers a pattern.
BAND = (9.0, 12.0, 118.0, 65.0)
PLATE = (9.0, 9.0, 103.0, 118.0)


def sized(style):
    return patterns.default_cell(style), patterns.default_rib(style)


def ccw(profile):
    return profile if geom.signed_area(profile) > 0 else profile[::-1]


class Api(unittest.TestCase):
    def test_an_unknown_pattern_lists_the_real_ones(self):
        with self.assertRaises(ValueError) as caught:
            patterns.tile("tartan", BAND, 12, 4)
        self.assertIn("honeycomb", str(caught.exception))

    def test_every_pattern_has_a_default_size_and_a_description(self):
        for style in patterns.PATTERNS:
            with self.subTest(pattern=style):
                cell, rib = sized(style)
                self.assertGreaterEqual(cell, patterns.MIN_HOLE)
                self.assertGreater(rib, 0)
                self.assertTrue(patterns.describe(style, cell, rib))

    def test_a_region_too_small_to_pattern_comes_back_empty(self):
        for style in patterns.PATTERNS:
            with self.subTest(pattern=style):
                self.assertEqual(patterns.tile(style, (0, 0, 3, 3), 12, 4), [])

    def test_a_cell_smaller_than_a_hole_is_declined(self):
        self.assertEqual(patterns.tile("grid", BAND, 1.0, 4.0), [])


class Placement(unittest.TestCase):
    def test_every_pattern_fills_a_wall_band_and_a_plate(self):
        for style in patterns.PATTERNS:
            cell, rib = sized(style)
            for name, rect in (("band", BAND), ("plate", PLATE)):
                with self.subTest(pattern=style, region=name):
                    self.assertGreater(len(patterns.tile(style, rect, cell, rib)), 0)

    def test_no_cut_out_escapes_its_region(self):
        for style in patterns.PATTERNS:
            cell, rib = sized(style)
            with self.subTest(pattern=style):
                for profile in patterns.tile(style, BAND, cell, rib):
                    for a, b in profile:
                        self.assertGreaterEqual(a, BAND[0] - 1e-6)
                        self.assertLessEqual(a, BAND[2] + 1e-6)
                        self.assertGreaterEqual(b, BAND[1] - 1e-6)
                        self.assertLessEqual(b, BAND[3] + 1e-6)

    def test_cut_outs_never_run_into_each_other(self):
        """Overlapping cut-outs merge into one ragged hole with no web left."""
        for style in patterns.PATTERNS:
            cell, rib = sized(style)
            with self.subTest(pattern=style):
                profiles = patterns.tile(style, BAND, cell, rib)
                shapes = [m3.CrossSection([list(p)]) for p in profiles]
                separate = sum(shape.area() for shape in shapes)
                merged = m3.CrossSection.batch_boolean(shapes, m3.OpType.Add)
                self.assertAlmostEqual(
                    merged.area(), separate, delta=max(separate * 1e-6, 1e-6)
                )

    def test_the_pattern_is_centred_in_its_region(self):
        for style in patterns.PATTERNS:
            cell, rib = sized(style)
            with self.subTest(pattern=style):
                points = [
                    point
                    for profile in patterns.tile(style, BAND, cell, rib)
                    for point in profile
                ]
                for index, (low, high) in enumerate(
                    ((BAND[0], BAND[2]), (BAND[1], BAND[3]))
                ):
                    before = min(p[index] for p in points) - low
                    after = high - max(p[index] for p in points)
                    self.assertAlmostEqual(before, after, places=6)


class SupportFree(unittest.TestCase):
    """The printability guarantee, checked rather than asserted in a comment.

    A hole in a vertical wall is printed by bridging over it. Walk the outline:
    for a counter-clockwise loop the material is to the left of each edge, so
    an edge running right-to-left has material above it and is a roof. Every
    roof must either be steeper than 45 degrees or short enough to bridge.
    """

    def roofs(self, profile):
        loop = ccw(profile)
        for index, (a0, b0) in enumerate(loop):
            a1, b1 = loop[(index + 1) % len(loop)]
            if a1 - a0 < -1e-9:                     # runs right to left
                yield (a0, b0), (a1, b1)

    def test_no_roof_is_shallower_than_45_degrees_or_too_long_to_bridge(self):
        for style in patterns.PATTERNS:
            cell, rib = sized(style)
            with self.subTest(pattern=style):
                for profile in patterns.tile(style, BAND, cell, rib):
                    for (a0, b0), (a1, b1) in self.roofs(profile):
                        run, rise = abs(a1 - a0), abs(b1 - b0)
                        if rise >= run - 1e-9:
                            continue                # 45 degrees or steeper
                        self.assertLessEqual(
                            run, patterns.MAX_BRIDGE + 1e-6,
                            f"{style}: a {run:.1f} mm roof at "
                            f"{math.degrees(math.atan2(rise, run)):.0f} degrees",
                        )

    def test_a_honeycomb_shrinks_rather_than_bridge_too_far(self):
        profiles = patterns.tile("honeycomb", (0, 0, 300, 200), 90.0, 6.0)
        self.assertTrue(profiles)
        for profile in profiles:
            for (a0, _), (a1, _) in self.roofs(profile):
                self.assertLessEqual(abs(a1 - a0), patterns.MAX_BRIDGE + 1e-6)

    def test_hexagons_sit_flat_top_not_point_top(self):
        """Point-top hexagons look the same in a render and cannot be printed."""
        profile = patterns.tile("honeycomb", BAND, 14.0, 5.0)[0]
        top = max(b for _, b in profile)
        on_top = [a for a, b in profile if abs(b - top) < 1e-6]
        self.assertEqual(len(on_top), 2, "a flat top has two corners, not one")

    def test_triangles_point_up(self):
        profile = patterns.tile("triangle", BAND, 20.0, 5.0)[0]
        top = max(b for _, b in profile)
        self.assertEqual(len([1 for _, b in profile if abs(b - top) < 1e-6]), 1)


if __name__ == "__main__":
    unittest.main()
