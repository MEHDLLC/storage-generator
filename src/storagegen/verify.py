"""Independent validation of the files a run actually wrote.

The generators build on manifold3d, which cannot produce a non-manifold solid,
so checking the in-memory object proves very little. What can still go wrong is
everything after that: a truncated write, a bad triangle count in an STL header,
an exporter that drops a vertex, a file copied badly by CI. This module reads
the bytes back off disk and works out the topology from scratch.

STL carries no topology at all -- three unshared float32 corners per triangle --
so any reader has to weld coincident vertices before it can say anything about
watertightness. That is exactly what a slicer does when it opens the file, so
welding here is not a workaround, it is the test. The weld is done by snapping
to a fixed grid rather than by a scale-dependent tolerance, so the same file
always gives the same answer.

Deliberately not included: mesh repair. If something here fails, the geometry
is wrong upstream and the fix belongs there. Repairing a hole would ship a
model whose shape nobody chose.
"""

from __future__ import annotations

import json
import struct
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

import numpy as np

# Snap-to-grid used when welding STL corners. Well below any real feature and
# well above float32 noise at the sizes these parts are.
WELD_GRID_MM = 1e-3

_STL_RECORD = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
_CORE_NS = {"c": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}


@dataclass
class MeshReport:
    """What the bytes on disk turned out to describe."""

    path: Path
    name: str
    triangles: int = 0
    vertices: int = 0
    edges: int = 0
    components: int = 0
    genus: int = 0
    volume_mm3: float = 0.0
    size_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    boundary_edges: int = 0
    overused_edges: int = 0
    flipped_edges: int = 0
    degenerate_triangles: int = 0
    non_finite_vertices: int = 0
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def watertight(self) -> bool:
        return self.boundary_edges == 0 and self.overused_edges == 0

    @property
    def oriented(self) -> bool:
        return self.flipped_edges == 0

    @property
    def ok(self) -> bool:
        return not self.problems

    def summary(self) -> str:
        state = "FAIL" if self.problems else ("WARN" if self.warnings else "PASS")
        return (
            f"{state}  {self.name:<38} {self.triangles:>6d} tri  "
            f"{self.volume_mm3 / 1000.0:>8.1f} cm3  "
            f"{'x'.join(f'{v:.1f}' for v in self.size_mm):>22}  "
            f"{self.components} piece{'s' if self.components != 1 else ''}"
        )

    def to_dict(self) -> dict:
        return {
            "file": str(self.path),
            "name": self.name,
            "ok": self.ok,
            "triangles": self.triangles,
            "vertices": self.vertices,
            "edges": self.edges,
            "components": self.components,
            "genus": self.genus,
            "watertight": self.watertight,
            "winding_consistent": self.oriented,
            "volume_cm3": round(self.volume_mm3 / 1000.0, 4),
            "size_mm": [round(v, 3) for v in self.size_mm],
            "problems": self.problems,
            "warnings": self.warnings,
        }


def verify_file(path: Path, expect_one_piece: bool = True) -> list[MeshReport]:
    """Validate one STL or 3MF. A 3MF may hold several objects."""
    suffix = path.suffix.lower()
    if suffix == ".stl":
        meshes = [(path.stem, _read_stl(path))]
    elif suffix == ".3mf":
        meshes = _read_3mf(path)
    else:
        raise ValueError(f"not a mesh file: {path}")
    return [
        _report(path, name, corners, expect_one_piece) for name, corners in meshes
    ]


def verify_directory(directory: Path, expect_one_piece: bool = True,
                     check_manifest: bool = True) -> list[MeshReport]:
    """Validate every mesh under a directory, newest run layout or not."""
    reports: list[MeshReport] = []
    for path in sorted(directory.rglob("*")):
        if path.suffix.lower() in (".stl", ".3mf"):
            reports.extend(verify_file(path, expect_one_piece))
    if check_manifest:
        for manifest in sorted(directory.rglob("manifest.json")):
            _cross_check_manifest(manifest, reports)
    return reports


# ---------------------------------------------------------------------------
# readers
# ---------------------------------------------------------------------------


