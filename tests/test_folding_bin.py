"""The folding bin is a mechanism, so the tests are about motion.

A watertight mesh proves nothing here. What matters is that no wall touches
anything it should not at any angle it actually turns through, that it stops
where it is meant to, and that the whole thing still comes apart into five
printable pieces afterwards.
"""

import unittest

from _support import build

from storagegen import geom
from storagegen.generators import folding_bin as fb
from storagegen.options import Report


def layout_for(**options):
    generator, opt, _ = build("folding-bin", **options)
    report = Report()
    fb._apply_preset(opt, report)
    return opt, fb.Layout(opt)


def overlap(*solids) -> float:
    return max(0.0, geom.intersection(list(solids)).volume())


def pairs_at(layout, opt, side_angle, end_angle):
    walls = fb.walls_at(layout, opt, side_angle, end_angle)
    return (geom.union([walls["side-neg"], walls["side-pos"]]),
            geom.union([walls["end-neg"], walls["end-pos"]]))


# The bin is only ever in one of two states: the long walls moving with the
# short ones lying flat, or the short ones moving with the long ones up. Any
# other combination is a position the mechanism never reaches.
def travel(step=10):
    for angle in range(0, 91, step):
        yield float(angle), 0.0
    for angle in range(0, 91, step):
        yield 90.0, float(angle)


class Motion(unittest.TestCase):
    def test_nothing_touches_anywhere_in_the_fold(self):
        opt, layout = layout_for()
        base = fb._base(layout, opt)
        for side_angle, end_angle in travel():
            with self.subTest(side=side_angle, end=end_angle):
                side, end = pairs_at(layout, opt, side_angle, end_angle)
                self.assertLess(overlap(geom.union([side, end]), base), 1.0)
                self.assertLess(overlap(side, end), 1.0)

    def test_walls_stop_at_square(self):
        """Past square there is no clearance, and that is the whole point.

        The base is carved by the fold itself, from flat to square and no
        further, so everything a wall would have to pass through to lean out
        any further is still standing.
        """
        opt, layout = layout_for()
        base = fb._base(layout, opt)
        walls = geom.union(list(fb.walls_at(layout, opt, 90.0).values()))
        self.assertLess(overlap(walls, base), 1.0)
        leaning = geom.union(list(fb.walls_at(layout, opt, 96.0).values()))
        self.assertGreater(overlap(leaning, base), 10.0)

    def test_folded_walls_lie_at_two_separate_heights(self):
        """Folded, one pair has to lie clear on top of the other.

        Bounding boxes will not answer this -- the pins stand proud of both
        walls and their boxes overlap even where the walls do not -- so ask
        the heights the walls themselves fold to.
        """
        _, layout = layout_for()
        under = layout.z_end - layout.pin_r + layout.wall_t
        over = layout.z_side - layout.pin_r
        self.assertGreaterEqual(over - under, fb.FOLD_GAP - 1e-6,
                                "the long walls have to clear the short ones")

    def test_folded_bin_is_shorter_than_it_is_erect(self):
        _, _, result = build("folding-bin")
        erect = result.facts["outside_mm"][2]
        folded = result.facts["folded_mm"][2]
        self.assertGreater(erect, 2.0 * folded)


class Pieces(unittest.TestCase):
    def test_every_part_is_one_watertight_piece(self):
        _, _, result = build("folding-bin")
        self.assertEqual(len(result.parts.parts), 3)
        for part in result.parts.parts:
            with self.subTest(part=part.name):
                self.assertEqual(len(part.solid.decompose()), 1)
                self.assertTrue(part.is_manifold())
                self.assertGreater(part.volume_mm3, 0.0)

    def test_pins_are_welded_to_their_wall(self):
        """A pin that only shares a face with the wall prints beside it."""
        opt, layout = layout_for()
        for kind in ("side", "end"):
            with self.subTest(kind=kind):
                wall = fb._wall_flat(layout, opt, kind)
                self.assertEqual(len(wall.decompose()), 1)

    def test_shapes_across_the_option_space_stay_one_piece(self):
        cases = [
            {"width": 100.0, "depth": 80.0, "height": 40.0},
            {"width": 400.0, "depth": 300.0, "height": 120.0},
            {"wall": 1.6}, {"wall": 6.0},
            {"pivot_across": 4.0, "pivot_facets": 6},
            {"pivot_across": 10.0},
            {"pattern": "honeycomb"}, {"pattern": "round"},
            {"preset": "greenmade-rack"},
        ]
        for case in cases:
            with self.subTest(**case):
                _, _, result = build("folding-bin", **case)
                for part in result.parts.parts:
                    self.assertEqual(len(part.solid.decompose()), 1, part.name)


class Printability(unittest.TestCase):
    def test_default_pin_prints_without_support(self):
        _, _, result = build("folding-bin")
        self.assertFalse(result.facts["supports_required"])
        self.assertLessEqual(result.facts["pivot_facets"],
                             fb.MAX_PRINTABLE_FACETS)

    def test_a_ten_sided_pin_is_called_out(self):
        _, _, result = build("folding-bin", pivot_facets=10)
        self.assertTrue(any("support" in w for w in result.report.warnings))

    def test_every_part_lies_flat_on_the_bed(self):
        """Nothing is taller than a wall is thick, plus its flange."""
        opt, layout = layout_for()
        for kind in ("side", "end"):
            wall = fb._wall_flat(layout, opt, kind)
            box = wall.bounding_box()
            self.assertLessEqual(box[5] - box[2],
                                 2.0 * layout.pin_r + layout.flange + 0.01)

    def test_the_floor_is_not_perforated_by_the_fold(self):
        """A long wall tipped below flat would carve a trench in the floor."""
        opt, layout = layout_for()
        base = fb._base(layout, opt)
        slab = geom.box([layout.outer_x, layout.outer_y, layout.floor_t - 0.4],
                        at=[-layout.outer_x / 2.0, -layout.outer_y / 2.0, 0.2])
        self.assertLess(overlap(geom.difference(slab, [base])), 1.0)


class RackPreset(unittest.TestCase):
    def test_preset_matches_the_bin_it_replaces(self):
        from storagegen.presets import get_bin

        spec = get_bin("greenmade-mini")
        opt, layout = layout_for(preset="greenmade-rack")
        self.assertAlmostEqual(layout.body_y, spec.body_width, places=1)
        self.assertAlmostEqual(layout.flange_y, spec.width, places=1)
        self.assertAlmostEqual(layout.flange_x, spec.length, places=1)
        self.assertTrue(layout.hangs)

    def test_preset_says_what_it_gave_up(self):
        _, _, result = build("folding-bin", preset="greenmade-rack")
        self.assertTrue(any("greenmade-rack" in n for n in result.report.notes))

    def test_a_flange_that_cannot_reach_a_rail_is_flagged(self):
        _, _, result = build("folding-bin", rim_flange=0.5)
        self.assertTrue(any("rail" in w for w in result.report.warnings))


if __name__ == "__main__":
    unittest.main()
