"""A small software renderer, so every run ships a picture of what it made.

Listings need images, and a generated model nobody looked at is a model
nobody checked.  This is a plain z-buffered triangle rasteriser with flat
shading: no GPU, no display, no extra dependency, and PNG written by hand
through zlib.
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path
from typing import Sequence

import numpy as np

from .mesh_io import Part

BACKGROUND = (250, 250, 249)
SURFACE = (232, 122, 42)         # the printed part
CONTEXT = (150, 158, 168)        # things the part holds, drawn cooler and duller

Layer = tuple[np.ndarray, np.ndarray, tuple[int, int, int]]


DEFAULT_VIEWS: Sequence[tuple[str, float, float]] = (
    ("three-quarter", 38.0, 26.0),
    ("front", 0.0, 4.0),
    ("side", 90.0, 4.0),
)


def render_views(path: Path, part: Part, size: int = 620,
                 views: Sequence[tuple[str, float, float]] = DEFAULT_VIEWS,
                 supersample: int = 2) -> Path:
    """Render several viewpoints of one part into a contact sheet."""
    return render_scene(path, [part], size=size, views=views,
                        supersample=supersample)


def render_scene(path: Path, parts: Sequence[Part],
                 context: Sequence[Part] = (), size: int = 620,
                 views: Sequence[tuple[str, float, float]] = DEFAULT_VIEWS,
                 supersample: int = 2) -> Path:
    """Render the printed parts, optionally with the things they hold.

    Context parts -- the bins a rack carries -- are drawn in a cooler, duller
    colour so a glance separates what you print from what you already own.
    """
    tiles = [
        scene_pixels(parts, context, size, azimuth, elevation, supersample)
        for _, azimuth, elevation in views
    ]
    _write_png(path, np.concatenate(tiles, axis=1))
    return path


def scene_pixels(parts: Sequence[Part], context: Sequence[Part] = (),
                 size: int = 620, azimuth: float = 38.0,
                 elevation: float = 26.0, supersample: int = 2) -> np.ndarray:
    """One rendered view as a pixel array, for callers composing their own sheet."""
    layers = _layers(parts) + _layers(context, CONTEXT)
    pixels = _render(layers, size * supersample, azimuth, elevation)
    return _downsample(pixels, supersample) if supersample > 1 else pixels


def write_sheet(path: Path, rows: Sequence[Sequence[np.ndarray]]) -> Path:
    """Stack rendered views into one contact sheet."""
    _write_png(path, np.concatenate(
        [np.concatenate(row, axis=1) for row in rows], axis=0))
    return path


def _layers(parts: Sequence[Part],
            colour: tuple[int, int, int] = SURFACE) -> list[Layer]:
    out: list[Layer] = []
    for part in parts:
        verts, tris = part.mesh()
        if len(tris):
            out.append((verts, tris, colour))
    return out


def _render(layers: Sequence[Layer], size: int,
            azimuth: float, elevation: float) -> np.ndarray:
    if not layers:
        raise ValueError("nothing to render")
    camera = _basis(azimuth, elevation)

    everything = np.concatenate([verts for verts, _, _ in layers]) @ camera.T
    screen = everything[:, :2]
    lo, hi = screen.min(axis=0), screen.max(axis=0)
    extent = max((hi - lo).max(), 1e-6)
    scale = (size * 0.86) / extent
    offset = (size / 2.0) - ((lo + hi) / 2.0) * scale

    image = np.zeros((size, size, 3), dtype=np.float32)
    image[:] = np.array(BACKGROUND, dtype=np.float32) / 255.0
    zbuffer = np.full((size, size), -np.inf, dtype=np.float32)
    light = _normalise(camera[2] * 0.75 + camera[1] * 0.5 + camera[0] * 0.3)

    for verts, tris, colour in layers:
        view = verts @ camera.T                  # x right, y up, z toward camera
        px = view[:, :2] * scale + offset
        px[:, 1] = size - px[:, 1]               # image rows run downward
        depth = view[:, 2]

        corners = np.stack([px[tris[:, i]] for i in range(3)], axis=1)
        z_corners = np.stack([depth[tris[:, i]] for i in range(3)], axis=1)

        world = np.stack([verts[tris[:, i]] for i in range(3)], axis=1)
        normals = np.cross(world[:, 1] - world[:, 0], world[:, 2] - world[:, 0])
        lengths = np.linalg.norm(normals, axis=1, keepdims=True)
        normals = np.divide(normals, lengths, out=np.zeros_like(normals),
                            where=lengths > 0)
        shade = 0.30 + 0.70 * np.clip(normals @ light, 0.0, 1.0)
        base = np.array(colour, dtype=np.float32) / 255.0

        # Signed screen-space area picks out the front faces. Written out
        # rather than np.cross because a 2-D cross product is deprecated.
        edge1 = corners[:, 1] - corners[:, 0]
        edge2 = corners[:, 2] - corners[:, 0]
        facing = edge1[:, 0] * edge2[:, 1] - edge1[:, 1] * edge2[:, 0]
        for index in np.nonzero(facing < 0)[0]:  # image rows run downward
            _raster(image, zbuffer, corners[index], z_corners[index],
                    base * shade[index])
    return np.clip(image * 255.0, 0, 255).astype(np.uint8)


def _raster(image: np.ndarray, zbuffer: np.ndarray, tri: np.ndarray,
            z: np.ndarray, colour: np.ndarray) -> None:
    size = image.shape[0]
    x_min = max(int(math.floor(tri[:, 0].min())), 0)
    x_max = min(int(math.ceil(tri[:, 0].max())) + 1, size)
    y_min = max(int(math.floor(tri[:, 1].min())), 0)
    y_max = min(int(math.ceil(tri[:, 1].max())) + 1, size)
    if x_min >= x_max or y_min >= y_max:
        return

    (x0, y0), (x1, y1), (x2, y2) = tri
    area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
    if abs(area) < 1e-9:
        return

    ys, xs = np.mgrid[y_min:y_max, x_min:x_max]
    xs = xs + 0.5
    ys = ys + 0.5
    w0 = ((x1 - x0) * (ys - y0) - (xs - x0) * (y1 - y0)) / area
    w1 = ((xs - x0) * (y2 - y0) - (x2 - x0) * (ys - y0)) / area
    inside = (w0 >= 0) & (w1 >= 0) & (w0 + w1 <= 1)
    if not inside.any():
        return

    depth = z[0] + w1 * (z[1] - z[0]) + w0 * (z[2] - z[0])
    window = zbuffer[y_min:y_max, x_min:x_max]
    visible = inside & (depth > window)
    if not visible.any():
        return
    window[visible] = depth[visible]
    image[y_min:y_max, x_min:x_max][visible] = colour


def _basis(azimuth_deg: float, elevation_deg: float) -> np.ndarray:
    """Rows are the camera's right, up and forward axes in model space."""
    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)
    forward = np.array([
        math.sin(az) * math.cos(el),
        -math.cos(az) * math.cos(el),
        math.sin(el),
    ])
    forward = _normalise(forward)
    right = _normalise(np.cross(np.array([0.0, 0.0, 1.0]), forward))
    up = np.cross(forward, right)
    return np.stack([right, up, forward])


def _normalise(vector: np.ndarray) -> np.ndarray:
    length = np.linalg.norm(vector)
    return vector / length if length else vector


def _downsample(pixels: np.ndarray, factor: int) -> np.ndarray:
    height, width, channels = pixels.shape
    trimmed = pixels[: height // factor * factor, : width // factor * factor]
    return (
        trimmed.reshape(height // factor, factor, width // factor, factor, channels)
        .mean(axis=(1, 3))
        .astype(np.uint8)
    )


def _write_png(path: Path, pixels: np.ndarray) -> Path:
    height, width, _ = pixels.shape
    raw = b"".join(
        b"\x00" + pixels[row].tobytes() for row in range(height)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n")
        handle.write(_chunk(b"IHDR",
                            struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)))
        handle.write(_chunk(b"IDAT", zlib.compress(raw, 9)))
        handle.write(_chunk(b"IEND", b""))
    return path


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + tag
        + payload
        + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
    )
