import unittest

from _support import build

from storagegen import geom


class Steps(unittest.TestCase):
    def test_readings_are_round_numbers_stepping_evenly_down(self):
        _, opt, result = build("fit-gauge")
        steps = result.facts["step_widths_mm"]
        self.assertGreater(len(steps), 5)
        for width in steps:
            self.assertAlmostEqual(width % opt["step"], 0.0, places=6)
        for earlier, later in zip(steps, steps[1:]):
            self.assertAlmostEqual(earlier - later, opt["step"], places=6)

    def test_the_range_brackets_both_measurements_it_has_to_take(self):
        _, _, result = build("fit-gauge")
        steps = result.facts["step_widths_mm"]
        self.assertGreater(steps[0], result.facts["expected_rim_width_mm"])
        self.assertLess(steps[-1], result.facts["expected_body_width_mm"])

    def test_too_few_steps_is_refused_rather_than_shipped(self):
        with self.assertRaises(ValueError):
            build("fit-gauge", range_above=1.0, range_below=1.0, step=4.0)


class Slot(unittest.TestCase):
    """Each step has to be the width it claims, or the gauge lies."""

    def gauge(self, **options):
        _, opt, result = build("fit-gauge", **options)
        return opt, result, result.parts.parts[0].solid

    def test_each_step_measures_exactly_what_it_says(self):
        opt, result, solid = self.gauge()
        steps = result.facts["step_widths_mm"]
        centre = (steps[0] + 2 * opt["gauge_margin"]) / 2.0
        step_len = opt["step_length"]

        for index, width in enumerate(steps):
            with self.subTest(step=index, width=width):
                y0 = index * step_len + 1.0
                y1 = (index + 1) * step_len - 1.0
                fits = geom.box(
                    [width - 0.1, y1 - y0, 2.0],
                    at=[centre - (width - 0.1) / 2.0, y0, 1.0],
                )
                too_wide = geom.box(
                    [width + 0.4, y1 - y0, 2.0],
                    at=[centre - (width + 0.4) / 2.0, y0, 1.0],
                )
                self.assertLess(
                    geom.intersection([solid, fits]).volume(), 1e-3,
                    "the slot is narrower here than the step claims",
                )
                self.assertGreater(
                    geom.intersection([solid, too_wide]).volume(), 0.1,
                    "the slot is wider here than the step claims",
                )

    def test_the_slot_only_narrows(self):
        opt, result, _ = self.gauge()
        steps = result.facts["step_widths_mm"]
        self.assertEqual(steps, sorted(steps, reverse=True))


class Parts(unittest.TestCase):
    def test_both_parts_are_single_watertight_solids(self):
        _, _, result = build("fit-gauge")
        self.assertEqual(len(result.parts), 2)
        for part in result.parts:
            with self.subTest(part=part.name):
                self.assertEqual(len(part.solid.decompose()), 1)
                self.assertTrue(part.is_manifold())

    def test_the_rail_sample_can_be_turned_off(self):
        _, _, result = build("fit-gauge", rail_sample=False)
        self.assertEqual(len(result.parts), 1)

    def test_the_sample_span_tracks_the_bin_and_the_offset(self):
        _, _, nominal = build("fit-gauge")
        _, _, looser = build("fit-gauge", sample_span_offset=1.5)
        self.assertAlmostEqual(
            looser.facts["sample_rail_span_mm"]
            - nominal.facts["sample_rail_span_mm"],
            1.5, places=3,
        )

    def test_the_sample_matches_the_rack_the_rack_generator_would_build(self):
        _, _, gauge = build("fit-gauge")
        from storagegen.generators import bin_shelf
        from storagegen.options import Report
        _, rack_opt, _ = build("bin-shelf")
        spec = bin_shelf.resolve_bin(rack_opt, Report())
        layout = bin_shelf.Layout(spec, rack_opt)
        self.assertAlmostEqual(
            gauge.facts["sample_rail_span_mm"], round(layout.span, 2), places=2
        )

    def test_the_listing_explains_how_to_read_it(self):
        generator, opt, result = build("fit-gauge")
        body = " ".join(generator.listing_body(opt, result))
        self.assertIn("Over the rim", body)
        self.assertIn("Under the rim", body)
        self.assertIn("Half the difference", body)


if __name__ == "__main__":
    unittest.main()
