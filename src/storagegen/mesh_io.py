"""Mesh export: binary STL and 3MF.

Both writers are hand-rolled on purpose.  3MF is the format that actually
carries what a customer needs -- millimetre units declared in the file, and
several *named* objects arranged on one plate -- and the general-purpose
libraries either skip it or flatten the object names away.
"""

from __future__ import annotations

import struct
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import manifold3d
import numpy as np

from .geom import Solid, bounds, size_of

# Fixed zip timestamp so two runs with identical options produce identical
# bytes.  Customers re-download; identical inputs should not look like a change.
_ZIP_DATE = (2024, 1, 1, 0, 0, 0)

_CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>
"""

_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
"""


@dataclass
class Part:
    """One printable object: a solid plus the name it should carry."""

    name: str
    solid: Solid
    note: str = ""
    copies: int = 1

    def mesh(self) -> tuple[np.ndarray, np.ndarray]:
        raw = self.solid.to_mesh()
        verts = np.asarray(raw.vert_properties, dtype=np.float64)[:, :3]
        tris = np.asarray(raw.tri_verts, dtype=np.uint32)
        return verts, tris

    @property
    def size(self) -> tuple[float, float, float]:
        return size_of(self.solid)

    @property
    def volume_mm3(self) -> float:
        return float(self.solid.volume())

    @property
    def triangle_count(self) -> int:
        return int(self.solid.num_tri())

    def is_manifold(self) -> bool:
        """Confirm the solid really is closed and non-degenerate.

        `status()` returns an `Error` enum, not an int, so it has to be
        compared against `Error.NoError`; comparing it to 0 is quietly always
        false and turns this check into a rubber stamp that always fails.
        """
        return (
            not self.solid.is_empty()
            and self.solid.status() == manifold3d.Error.NoError
        )


@dataclass
class PartSet:
    """Everything one generator run produced."""

    parts: list[Part] = field(default_factory=list)

    def add(self, name: str, solid: Solid, note: str = "", copies: int = 1) -> Part:
        part = Part(name=name, solid=solid, note=note, copies=copies)
        self.parts.append(part)
        return part

    def __iter__(self):
        return iter(self.parts)

    def __len__(self):
        return len(self.parts)


def write_stl(path: Path, part: Part) -> Path:
    """Binary STL for a single part, dropped onto Z=0 at the origin."""
    verts, tris = part.mesh()
    verts = _drop_to_origin(verts)
    corners = verts[tris]

    normals = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = np.divide(normals, lengths, out=np.zeros_like(normals), where=lengths > 0)

    record = np.zeros(
        len(tris),
        dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")]),
    )
    record["n"] = normals
    record["v"] = corners

    header = f"{part.name} - storage-generator".encode("ascii", "replace")[:80]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(header.ljust(80, b"\0"))
        handle.write(struct.pack("<I", len(tris)))
        handle.write(record.tobytes())
    return path


def write_3mf(path: Path, parts: Sequence[Part], metadata: dict[str, str],
              gap: float = 6.0) -> Path:
    """One 3MF holding every part, laid out along X with `gap` between them."""
    printable = [p for p in parts if not p.solid.is_empty()]
    if not printable:
        raise ValueError("nothing to export: every part is empty")

    objects: list[str] = []
    items: list[str] = []
    cursor = 0.0
    for index, part in enumerate(printable, start=1):
        verts, tris = part.mesh()
        verts = _drop_to_origin(verts)
        objects.append(_object_xml(index, part.name, verts, tris))
        items.append(
            f'  <item objectid="{index}" transform="1 0 0 0 1 0 0 0 1 '
            f'{_num(cursor)} 0 0" />'
        )
        cursor += (verts[:, 0].max() - verts[:, 0].min()) + gap

    meta_xml = "\n".join(
        f' <metadata name="{_escape(k)}">{_escape(v)}</metadata>'
        for k, v in metadata.items()
        if v
    )
    model = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<model unit="millimeter" xml:lang="en-US" xmlns="{_CORE_NS}">\n'
        f"{meta_xml}\n"
        " <resources>\n"
        + "\n".join(objects)
        + "\n </resources>\n"
        " <build>\n"
        + "\n".join(items)
        + "\n </build>\n"
        "</model>\n"
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in (
            ("[Content_Types].xml", _CONTENT_TYPES),
            ("_rels/.rels", _RELS),
            ("3D/3dmodel.model", model),
        ):
            info = zipfile.ZipInfo(name, date_time=_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, payload)
    return path


def _object_xml(index: int, name: str, verts: np.ndarray, tris: np.ndarray) -> str:
    vertex_xml = "".join(
        f'<vertex x="{_num(x)}" y="{_num(y)}" z="{_num(z)}"/>' for x, y, z in verts
    )
    triangle_xml = "".join(
        f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in tris
    )
    return (
        f'  <object id="{index}" type="model" name="{_escape(name)}">\n'
        f"   <mesh>\n"
        f"    <vertices>{vertex_xml}</vertices>\n"
        f"    <triangles>{triangle_xml}</triangles>\n"
        f"   </mesh>\n"
        f"  </object>"
    )


def _drop_to_origin(verts: np.ndarray) -> np.ndarray:
    """Move a part so its bounding box starts at the origin and sits on Z=0."""
    return verts - verts.min(axis=0)


def _num(value: float) -> str:
    text = f"{float(value):.4f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
