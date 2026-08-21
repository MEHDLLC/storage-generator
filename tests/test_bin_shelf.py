import unittest

from _support import build

from storagegen import geom
from storagegen.generators import bin_shelf
from storagegen.options import Report


def layout_for(**options):
    generator, opt, _ = build("bin-shelf", **options)
    spec = bin_shelf.resolve_bin(opt, Report())
    bin_shelf._validate(spec, opt, Report())
    return spec, opt, bin_shelf.Layout(spec, opt)


class Integrity(unittest.TestCase):
    def test_default_rack_is_one_watertight_piece(self):
        _, _, result = build("bin-shelf")
        part = result.parts.parts[0]
        self.assertEqual(len(part.solid.decompose()), 1)
        self.assertTrue(part.is_manifold())
        self.assertGreater(part.volume_mm3, 0)

    def test_every_option_combination_builds_in_one_piece(self):
        """The failure this guards against is a rack that prints as two halves.

        Several options remove cross members; losing the last one leaves the
        side assemblies unconnected, and nothing about the STL says so.
        """
        axes = {
            "back": ("windowed", "panel"),
            "sides": ("windowed", "solid"),
            "front_stop": ("none", "tabs", "lip", "label"),
            "base": ("open", "plate"),
            "top": ("none", "plate"),
            "rail_style": ("full", "pads"),
            "stackable": (True, False),
        }
        baseline = {name: values[0] for name, values in axes.items()}
        cases = [dict(baseline)]
        for name, values in axes.items():         # vary one axis at a time
            for value in values[1:]:
                cases.append({**baseline, name: value})
        cases.append({name: values[-1] for name, values in axes.items()})
        cases.append({"back": "open", "base": "plate", "top": "plate"})

        for case in cases:
            with self.subTest(**case):
                _, _, result = build("bin-shelf", rows=2, **case)
                part = result.parts.parts[0]
                self.assertEqual(len(part.solid.decompose()), 1)
                self.assertTrue(part.is_manifold())

    def test_multi_column_and_multi_row_stay_one_piece(self):
        for columns, rows in ((2, 1), (3, 2), (1, 6)):
            with self.subTest(columns=columns, rows=rows):
                _, _, result = build("bin-shelf", columns=columns, rows=rows)
                self.assertEqual(
                    len(result.parts.parts[0].solid.decompose()), 1
                )


class BinFit(unittest.TestCase):
    """The point of the whole thing: does a real bin go in, and is it held?"""

    def test_rack_clears_the_bins_it_holds(self):
        spec, opt, layout = layout_for(rows=3, columns=2)
        _, _, result = build("bin-shelf", rows=3, columns=2)
        rack = result.parts.parts[0].solid
        bins = geom.union(bin_shelf.bin_solids(spec, layout, opt))
        overlap = geom.intersection([rack, bins]).volume()
        self.assertLess(overlap, 1.0, f"rack fouls the bins by {overlap:.1f} mm3")

    def test_the_bins_are_actually_resting_on_something(self):
        """Clearance alone is not support: a bin could be floating in a hole.

        Drop each bin a fraction of a millimetre. If it now collides with the
        rack, the rack was holding it up.
        """
        spec, opt, layout = layout_for(rows=2)
        _, _, result = build("bin-shelf", rows=2)
        rack = result.parts.parts[0].solid
        for index, one_bin in enumerate(bin_shelf.bin_solids(spec, layout, opt)):
            with self.subTest(level=index):
                dropped = one_bin.translate([0, 0, -0.3])
                self.assertGreater(
                    geom.intersection([rack, dropped]).volume(), 0.0,
                    "nothing under this bin's rim",
                )

    def test_front_stops_stand_in_the_bin_s_way(self):
        spec, opt, layout = layout_for(rows=1, front_stop="tabs")
        _, _, result = build("bin-shelf", rows=1, front_stop="tabs")
        rack = result.parts.parts[0].solid
        one_bin = bin_shelf.bin_solids(spec, layout, opt)[0]
        forward = one_bin.translate([0, -layout.front_t - 1.0, 0])
        self.assertGreater(
            geom.intersection([rack, forward]).volume(), 0.0,
            "a bin slid forward meets nothing, so nothing retains it",
        )

    def test_an_open_front_lets_the_bin_straight_out(self):
        spec, opt, layout = layout_for(rows=1, front_stop="none")
        _, _, result = build("bin-shelf", rows=1, front_stop="none")
        rack = result.parts.parts[0].solid
        one_bin = bin_shelf.bin_solids(spec, layout, opt)[0]
        forward = one_bin.translate([0, -60.0, 0])
        # The rim slides along the rail tops, so surfaces touch; only a real
        # volume of overlap means something is in the way.
        self.assertLess(geom.intersection([rack, forward]).volume(), 1e-3)

    def test_rail_span_follows_the_bin_and_the_clearance(self):
        spec, _, layout = layout_for(side_clearance=0.75)
        self.assertAlmostEqual(layout.span, spec.body_width + 1.5, places=6)

    def test_measured_overrides_move_the_rails(self):
        _, _, wide = layout_for(lip_overhang=1.0)
        _, _, narrow = layout_for(lip_overhang=4.0)
        self.assertAlmostEqual(wide.span - narrow.span, 6.0, places=6)


