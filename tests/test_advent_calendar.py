"""The advent calendar is a kit, so the tests are about the kit fitting.

Every mating pair is placed exactly as it will be used and checked for zero
overlap; then it is pushed the wrong way to prove the feature that is meant
to catch it is really there. After that, the counts: a tree of 25 has a
known number of joints and outside faces, and every one of them needs a part.
"""

import math
import unittest

from _support import build

from storagegen import geom
from storagegen.generators import advent_calendar as ac


def layout_for(**options):
    _, opt, _ = build("advent-calendar", days=1, **options)
    return opt, ac.Layout(opt)


def overlap(a, b) -> float:
    return max(0.0, geom.intersection([a, b]).volume())


class LidFit(unittest.TestCase):
    def test_lid_seats_between_lip_and_ledge(self):
        for shape in ("box", "hexagon", "triangle", "cylinder"):
            with self.subTest(shape=shape):
                opt, lay = layout_for(shape=shape, width=56.0)
                box = ac._box(lay)
                lid = ac._lid(lay, 25).translate(
                    [0.0, 0.0, lay.seat_z + ac.LID_PLAY / 2.0])
                self.assertLess(overlap(lid, box), 0.5, "lid fouls the box")
                self.assertGreater(overlap(lid.translate([0, 0, 1.0]), box), 1.0,
                                   "nothing above the lid to hold it down")
                self.assertGreater(overlap(lid.translate([0, 0, -1.0]), box), 1.0,
                                   "nothing under the lid to land on")

    def test_lip_is_only_in_the_middle_of_each_side(self):
        """The plate gets past the lip because the walls bow; corners cannot."""
        opt, lay = layout_for()
        box = ac._box(lay)
        z = lay.h - ac.LIP_H / 2.0
        # A probe that lies exactly in the band the lip occupies, just
        # inside the cavity wall, so it touches the lip and nothing else.
        wall_at = lay.foot.size[0] / 2.0 - lay.wall
        band = (wall_at - ac.LIP - 0.05, wall_at - 0.05)
        at_corner = geom.box([band[1] - band[0], 1.0, 0.5],
                             at=[band[0], band[1] - 1.0, z])
        at_middle = geom.box([1.0, band[1] - band[0], 0.5],
                             at=[-0.5, band[0], z])
        self.assertLess(overlap(at_corner, box), 0.01)
        self.assertGreater(overlap(at_middle, box), 0.1)


class Joints(unittest.TestCase):
    def setUp(self):
        self.opt, self.lay = layout_for()
        self.box = ac._box(self.lay)

    def keyed_pair(self):
        lay = self.lay
        px = lay.pitch[0]
        left = self.box.translate([-px / 2.0, 0.0, 0.0])
        right = self.box.translate([px / 2.0, 0.0, 0.0])
        key = ac._key(lay)
        standing = key.translate(
            [-(ac.SEAM / 2.0 + ac.SLOT_DEPTH - ac.KEY_FIT), 0.0, 0.0]
        ).rotate([0.0, -90.0, 0.0])
        b = standing.bounding_box()
        key = standing.translate([0.0, 0.0, lay.slot_z0 + 0.5 - b[2]])
        return left, right, key

    def test_key_sits_in_both_slots_and_cannot_pull_out(self):
        left, right, key = self.keyed_pair()
        self.assertLess(overlap(key, left), 0.01)
        self.assertLess(overlap(key, right), 0.01)
        both = geom.union([left, right])
        self.assertGreater(overlap(key.translate([0.0, 1.0, 0.0]), both), 5.0)
        self.assertGreater(overlap(key.translate([1.0, 0.0, 0.0]), both), 5.0,
                           "the boxes should not be able to part sideways")

    def test_key_prints_on_a_flat_face(self):
        key = ac._key(self.lay)
        b = key.bounding_box()
        slice_ = geom.box([b[3] - b[0], b[4] - b[1], 0.2],
                          at=[b[0], b[1], b[2]])
        footprint = overlap(slice_, key) / 0.2
        self.assertGreater(footprint, 0.8 * (b[3] - b[0]) * 2.0 * (
            ac.SLOT_MOUTH / 2.0 - ac.KEY_FIT))

    def test_skin_sits_on_a_face_and_holds(self):
        lay = self.lay
        skin = ac._skin(lay, "w", "ss")
        upright = skin.translate([0, 0, -lay.skin_t]).rotate([90.0, 0.0, 0.0])
        side = lay.foot.sides[2]
        angle = math.degrees(math.atan2(-side.normal[0], side.normal[1]))
        placed = upright.rotate([0, 0, angle]).translate(
            [side.mid[0] + side.normal[0] * ac.SEAM / 2.0,
             side.mid[1] + side.normal[1] * ac.SEAM / 2.0, 0.0])
        self.assertLess(overlap(placed, self.box), 0.01)
        self.assertGreater(overlap(placed.translate([0.0, 1.0, 0.0]), self.box), 1.0)
        b = placed.bounding_box()
        self.assertAlmostEqual(b[4], side.mid[1] + ac.SEAM / 2.0 + lay.skin_t,
                               places=6, msg="front face should sit skin_t out")

    def test_skin_prints_face_down(self):
        skin = ac._skin(self.lay, "w", "mm")
        b = skin.bounding_box()
        self.assertAlmostEqual(b[2], 0.0, places=6)
        self.assertGreater(b[5], self.lay.skin_t + 1.0, "tab should point up")


