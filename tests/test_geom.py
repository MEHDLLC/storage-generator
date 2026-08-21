import unittest

from _support import SRC  # noqa: F401

from storagegen import geom


class ProfileWinding(unittest.TestCase):
    """A clockwise profile used to extrude to nothing, silently."""

    SQUARE_CCW = [(0, 0), (10, 0), (10, 4), (0, 4)]
    SQUARE_CW = [(0, 0), (0, 4), (10, 4), (10, 0)]

    def test_signed_area_sign(self):
        self.assertGreater(geom.signed_area(self.SQUARE_CCW), 0)
        self.assertLess(geom.signed_area(self.SQUARE_CW), 0)

    def test_both_windings_extrude_identically(self):
        ccw = geom.prism_y(self.SQUARE_CCW, 0, 5)
        cw = geom.prism_y(self.SQUARE_CW, 0, 5)
        self.assertAlmostEqual(ccw.volume(), 200.0, places=3)
        self.assertAlmostEqual(cw.volume(), 200.0, places=3)

    def test_degenerate_profile_is_an_error_not_an_empty_solid(self):
        for bad in ([(0, 0), (1, 1), (2, 2)], [(0, 0), (1, 0)]):
            with self.assertRaises(ValueError):
                geom.prism_y(bad, 0, 5)


class Axes(unittest.TestCase):
    """Each prism helper takes its profile in the plane it says it does."""

    PROFILE = [(0, 0), (10, 0), (10, 4), (0, 4)]   # first axis 0..10, second 0..4

    def test_prism_y_maps_profile_to_xz(self):
        solid = geom.prism_y(self.PROFILE, 2, 7)
        self.assertEqual(
            [round(v, 6) for v in geom.bounds(solid)], [0, 2, 0, 10, 7, 4]
        )

    def test_prism_x_maps_profile_to_yz(self):
        solid = geom.prism_x(self.PROFILE, 2, 7)
        self.assertEqual(
            [round(v, 6) for v in geom.bounds(solid)], [2, 0, 0, 7, 10, 4]
        )

    def test_prism_z_maps_profile_to_xy(self):
        solid = geom.prism_z(self.PROFILE, 2, 7)
        self.assertEqual(
            [round(v, 6) for v in geom.bounds(solid)], [0, 0, 2, 10, 4, 7]
        )

    def test_cylinder_y_runs_along_y(self):
        solid = geom.cylinder_y(5, 0, 20, at_xz=(50, 30))
        self.assertEqual(
            [round(v, 3) for v in geom.bounds(solid)], [45, 0, 25, 55, 20, 35]
        )


class Chamfers(unittest.TestCase):
    def test_chamfer_removes_a_triangle(self):
        plain = geom.prism_y(geom.chamfered_rect(0, 6, 0, 4), 0, 10)
        cut = geom.prism_y(
            geom.chamfered_rect(0, 6, 0, 4, chamfer_bottom=3,
                                chamfer_side="right"),
            0, 10,
        )
        self.assertAlmostEqual(plain.volume(), 6 * 4 * 10, places=3)
        self.assertAlmostEqual(cut.volume(), (24 - 4.5) * 10, places=3)


class Booleans(unittest.TestCase):
    def test_union_ignores_empties_and_nesting(self):
        result = geom.union([geom.box([2, 2, 2]), None], geom.empty())
        self.assertAlmostEqual(result.volume(), 8.0, places=6)

    def test_difference_with_no_cutters_is_identity(self):
        box = geom.box([2, 2, 2])
        self.assertAlmostEqual(geom.difference(box).volume(), 8.0, places=6)


if __name__ == "__main__":
    unittest.main()