def _read_stl(path: Path) -> np.ndarray:
    data = path.read_bytes()
    if len(data) < 84:
        raise ValueError(f"{path.name}: too short to be an STL")
    if data[:6].lower() == b"solid " and b"facet" in data[:512]:
        raise ValueError(f"{path.name}: ASCII STL, expected binary")

    declared = struct.unpack("<I", data[80:84])[0]
    expected = 84 + 50 * declared
    if len(data) != expected:
        raise ValueError(
            f"{path.name}: header declares {declared} triangles, which needs "
            f"{expected} bytes, but the file is {len(data)}. Truncated or "
            "corrupt."
        )
    record = np.frombuffer(data, dtype=_STL_RECORD, count=declared, offset=84)
    return np.asarray(record["v"], dtype=np.float64)


def _read_3mf(path: Path) -> list[tuple[str, np.ndarray]]:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        for required in ("[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model"):
            if required not in names:
                raise ValueError(f"{path.name}: 3MF is missing {required}")
        model = ElementTree.fromstring(archive.read("3D/3dmodel.model"))

    if model.get("unit") != "millimeter":
        raise ValueError(
            f"{path.name}: declares unit {model.get('unit')!r}; every generator "
            "here works in millimetres and must say so in the file."
        )

    out = []
    for index, obj in enumerate(model.findall(".//c:object", _CORE_NS), start=1):
        vertices = np.array(
            [
                (float(v.get("x")), float(v.get("y")), float(v.get("z")))
                for v in obj.findall(".//c:vertex", _CORE_NS)
            ],
            dtype=np.float64,
        ).reshape(-1, 3)
        triangles = np.array(
            [
                (int(t.get("v1")), int(t.get("v2")), int(t.get("v3")))
                for t in obj.findall(".//c:triangle", _CORE_NS)
            ],
            dtype=np.int64,
        ).reshape(-1, 3)
        if len(triangles) == 0:
            raise ValueError(f"{path.name}: object {index} has no triangles")
        if triangles.max() >= len(vertices):
            raise ValueError(
                f"{path.name}: object {index} indexes vertex "
                f"{triangles.max()} but only supplies {len(vertices)}"
            )
        name = obj.get("name") or f"object-{index}"
        out.append((f"{path.name}:{name}", vertices[triangles]))
    if not out:
        raise ValueError(f"{path.name}: 3MF contains no objects")
    return out


# ---------------------------------------------------------------------------
# topology
# ---------------------------------------------------------------------------


