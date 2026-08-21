import contextlib
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from _support import SRC  # noqa: F401

from storagegen import catalogue, cli
from storagegen.catalogue import CatalogueError, Variant

SWEEP = {
    "sweeps": [{
        "generator": "bin-shelf",
        "name": "rack_{columns}x{rows}_{pattern}",
        "options": {"bin": "greenmade-mini"},
        "axes": {"columns": [1, 2], "rows": [2, 3],
                 "pattern": ["windows", "honeycomb", "diamond"]},
    }]
}


class Expanding(unittest.TestCase):
    def test_a_sweep_becomes_every_combination(self):
        variants = catalogue.expand(SWEEP)
        self.assertEqual(len(variants), 2 * 2 * 3)
        self.assertIn("rack_2x3_diamond", {v.name for v in variants})

    def test_sweep_options_merge_over_the_shared_base(self):
        variant = next(
            v for v in catalogue.expand(SWEEP) if v.name == "rack_2x3_diamond"
        )
        self.assertEqual(
            variant.options,
            {"bin": "greenmade-mini", "columns": 2, "rows": 3,
             "pattern": "diamond"},
        )

    def test_items_and_sweeps_live_together(self):
        raw = dict(SWEEP)
        raw["items"] = [{"name": "gauge", "generator": "fit-gauge"}]
        names = [v.name for v in catalogue.expand(raw)]
        self.assertEqual(names[0], "gauge")
        self.assertEqual(len(names), 13)


class Rejecting(unittest.TestCase):
    """A catalogue is checked once, in a second, instead of by every job."""

    def test_an_option_the_generator_does_not_have(self):
        with self.assertRaises(CatalogueError) as caught:
            catalogue.expand({"items": [
                {"name": "x", "generator": "bin-shelf",
                 "options": {"colour": "red"}}
            ]})
        self.assertIn("x:", str(caught.exception))
        self.assertIn("colour", str(caught.exception))

    def test_a_value_outside_the_allowed_range(self):
        with self.assertRaises(CatalogueError) as caught:
            catalogue.expand({"items": [
                {"name": "x", "generator": "bin-shelf", "options": {"rows": 99}}
            ]})
        self.assertIn("maximum", str(caught.exception))

    def test_an_unknown_generator(self):
        with self.assertRaises(CatalogueError) as caught:
            catalogue.expand({"items": [{"name": "x", "generator": "nope"}]})
        self.assertIn("nope", str(caught.exception))

    def test_two_variants_with_the_same_name(self):
        with self.assertRaises(CatalogueError) as caught:
            catalogue.expand({"items": [
                {"name": "same", "generator": "fit-gauge"},
                {"name": "same", "generator": "fit-gauge"},
            ]})
        self.assertIn("duplicate", str(caught.exception))

    def test_a_name_template_referring_to_something_that_is_not_an_axis(self):
        with self.assertRaises(CatalogueError) as caught:
            catalogue.expand({"sweeps": [{
                "generator": "bin-shelf", "name": "rack_{nope}",
                "axes": {"rows": [2]},
            }]})
        self.assertIn("not an axis", str(caught.exception))

    def test_an_empty_catalogue(self):
        with self.assertRaises(CatalogueError):
            catalogue.expand({})

    def test_a_missing_file_says_so_plainly(self):
        with self.assertRaises(CatalogueError) as caught:
            catalogue.load(Path("/nowhere/catalogue.json"))
        self.assertIn("no catalogue", str(caught.exception))


class Selecting(unittest.TestCase):
    def setUp(self):
        self.variants = catalogue.expand(SWEEP).variants

    def test_a_limit_spreads_across_the_catalogue_by_default(self):
        picked = catalogue.select(self.variants, limit=3)
        self.assertEqual(len(picked), 3)
        patterns = {v.options["pattern"] for v in picked}
        self.assertGreater(len(patterns), 1, "a spread should not be all alike")

    def test_a_limit_can_take_the_first_instead(self):
        picked = catalogue.select(self.variants, limit=3, pick="first")
        self.assertEqual([v.name for v in picked],
                         [v.name for v in self.variants[:3]])

    def test_chunks_cover_everything_exactly_once(self):
        chunks = 4
        seen = []
        for index in range(chunks):
            seen += catalogue.select(self.variants, chunk=index, chunks=chunks)
        self.assertEqual(
            sorted(v.name for v in seen),
            sorted(v.name for v in self.variants),
        )

    def test_chunks_are_balanced(self):
        sizes = [
            len(catalogue.select(self.variants, chunk=i, chunks=5))
            for i in range(5)
        ]
        self.assertLessEqual(max(sizes) - min(sizes), 1)

    def test_selecting_by_name(self):
        picked = catalogue.select(self.variants, only=["rack_1x2_windows"])
        self.assertEqual(len(picked), 1)

    def test_an_unknown_name_is_refused(self):
        with self.assertRaises(CatalogueError) as caught:
            catalogue.select(self.variants, only=["nope"])
        self.assertIn("nope", str(caught.exception))

    def test_a_chunk_outside_the_range_is_refused(self):
        with self.assertRaises(CatalogueError):
            catalogue.select(self.variants, chunk=9, chunks=3)

    def test_chunk_count_scales_with_the_catalogue(self):
        self.assertEqual(catalogue.chunk_count(0, 8), 1)
        self.assertEqual(catalogue.chunk_count(8, 8), 1)
        self.assertEqual(catalogue.chunk_count(9, 8), 2)
        self.assertEqual(catalogue.chunk_count(10_000, 1, cap=200), 200)