class Counts(unittest.TestCase):
    def test_a_tree_of_25_has_36_joints_and_28_faces(self):
        _, _, result = build("advent-calendar")
        self.assertEqual(result.facts["rows"], [1, 3, 5, 7, 9])
        self.assertEqual(result.facts["keys"], 36)
        self.assertEqual(result.facts["panels_total"], 28)
        names = [p.name for p in result.parts.parts]
        self.assertEqual(sum(1 for n in names if n.startswith("lid-")), 25)
        self.assertEqual(sum(p.copies for p in result.parts.parts
                             if p.name.startswith("skin-")), 28)

    def test_a_grid_of_24_is_4_by_6(self):
        _, _, result = build("advent-calendar", days=24, arrangement="grid")
        self.assertEqual(result.facts["rows"], [6, 6, 6, 6])
        self.assertEqual(result.facts["keys"], 3 * 6 + 4 * 5)
        self.assertEqual(result.facts["panels_total"], 2 * 6 + 2 * 4)

    def test_every_face_of_a_row_is_covered(self):
        _, _, result = build("advent-calendar", days=4, arrangement="row")
        self.assertEqual(result.facts["keys"], 3)
        self.assertEqual(result.facts["panels_total"], 4 + 4 + 2)
        self.assertEqual(result.facts["panels"], {"w-ms": 1, "w-sm": 1, "w-ss": 6,
                                                  "l-mm": 2} | result.facts["panels"])

    def test_reversed_puts_the_last_day_at_the_top(self):
        _, _, result = build("advent-calendar", numbering="reversed")
        self.assertEqual(result.facts["numbers"][0], 25)

    def test_scattered_is_a_permutation_and_repeatable(self):
        _, _, a = build("advent-calendar", numbering="scattered")
        _, _, b = build("advent-calendar", numbering="scattered")
        self.assertEqual(sorted(a.facts["numbers"]), list(range(1, 26)))
        self.assertEqual(a.facts["numbers"], b.facts["numbers"])
        self.assertNotEqual(a.facts["numbers"], list(range(1, 26)))


class Pieces(unittest.TestCase):
    def test_every_part_is_one_watertight_piece(self):
        cases = [
            {},
            {"shape": "hexagon", "frame": "star"},
            {"shape": "triangle", "width": 60.0, "frame": "heart"},
            {"shape": "cylinder", "width": 52.0, "frame": "snowflake",
             "skin": "honeycomb"},
            {"lego": True, "frame": "circle"},
            {"lego": True, "frame": "none", "number": "recessed"},
            {"frame": "square", "number": "recessed", "skin": "plain"},
        ]
        for case in cases:
            with self.subTest(**case):
                _, _, result = build("advent-calendar", days=3,
                                     arrangement="row", **case)
                for part in result.parts.parts:
                    self.assertEqual(len(part.solid.decompose()), 1, part.name)
                    self.assertTrue(part.is_manifold(), part.name)

    def test_every_digit_draws(self):
        for n in range(0, 32):
            with self.subTest(n=n):
                polys = ac.number_polygons(str(n), 16.0)
                self.assertTrue(polys)
                self.assertGreater(geom.extrude(polys, 0, 1).volume(), 20.0)

    def test_every_motif_is_wound_to_read_as_solid(self):
        for name, motif in ac.MOTIFS.items():
            if motif.outline:
                with self.subTest(motif=name):
                    self.assertGreater(geom.signed_area(motif.outline), 0.0)
                    polys = ac.motif_polygons(name, 30.0, 1.5)
                    self.assertGreater(geom.extrude(polys, 0, 1).volume(), 10.0)

    def test_lego_studs_stay_inside_the_lid(self):
        opt, lay = layout_for(lego=True, frame="none")
        lid = ac._lid(lay, 9)
        outline = lay.lid_outline()
        xs = [x for x, _ in outline]
        b = lid.bounding_box()
        self.assertGreaterEqual(b[0], min(xs) - 1e-6)
        self.assertLessEqual(b[3], max(xs) + 1e-6)
        above = geom.box([100, 100, 5], at=[-50, -50, lay.plate + 0.1])
        studs = geom.intersection([lid, above])
        self.assertGreaterEqual(len(studs.decompose()), 8, "expected a ring of studs")


if __name__ == "__main__":
    unittest.main()
