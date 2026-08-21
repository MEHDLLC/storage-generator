import contextlib
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from _support import SRC  # noqa: F401

from storagegen import cli, runner
from storagegen import generator as registry


class Run(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.result = runner.run(
            registry.get("bin-shelf"), {"rows": 2}, out_root=self.root
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_run_leaves_models_words_and_a_record(self):
        names = {path.name for path in self.result.directory.iterdir()}
        self.assertIn("listing.md", names)
        self.assertIn("listing.json", names)
        self.assertIn("manifest.json", names)
        self.assertIn("preview.png", names)
        self.assertIn("preview-in-use.png", names)
        self.assertTrue(any(n.endswith(".stl") for n in names))
        self.assertTrue(any(n.endswith(".3mf") for n in names))

    def test_the_manifest_lists_every_file_it_sits_beside(self):
        manifest = json.loads((self.result.directory / "manifest.json").read_text())
        on_disk = sorted(p.name for p in self.result.directory.iterdir())
        self.assertEqual(sorted(manifest["files"]), on_disk)

    def test_the_listing_carries_a_title_and_a_description(self):
        listing = json.loads((self.result.directory / "listing.json").read_text())
        self.assertTrue(listing["title"])
        self.assertLess(len(listing["title"]), 140)
        body = (self.result.directory / "listing.md").read_text()
        for heading in ("## Highlights", "## What you get", "## Dimensions",
                        "## Printing", "## Options used"):
            self.assertIn(heading, body)

    def test_the_description_quotes_the_size_the_model_really_is(self):
        body = (self.result.directory / "listing.md").read_text()
        width, depth, height = self.result.manifest["facts"]["outside_mm"]
        self.assertIn(f"{width:.1f} mm", body)
        self.assertIn(f"{height:.1f} mm", body)

    def test_the_same_options_hash_the_same_way(self):
        again = runner.run(registry.get("bin-shelf"), {"rows": 2},
                           out_root=self.root)
        self.assertEqual(
            self.result.manifest["options_hash"], again.manifest["options_hash"]
        )
        different = runner.run(registry.get("bin-shelf"), {"rows": 3},
                               out_root=self.root)
        self.assertNotEqual(
            self.result.manifest["options_hash"], different.manifest["options_hash"]
        )

    def test_every_exported_part_is_recorded_as_watertight(self):
        for part in self.result.manifest["parts"]:
            self.assertTrue(part["watertight_manifold"], part["name"])

    def test_formats_can_be_narrowed(self):
        only_stl = runner.run(registry.get("bin-shelf"), {"rows": 1},
                              out_root=self.root, formats=["stl"],
                              with_preview=False, slug="stl-only")
        names = {p.name for p in only_stl.directory.iterdir()}
        self.assertFalse(any(n.endswith(".3mf") for n in names))
        self.assertFalse(any(n.endswith(".png") for n in names))

    def test_an_unsupported_format_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            runner.run(registry.get("bin-shelf"), {}, out_root=self.root,
                       formats=["obj"])
        self.assertIn("obj", str(caught.exception))


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def run_cli(argv):
        """Run the CLI with its console output captured."""
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            code = cli.main(argv)
        return code, buffer.getvalue()

    def test_listing_generators_and_bins_succeeds(self):
        for argv, expected in (
            (["list"], "bin-shelf"),
            (["bins"], "greenmade-mini"),
            (["options", "bin-shelf"], "--rail-width"),
        ):
            code, output = self.run_cli(argv)
            self.assertEqual(code, 0)
            self.assertIn(expected, output)

    def test_building_from_flags_writes_a_run(self):
        code, _ = self.run_cli([
            "bin-shelf", "--rows", "2", "--columns", "2",
            "--out", str(self.root), "--no-preview",
        ])
        self.assertEqual(code, 0)
        runs = list(self.root.iterdir())
        self.assertEqual(len(runs), 1)
        self.assertIn("2x2", runs[0].name)

    def test_set_pairs_are_accepted(self):
        code, _ = self.run_cli([
            "fit-gauge", "--set", "step=0.5", "--out", str(self.root),
            "--no-preview",
        ])
        self.assertEqual(code, 0)

    def test_a_bad_value_fails_without_a_traceback(self):
        code, output = self.run_cli([
            "bin-shelf", "--back", "open", "--out", str(self.root),
            "--no-preview",
        ])
        self.assertEqual(code, 1)
        self.assertIn("two loose halves", output)

    def test_an_unknown_option_name_is_reported(self):
        code, output = self.run_cli([
            "bin-shelf", "--set", "colour=red", "--out", str(self.root),
        ])
        self.assertEqual(code, 1)
        self.assertIn("colour", output)


if __name__ == "__main__":
    unittest.main()