class TheShippedCatalogue(unittest.TestCase):
    def test_it_expands_and_every_variant_validates(self):
        path = Path(__file__).resolve().parents[1] / "catalogue.json"
        loaded = catalogue.load(path)
        self.assertGreater(len(loaded), 5)
        for variant in loaded.variants:
            catalogue.validate(variant, str(path))

    def test_it_names_the_release_it_produces(self):
        path = Path(__file__).resolve().parents[1] / "catalogue.json"
        release = catalogue.load(path).release
        self.assertIsNotNone(release, "the shipped catalogue should be nameable")
        self.assertEqual(release.tag, f"{release.name}-v{release.version}")
        self.assertTrue(release.summary)


class ReleaseNaming(unittest.TestCase):
    """The tag names the product line, and becomes a git tag and a file name."""

    def expand_with(self, **release):
        return catalogue.expand({
            "release": release,
            "items": [{"name": "g", "generator": "fit-gauge"}],
        })

    def test_a_tag_is_the_name_and_the_version(self):
        release = self.expand_with(
            name="storage-shelving", version="1.2.3", title="Storage Shelving"
        ).release
        self.assertEqual(release.tag, "storage-shelving-v1.2.3")
        self.assertEqual(release.display, "Storage Shelving v1.2.3")

    def test_a_catalogue_need_not_declare_one(self):
        self.assertIsNone(catalogue.expand(
            {"items": [{"name": "g", "generator": "fit-gauge"}]}).release)

    def test_a_name_that_is_not_safe_in_a_tag_is_refused(self):
        for bad in ("Storage Shelving", "storage_shelving", "-leading",
                    "trailing-", "storage--shelving"):
            with self.subTest(name=bad):
                with self.assertRaises(CatalogueError):
                    self.expand_with(name=bad, version="1.0.0", title="x")

    def test_a_version_that_is_not_three_numbers_is_refused(self):
        for bad in ("1.0", "v1.0.0", "1.0.0-rc1", "latest"):
            with self.subTest(version=bad):
                with self.assertRaises(CatalogueError):
                    self.expand_with(name="ok", version=bad, title="x")

    def test_a_release_missing_a_field_says_which(self):
        with self.assertRaises(CatalogueError) as caught:
            self.expand_with(name="ok", version="1.0.0")
        self.assertIn("title", str(caught.exception))


def run_cli(argv):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        code = cli.main(argv)
    return code, buffer.getvalue()