class Stacking(unittest.TestCase):
    def test_a_stacked_rack_seats_without_interference(self):
        _, _, layout = layout_for(rows=1)
        _, _, result = build("bin-shelf", rows=1)
        rack = result.parts.parts[0].solid
        above = rack.translate([0, 0, layout.body_height])
        clash = geom.intersection([rack, above]).volume()
        self.assertLess(
            clash, 0.5, f"stacking ribs foul their sockets by {clash:.2f} mm3"
        )

    def test_without_stacking_there_is_no_rib(self):
        _, _, plain = build("bin-shelf", rows=1, stackable=False)
        _, _, ribbed = build("bin-shelf", rows=1, stackable=True)
        self.assertLess(
            plain.parts.parts[0].size[2], ribbed.parts.parts[0].size[2]
        )


class Guardrails(unittest.TestCase):
    def test_open_back_with_nothing_bracing_it_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            build("bin-shelf", back="open")
        self.assertIn("two loose halves", str(caught.exception))

    def test_rail_narrower_than_the_rim_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            build("bin-shelf", lip_overhang=8.0, rail_width=4.0)
        self.assertIn("too narrow", str(caught.exception))

    def test_oversize_builds_warn_about_the_bed(self):
        _, _, result = build("bin-shelf", rows=8, bed_z=200)
        self.assertTrue(
            any("Bigger than the bed" in w for w in result.report.warnings)
        )

    def test_a_tall_front_stop_warns_about_lifting_the_bin_out(self):
        _, _, result = build("bin-shelf", front_stop="label", label_height=20,
                             headroom=10)
        self.assertTrue(
            any("tilted rather than lifted" in w for w in result.report.warnings)
        )

    def test_wall_mount_forces_a_panel_to_hang_from(self):
        _, opt, result = build("bin-shelf", wall_mount=True, back="windowed",
                               stackable=False)
        self.assertEqual(opt["back"], "windowed", "the request is unchanged")
        self.assertEqual(
            result.effective_options["back"], "panel",
            "but the rack was built with a panel to hang from",
        )
        self.assertTrue(any("full panel" in n for n in result.report.notes))


class WallMount(unittest.TestCase):
    def build_it(self, **extra):
        options = {"wall_mount": True, "stackable": False, "rows": 1, **extra}
        _, opt, result = build("bin-shelf", **options)
        _, _, layout = layout_for(**{**options, "back": "panel"})
        return result.effective_options, layout, result.parts.parts[0].solid

    def test_the_flange_stands_above_the_rack(self):
        opt, layout, solid = self.build_it()
        self.assertGreater(layout.flange_height, 0)
        self.assertAlmostEqual(
            geom.bounds(solid)[5], layout.body_height + layout.flange_height,
            places=3,
        )

    def test_a_screw_head_passes_through_the_mouth_but_not_the_slot(self):
        """A keyhole that does not open wide enough is just a hole."""
        opt, layout, solid = self.build_it()
        head_d, shank_d = opt["keyhole_head"], opt["keyhole_screw"]
        top = layout.body_height + layout.flange_height
        z_entry = top - head_d / 2.0 - 4.0
        z_rest = z_entry - max(head_d * 1.1, 8.0)
        y0, y1 = layout.depth - 12.0, layout.depth + 1.0

        for fraction in (0.25, 0.75):
            x = layout.width * fraction
            with self.subTest(keyhole=fraction):
                mouth = geom.cylinder_y(head_d / 2.0 - 0.2, y0, y1,
                                        at_xz=(x, z_entry))
                self.assertLess(
                    geom.intersection([solid, mouth]).volume(), 1e-3,
                    "the head cannot get through the mouth",
                )
                head_at_rest = geom.cylinder_y(head_d / 2.0, y0, y1,
                                               at_xz=(x, z_rest))
                self.assertGreater(
                    geom.intersection([solid, head_at_rest]).volume(), 1.0,
                    "nothing traps the head once the rack drops",
                )
                shank = geom.cylinder_y(shank_d / 2.0 - 0.2, y0, y1,
                                        at_xz=(x, z_rest))
                self.assertLess(
                    geom.intersection([solid, shank]).volume(), 1e-3,
                    "the shank has nowhere to sit",
                )

    def test_a_head_no_bigger_than_the_shank_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            build("bin-shelf", wall_mount=True, keyhole_head=5.0,
                  keyhole_screw=5.0)
        self.assertIn("pass through", str(caught.exception))

    def test_too_short_a_flange_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            build("bin-shelf", wall_mount=True, mount_flange_height=18.0)
        self.assertIn("no room for a keyhole", str(caught.exception))


class Reporting(unittest.TestCase):
    def test_the_headline_size_matches_the_model(self):
        """Copy that quotes a size the model does not have is a returned order."""
        _, _, result = build("bin-shelf", stackable=True)
        height = result.facts["outside_mm"][2]
        headline = next(h for h in result.highlights if "Outside size" in h)
        self.assertIn(f"{height:.1f} mm", headline)

    def test_facts_match_the_geometry(self):
        _, _, result = build("bin-shelf", columns=2, rows=3)
        part = result.parts.parts[0]
        self.assertEqual(result.facts["capacity"], 6)
        self.assertEqual(
            result.facts["outside_mm"], [round(v, 2) for v in part.size]
        )
        self.assertFalse(result.facts["supports_required"])

    def test_estimated_dimensions_are_declared(self):
        _, _, result = build("bin-shelf")
        self.assertFalse(result.facts["bin_fully_measured"])
        self.assertIn("lip_overhang", result.facts["bin_estimated_fields"])

    def test_supplying_a_measurement_clears_the_estimate(self):
        _, _, result = build("bin-shelf", lip_overhang=3.1)
        self.assertIn(
            "user-supplied: lip_overhang", result.facts["bin_estimated_fields"]
        )


if __name__ == "__main__":
    unittest.main()