def _report(path: Path, name: str, corners: np.ndarray,
            expect_one_piece: bool) -> MeshReport:
    report = MeshReport(path=path, name=name, triangles=len(corners))
    if report.triangles == 0:
        report.problems.append("no triangles")
        return report

    flat = corners.reshape(-1, 3)
    finite = np.isfinite(flat).all(axis=1)
    report.non_finite_vertices = int((~finite).sum())
    if report.non_finite_vertices:
        report.problems.append(
            f"{report.non_finite_vertices} vertices are NaN or infinite"
        )
        return report

    # Weld coincident corners onto a fixed grid, the way a slicer would.
    keys = np.round(flat / WELD_GRID_MM).astype(np.int64)
    _, first, inverse = np.unique(keys, axis=0, return_index=True,
                                  return_inverse=True)
    faces = inverse.reshape(-1, 3)
    report.vertices = int(faces.max()) + 1
    report.size_mm = tuple(float(v) for v in (flat.max(axis=0) - flat.min(axis=0)))

    degenerate = (
        (faces[:, 0] == faces[:, 1])
        | (faces[:, 1] == faces[:, 2])
        | (faces[:, 2] == faces[:, 0])
    )
    report.degenerate_triangles = int(degenerate.sum())
    faces = faces[~degenerate]
    if len(faces) == 0:
        report.problems.append("every triangle is degenerate")
        return report

    # Volume from the unwelded coordinates, by the divergence theorem.
    a, b, c = corners[:, 0], corners[:, 1], corners[:, 2]
    report.volume_mm3 = float(np.einsum("ij,ij->", a, np.cross(b, c)) / 6.0)

    # Slivers with three distinct but collinear corners survive the weld, so
    # measure area as well as counting repeated indices.
    areas = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    report.degenerate_triangles = max(
        report.degenerate_triangles, int((areas <= 1e-9).sum())
    )

    directed = np.concatenate(
        [faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]
    )
    low = directed.min(axis=1)
    high = directed.max(axis=1)
    # +1 when the edge runs low->high, -1 the other way. A closed, consistently
    # wound surface uses each edge exactly twice, once in each direction, so
    # every edge's uses must number two and its signs must cancel.
    sign = np.where(directed[:, 0] < directed[:, 1], 1, -1)
    edge_key = low * (report.vertices + 1) + high
    unique_edges, edge_index = np.unique(edge_key, return_inverse=True)
    uses = np.bincount(edge_index, minlength=len(unique_edges))
    winding = np.bincount(edge_index, weights=sign, minlength=len(unique_edges))

    report.edges = len(unique_edges)
    report.boundary_edges = int((uses < 2).sum())
    report.overused_edges = int((uses > 2).sum())
    report.flipped_edges = int(((uses == 2) & (winding != 0)).sum())
    report.components = _count_components(faces, report.vertices)
    euler = report.vertices - report.edges + len(faces)
    report.genus = report.components - euler // 2

    if report.boundary_edges:
        report.problems.append(
            f"not watertight: {report.boundary_edges} edges belong to only one "
            "triangle, so the surface has a hole"
        )
    if report.overused_edges:
        report.problems.append(
            f"not manifold: {report.overused_edges} edges are shared by more "
            "than two triangles"
        )
    if report.flipped_edges:
        report.problems.append(
            f"inconsistent winding on {report.flipped_edges} edges: some "
            "triangles face inward"
        )
    if report.degenerate_triangles:
        # A zero-area triangle is untidy, not broken: the surface is still
        # closed and every slicer skips them. Booleans leave a few wherever
        # two coplanar faces meet, so this is reported, not failed on.
        report.warnings.append(
            f"{report.degenerate_triangles} zero-area triangles "
            f"({report.degenerate_triangles / max(report.triangles, 1):.1%} "
            "of the mesh)"
        )
    if report.volume_mm3 <= 0:
        report.problems.append(
            f"volume is {report.volume_mm3:.3f} mm3; the surface is inside out"
        )
    if expect_one_piece and report.components != 1:
        report.problems.append(
            f"{report.components} disconnected pieces; this model is meant to "
            "come off the bed in one piece"
        )
    return report


def _count_components(faces: np.ndarray, vertex_count: int) -> int:
    """Union-find over the welded vertices."""
    parent = np.arange(vertex_count, dtype=np.int64)

    def find(node: int) -> int:
        root = node
        while parent[root] != root:
            root = parent[root]
        while parent[node] != root:      # path compression
            parent[node], node = root, parent[node]
        return root

    for tri in faces:
        first = find(int(tri[0]))
        for other in tri[1:]:
            second = find(int(other))
            if first != second:
                parent[second] = first
    used = np.unique(faces)
    return len({find(int(v)) for v in used})


def _cross_check_manifest(manifest_path: Path,
                          reports: list[MeshReport]) -> None:
    """Confirm the manifest describes the files sitting next to it."""
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{manifest_path}: unreadable manifest ({exc})") from None

    directory = manifest_path.parent
    local = {r.path.stem: r for r in reports if r.path.parent == directory
             and r.path.suffix.lower() == ".stl"}
    for part in manifest.get("parts", []):
        report = local.get(part["name"])
        if report is None:
            continue
        claimed = float(part["volume_cm3"]) * 1000.0
        actual = report.volume_mm3
        if claimed > 0 and abs(actual - claimed) / claimed > 0.01:
            report.problems.append(
                f"manifest claims {claimed / 1000:.2f} cm3 but the file "
                f"measures {actual / 1000:.2f} cm3"
            )
        for axis, claimed_mm, actual_mm in zip(
            "XYZ", part["size_mm"], report.size_mm
        ):
            if abs(actual_mm - claimed_mm) > 0.05:
                report.problems.append(
                    f"manifest claims {axis}={claimed_mm:.2f} mm but the file "
                    f"measures {actual_mm:.2f} mm"
                )