class Commands(unittest.TestCase):
    """The commands a workflow drives, checked the way a workflow calls them."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.catalogue = self.root / "catalogue.json"
        self.catalogue.write_text(json.dumps({
            "release": {"name": "kit", "version": "2.0.0", "title": "Test Kit",
                        "summary": "A catalogue used by the tests."},
            "items": [{"name": "gauge", "generator": "fit-gauge",
                       "options": {"rail_sample": False}}],
            "sweeps": [{
                "generator": "bin-shelf",
                "name": "rack_{rows}_{pattern}",
                "options": {"rows": 1},
                "axes": {"rows": [1, 2], "pattern": ["windows", "honeycomb"]},
            }],
        }))

    def tearDown(self):
        self.tmp.cleanup()

    def test_schema_lists_every_variable_a_pipeline_could_set(self):
        code, output = run_cli(["schema"])
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertIn("bin-shelf", payload["generators"])
        self.assertIn("greenmade-mini", payload["bins"])
        names = {o["name"] for o in payload["generators"]["bin-shelf"]["options"]}
        for expected in ("pattern", "columns", "rows", "lip_overhang"):
            self.assertIn(expected, names)
        pattern = next(o for o in payload["generators"]["bin-shelf"]["options"]
                       if o["name"] == "pattern")
        self.assertIn("honeycomb", pattern["choices"])

    def test_plan_emits_a_matrix_whose_chunks_add_up(self):
        code, output = run_cli([
            "plan", "--catalogue", str(self.catalogue), "--chunk-size", "2",
            "--emit", "matrix",
        ])
        self.assertEqual(code, 0)
        matrix = json.loads(output)
        self.assertTrue(matrix)
        self.assertEqual(sum(entry["count"] for entry in matrix), 5)
        self.assertEqual({entry["chunks"] for entry in matrix}, {len(matrix)})
        self.assertEqual([entry["chunk"] for entry in matrix],
                         list(range(len(matrix))))

    def test_plan_reports_a_catalogue_error_without_a_traceback(self):
        bad = self.root / "bad.json"
        bad.write_text(json.dumps({"items": [
            {"name": "x", "generator": "bin-shelf", "options": {"rows": 99}}
        ]}))
        code, output = run_cli(["plan", "--catalogue", str(bad)])
        self.assertEqual(code, 2)
        self.assertIn("maximum", output)

    def test_batch_builds_a_chunk_verifies_it_and_indexes_it(self):
        out = self.root / "out"
        code, output = run_cli([
            "batch", "--catalogue", str(self.catalogue), "--chunk", "0",
            "--chunks", "2", "--out", str(out), "--no-preview",
        ])
        self.assertEqual(code, 0, output)
        self.assertIn("verified", output)
        index = json.loads((out / "index.json").read_text())
        self.assertEqual(len(index["built"]), 3)
        self.assertEqual(index["failed"], [])
        self.assertTrue((out / "INDEX.md").exists())

    def test_verify_passes_what_batch_wrote(self):
        out = self.root / "out"
        run_cli(["batch", "--catalogue", str(self.catalogue), "--limit", "2",
                 "--out", str(out), "--no-preview"])
        code, output = run_cli(["verify", str(out)])
        self.assertEqual(code, 0, output)
        self.assertIn("failed", output)

    def test_verify_fails_on_a_file_it_cannot_accept(self):
        out = self.root / "out"
        run_cli(["batch", "--catalogue", str(self.catalogue), "--limit", "1",
                 "--out", str(out), "--no-preview"])
        stl = next(out.rglob("*.stl"))
        data = bytearray(stl.read_bytes())
        del data[-50:]                       # lose one triangle, keep the count
        stl.write_bytes(bytes(data))
        code, _ = run_cli(["verify", str(out)])
        self.assertEqual(code, 1)

    def test_release_emit_names_the_tag_and_flags_a_partial_run(self):
        full = json.loads(run_cli([
            "plan", "--catalogue", str(self.catalogue), "--emit", "release",
        ])[1])
        self.assertEqual(full["tag"], "kit-v2.0.0")
        self.assertEqual(full["display"], "Test Kit v2.0.0")
        self.assertTrue(full["complete"])
        self.assertEqual(full["planned"], full["total"])

        partial = json.loads(run_cli([
            "plan", "--catalogue", str(self.catalogue), "--limit", "2",
            "--emit", "release",
        ])[1])
        self.assertFalse(
            partial["complete"],
            "a limited run must not claim to be the whole catalogue",
        )

    def test_release_emit_needs_a_release_block(self):
        bare = self.root / "bare.json"
        bare.write_text(json.dumps({
            "items": [{"name": "g", "generator": "fit-gauge"}]}))
        code, output = run_cli(["plan", "--catalogue", str(bare),
                                "--emit", "release"])
        self.assertEqual(code, 2)
        self.assertIn("no 'release' block", output)

    def test_notes_are_built_from_what_was_written(self):
        out = self.root / "out"
        run_cli(["batch", "--catalogue", str(self.catalogue), "--out", str(out),
                 "--no-preview"])
        run_cli(["verify", str(out), "--json", str(out / "verify.json")])
        code, _ = run_cli([
            "notes", str(out), "--catalogue", str(self.catalogue),
            "--verify", str(out / "verify.json"),
        ])
        self.assertEqual(code, 0)
        notes = (out / "RELEASE-NOTES.md").read_text()
        self.assertIn("# Test Kit v2.0.0", notes)
        self.assertIn("**5 models**", notes)
        self.assertIn("| **Failed** | **0** |", notes)
        self.assertIn("Print the fit gauge first", notes)

    def test_notes_need_an_index_first(self):
        empty = self.root / "empty"
        empty.mkdir()
        code, output = run_cli(["notes", str(empty), "--catalogue",
                                str(self.catalogue)])
        self.assertEqual(code, 2)
        self.assertIn("index.json", output)

    def test_index_can_be_rebuilt_over_merged_chunks(self):
        out = self.root / "out"
        for chunk in range(2):
            run_cli(["batch", "--catalogue", str(self.catalogue),
                     "--chunk", str(chunk), "--chunks", "2",
                     "--out", str(out), "--no-preview"])
        code, output = run_cli(["index", str(out)])
        self.assertEqual(code, 0)
        self.assertIn("indexed 5", output)


if __name__ == "__main__":
    unittest.main()
