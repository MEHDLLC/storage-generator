import struct
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree

from _support import SRC  # noqa: F401

from storagegen import geom, mesh_io

NS = {"c": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}


def read_stl(path: Path):
    data = path.read_bytes()
    count = struct.unpack("<I", data[80:84])[0]
    triangles = []
    for index in range(count):
        chunk = data[84 + index * 50: 84 + (index + 1) * 50]
        values = struct.unpack("<12fH", chunk)
        triangles.append(values[3:12])
    return count, triangles


class BinaryStl(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trips_with_the_right_triangle_count_and_size(self):
        part = mesh_io.Part("cube", geom.box([10, 20, 30], at=[5, 5, 5]))
        path = mesh_io.write_stl(self.dir / "cube.stl", part)
        count, triangles = read_stl(path)

        self.assertEqual(count, part.triangle_count)
        self.assertEqual(len(path.read_bytes()), 84 + 50 * count)
        xs = [t[i] for t in triangles for i in (0, 3, 6)]
        zs = [t[i] for t in triangles for i in (2, 5, 8)]
        self.assertAlmostEqual(max(xs) - min(xs), 10.0, places=4)
        self.assertAlmostEqual(max(zs) - min(zs), 30.0, places=4)

    def test_the_part_is_moved_onto_the_origin(self):
        part = mesh_io.Part("offset", geom.box([10, 10, 10], at=[40, 60, 25]))
        _, triangles = read_stl(mesh_io.write_stl(self.dir / "a.stl", part))
        coordinates = [t[i] for t in triangles for i in range(9)]
        self.assertAlmostEqual(min(coordinates), 0.0, places=5)

    def test_identical_input_gives_identical_bytes(self):
        part = mesh_io.Part("cube", geom.box([8, 8, 8]))
        first = mesh_io.write_stl(self.dir / "1.stl", part).read_bytes()
        second = mesh_io.write_stl(self.dir / "2.stl", part).read_bytes()
        self.assertEqual(first, second)


class ThreeMf(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.parts = [
            mesh_io.Part("rack", geom.box([30, 20, 10])),
            mesh_io.Part("gauge", geom.box([12, 12, 4])),
        ]
        self.path = mesh_io.write_3mf(
            self.dir / "set.3mf", self.parts,
            {"Title": "A rack & gauge", "Designer": "storage-generator"},
        )

    def tearDown(self):
        self.tmp.cleanup()

    def model(self):
        with zipfile.ZipFile(self.path) as archive:
            return ElementTree.fromstring(archive.read("3D/3dmodel.model"))

    def test_package_has_the_parts_a_3mf_reader_looks_for(self):
        with zipfile.ZipFile(self.path) as archive:
            self.assertEqual(
                sorted(archive.namelist()),
                sorted(["[Content_Types].xml", "_rels/.rels",
                        "3D/3dmodel.model"]),
            )

    def test_units_are_declared_as_millimetres(self):
        self.assertEqual(self.model().get("unit"), "millimeter")

    def test_every_part_is_a_named_object_on_the_plate(self):
        model = self.model()
        objects = model.findall(".//c:object", NS)
        self.assertEqual([o.get("name") for o in objects], ["rack", "gauge"])
        items = model.findall(".//c:item", NS)
        self.assertEqual(len(items), len(self.parts))

    def test_parts_are_spread_out_rather_than_stacked_on_each_other(self):
        offsets = [
            float(item.get("transform").split()[9])
            for item in self.model().findall(".//c:item", NS)
        ]
        self.assertEqual(offsets[0], 0.0)
        self.assertGreaterEqual(offsets[1], 30.0)

    def test_metadata_is_escaped_not_broken(self):
        titles = [
            m.text for m in self.model().findall("c:metadata", NS)
            if m.get("name") == "Title"
        ]
        self.assertEqual(titles, ["A rack & gauge"])

    def test_identical_input_gives_identical_bytes(self):
        again = mesh_io.write_3mf(self.dir / "again.3mf", self.parts,
                                  {"Title": "A rack & gauge",
                                   "Designer": "storage-generator"})
        self.assertEqual(self.path.read_bytes(), again.read_bytes())

    def test_an_empty_set_is_refused(self):
        with self.assertRaises(ValueError):
            mesh_io.write_3mf(self.dir / "empty.3mf", [], {})


if __name__ == "__main__":
    unittest.main()
