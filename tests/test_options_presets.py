import unittest

from _support import SRC  # noqa: F401

from storagegen.options import Option, OptionError, OptionSet
from storagegen.presets import BIN_PRESETS, get_bin


SAMPLE = OptionSet([
    Option("rows", 5, "levels", kind="int", minimum=1, maximum=10),
    Option("wall", 3.0, "thickness", unit=" mm", minimum=1.0),
    Option("back", "panel", "back style", kind="choice",
           choices=("open", "panel")),
    Option("stackable", True, "stack", kind="bool"),
    Option("lip", None, "override", minimum=0.5),
])


class Resolving(unittest.TestCase):
    def test_defaults_come_through_untouched(self):
        self.assertEqual(
            SAMPLE.resolve(),
            {"rows": 5, "wall": 3.0, "back": "panel", "stackable": True,
             "lip": None},
        )

    def test_strings_are_coerced_to_the_declared_type(self):
        resolved = SAMPLE.resolve({"rows": "3", "wall": "2.5",
                                   "stackable": "no"})
        self.assertEqual(resolved["rows"], 3)
        self.assertEqual(resolved["wall"], 2.5)
        self.assertIs(resolved["stackable"], False)

    def test_bool_accepts_the_words_people_actually_type(self):
        for text in ("yes", "true", "1", "on", "Y"):
            self.assertIs(SAMPLE.resolve({"stackable": text})["stackable"], True)
        for text in ("no", "false", "0", "off", "N"):
            self.assertIs(SAMPLE.resolve({"stackable": text})["stackable"], False)


class Rejecting(unittest.TestCase):
    def test_out_of_range_says_what_the_range_is(self):
        with self.assertRaises(OptionError) as caught:
            SAMPLE.resolve({"rows": 99})
        self.assertIn("maximum 10", str(caught.exception))

    def test_a_bad_choice_lists_the_good_ones(self):
        with self.assertRaises(OptionError) as caught:
            SAMPLE.resolve({"back": "sideways"})
        self.assertIn("open, panel", str(caught.exception))

    def test_an_unknown_option_is_not_silently_ignored(self):
        with self.assertRaises(OptionError) as caught:
            SAMPLE.resolve({"colour": "red"})
        self.assertIn("colour", str(caught.exception))

    def test_nonsense_numbers_are_rejected(self):
        with self.assertRaises(OptionError):
            SAMPLE.resolve({"wall": "thick"})

    def test_duplicate_names_are_a_programming_error(self):
        with self.assertRaises(ValueError):
            OptionSet([Option("a", 1, "x"), Option("a", 2, "y")])


class Presets(unittest.TestCase):
    def test_the_greenmade_mini_matches_its_published_size(self):
        spec = get_bin("greenmade-mini")
        self.assertAlmostEqual(spec.length / 25.4, 4.8, places=3)
        self.assertAlmostEqual(spec.width / 25.4, 3.3, places=3)
        self.assertAlmostEqual(spec.height / 25.4, 2.4, places=3)

    def test_derived_measurements_follow_from_the_rim(self):
        spec = get_bin("greenmade-mini")
        self.assertAlmostEqual(
            spec.body_width, spec.width - 2 * spec.lip_overhang, places=6
        )
        self.assertAlmostEqual(
            spec.hang_depth, spec.height - spec.lip_thickness, places=6
        )
        self.assertLess(spec.base_width, spec.body_width, "the bin tapers")

    def test_estimated_fields_are_declared_not_hidden(self):
        spec = get_bin("greenmade-mini")
        self.assertFalse(spec.fully_measured)
        self.assertIn("lip_overhang", spec.estimated_fields)
        self.assertIn("width", spec.measured_fields)

    def test_supplying_a_measurement_moves_it_out_of_the_estimates(self):
        spec = get_bin("greenmade-mini").replace(lip_overhang=3.4)
        self.assertNotIn("lip_overhang", spec.estimated_fields)
        self.assertIn("user-supplied: lip_overhang", spec.estimated_fields)
        self.assertAlmostEqual(spec.lip_overhang, 3.4)

    def test_replacing_a_published_dimension_drops_its_measured_claim(self):
        spec = get_bin("greenmade-mini").replace(width=90.0)
        self.assertNotIn("width", spec.measured_fields)

    def test_an_unknown_preset_names_the_known_ones(self):
        with self.assertRaises(KeyError) as caught:
            get_bin("nope")
        self.assertIn("greenmade-mini", str(caught.exception))

    def test_every_preset_produces_a_usable_solid(self):
        for key, spec in BIN_PRESETS.items():
            with self.subTest(bin=key):
                solid = spec.solid()
                self.assertEqual(len(solid.decompose()), 1)
                width, depth, height = (
                    solid.bounding_box()[i + 3] - solid.bounding_box()[i]
                    for i in range(3)
                )
                self.assertAlmostEqual(width, spec.width, places=3)
                self.assertAlmostEqual(depth, spec.length, places=3)
                self.assertAlmostEqual(height, spec.height, places=3)


if __name__ == "__main__":
    unittest.main()
