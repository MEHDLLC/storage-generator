import struct
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from _support import SRC  # noqa: F401

import numpy as np

from storagegen import geom, mesh_io, verify


def corners_of(solid):
    part = mesh_io.Part("x", solid)
    verts, tris = part.mesh()
    return verts[tris]


def write_raw_stl(path: Path, corners: np.ndarray, declared: int | None = None):
    """Write an STL by hand so a test can make it wrong on purpose."""
    record = np.zeros(len(corners), dtype=verify._STL_RECORD)
    record["v"] = corners
    with path.open("wb") as handle:
        handle.write(b"test".ljust(80, b"\0"))
        handle.write(struct.pack("<I", declared if declared is not None
                                 else len(corners)))
        handle.write(record.tobytes())
    return path


class GoodFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_plain_box_passes_every_check(self):
        part = mesh_io.Part("box", geom.box([10, 20, 30]))
        report = verify.verify_file(mesh_io.write_stl(self.dir / "b.stl", part))[0]
        self.assertTrue(report.ok, report.problems)
        self.assertTrue(report.watertight)
        self.assertTrue(report.oriented)
        self.assertEqual(report.components, 1)
        self.assertEqual(report.genus, 0)
        self.assertAlmostEqual(report.volume_mm3, 6000.0, places=2)
        self.assertEqual([round(v) for v in report.size_mm], [10, 20, 30])

    def test_a_3mf_reports_each_object_it_holds(self):
        parts = [mesh_io.Part("a", geom.box([10, 10, 10])),
                 mesh_io.Part("b", geom.box([4, 4, 4]))]
        path = mesh_io.write_3mf(self.dir / "s.3mf", parts, {"Title": "t"})
        reports = verify.verify_file(path)
        self.assertEqual(len(reports), 2)
        self.assertTrue(all(r.ok for r in reports))

    def test_genus_counts_holes_through_the_part(self):
        # A bar with a hole bored through it: one piece, one tunnel.
        ring = geom.difference(
            geom.box([20, 20, 12]),
            geom.cylinder_y(3, -1, 21, at_xz=(10, 6)),
        )
        report = verify.verify_file(mesh_io.write_stl(
            self.dir / "r.stl", mesh_io.Part("ring", ring)))[0]
        self.assertTrue(report.ok, report.problems)
        self.assertEqual(report.genus, 1)


class BrokenFiles(unittest.TestCase):
    """Each of these is a way a file can be wrong that an eyeball would miss."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.corners = corners_of(geom.box([10, 10, 10]))

    def tearDown(self):
        self.tmp.cleanup()

    def problems(self, corners, **kwargs):
        path = write_raw_stl(self.dir / "t.stl", corners, **kwargs)
        return verify.verify_file(path)[0].problems

    def test_a_truncated_file_is_caught_by_its_own_header(self):
        path = write_raw_stl(self.dir / "t.stl", self.corners)
        data = path.read_bytes()
        path.write_bytes(data[:-60])
        with self.assertRaises(ValueError) as caught:
            verify.verify_file(path)
        self.assertIn("Truncated", str(caught.exception))

    def test_a_missing_triangle_shows_up_as_a_hole(self):
        problems = self.problems(self.corners[:-1])
        self.assertTrue(any("not watertight" in p for p in problems), problems)

    def test_a_flipped_triangle_shows_up_as_bad_winding(self):
        corners = self.corners.copy()
        corners[0] = corners[0][::-1]
        problems = self.problems(corners)
        self.assertTrue(
            any("inconsistent winding" in p for p in problems), problems
        )

    def test_a_mesh_turned_inside_out_has_negative_volume(self):
        problems = self.problems(self.corners[:, ::-1])
        self.assertTrue(any("inside out" in p for p in problems), problems)

    def test_two_loose_pieces_are_rejected(self):
        pair = np.concatenate(
            [self.corners, corners_of(geom.box([5, 5, 5], at=[50, 0, 0]))]
        )
        problems = self.problems(pair)
        self.assertTrue(
            any("disconnected pieces" in p for p in problems), problems
        )

    def test_two_loose_pieces_are_allowed_when_asked_for(self):
        pair = np.concatenate(
            [self.corners, corners_of(geom.box([5, 5, 5], at=[50, 0, 0]))]
        )
        path = write_raw_stl(self.dir / "t.stl", pair)
        report = verify.verify_file(path, expect_one_piece=False)[0]
        self.assertTrue(report.ok, report.problems)
        self.assertEqual(report.components, 2)

    def test_a_not_a_number_vertex_is_caught(self):
        corners = self.corners.copy()
        corners[0, 0, 0] = np.nan
        problems = self.problems(corners)
        self.assertTrue(any("NaN" in p for p in problems), problems)

    def test_an_ascii_stl_is_refused_rather_than_misread(self):
        path = self.dir / "a.stl"
        path.write_bytes(
            b"solid x\n facet normal 0 0 0\n" + b" " * 600
        )
        with self.assertRaises(ValueError) as caught:
            verify.verify_file(path)
        self.assertIn("ASCII", str(caught.exception))

    def test_a_3mf_that_lies_about_its_units_is_refused(self):
        good = mesh_io.write_3mf(
            self.dir / "s.3mf", [mesh_io.Part("a", geom.box([9, 9, 9]))], {})
        with zipfile.ZipFile(good) as archive:
            payload = {n: archive.read(n) for n in archive.namelist()}
        payload["3D/3dmodel.model"] = payload["3D/3dmodel.model"].replace(
            b'unit="millimeter"', b'unit="inch"')
        bad = self.dir / "inch.3mf"
        with zipfile.ZipFile(bad, "w") as archive:
            for name, blob in payload.items():
                archive.writestr(name, blob)
        with self.assertRaises(ValueError) as caught:
            verify.verify_file(bad)
        self.assertIn("millimetres", str(caught.exception))


class AgainstTheManifest(unittest.TestCase):
    def test_a_manifest_that_disagrees_with_the_file_is_a_failure(self):
        import json

        from storagegen import generator as registry
        from storagegen import runner

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = runner.run(registry.get("bin-shelf"), {"rows": 1},
                                out_root=root, with_preview=False)
            clean = verify.verify_directory(result.directory)
            self.assertTrue(all(not r.problems for r in clean),
                            [r.problems for r in clean])

            manifest_path = result.directory / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["parts"][0]["volume_cm3"] *= 1.5
            manifest_path.write_text(json.dumps(manifest))

            after = verify.verify_directory(result.directory)
            self.assertTrue(
                any("manifest claims" in p for r in after for p in r.problems),
                [r.problems for r in after],
            )


class EveryShippedModel(unittest.TestCase):
    """The files the generators actually write, checked as files."""

    def test_a_run_of_each_generator_verifies_clean(self):
        from storagegen import generator as registry
        from storagegen import runner

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for key, options in (("bin-shelf", {"rows": 1}),
                                 ("bin-shelf", {"rows": 1, "pattern": "honeycomb",
                                                "base": "cut", "top": "cut"}),
                                 ("fit-gauge", {})):
                with self.subTest(generator=key, **options):
                    result = runner.run(registry.get(key), options,
                                        out_root=root, with_preview=False,
                                        slug=f"{key}-{len(options)}-{options.get('pattern','')}")
                    reports = verify.verify_directory(result.directory)
                    self.assertTrue(reports)
                    for report in reports:
                        self.assertEqual(report.problems, [], report.name)


if __name__ == "__main__":
    unittest.main()
