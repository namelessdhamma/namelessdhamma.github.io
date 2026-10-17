"""A5 v105: nine distinct, LIVE Pirate Sea parchment cells from approved art.

The accepted reference is an immutable input. Its two genuinely empty cells
(0 and 4) provide real board framing; other cells reuse only cartographic ink
motifs from non-gameplay parchment. No baked ranks, figures or UI are copied.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/a5_pirate_ranked/02_pirate_sea_canon_source.png"
OUTPUT = ROOT / "assets/a5_reference_cells/pirate"
EXPECTED_SOURCE_SHA256 = "0e9f2f706ba9127cecef7e718fa50c320a8e92b9fe093b54cffbd69b471eafb1"
SIZE = 192
BOARD_CORNERS = np.float32([[500, 254], [1190, 254], [1300, 706], [387, 706]])
# Each selected motif is from the APPROVED parchment illustration outside the
# playable grid or from an already empty cell. Never sample the occupied cells.
# Coordinates are exact source pixels, not generated reference replacements.
MOTIFS = {
    1: (505, 267, 675, 360, "northern_mountains"),
    2: (1235, 323, 1382, 435, "compass_rose"),
    3: (318, 311, 424, 360, "skull_chart_marker"),
    5: (1280, 448, 1452, 604, "merchant_sailing_ship"),
    6: (257, 409, 408, 543, "palm_island"),
    7: (276, 585, 408, 705, "river_treasure_route"),
    8: (1315, 612, 1480, 718, "southern_mountain"),
}

def _cell_quad(index: int) -> np.ndarray:
    c, r = index % 3, index // 3
    def point(u: float, v: float) -> np.ndarray:
        a, b, d, e = BOARD_CORNERS
        return (1 - v) * ((1 - u) * a + u * b) + v * ((1 - u) * e + u * d)
    return np.float32([point(c / 3, r / 3), point((c + 1) / 3, r / 3),
                       point((c + 1) / 3, (r + 1) / 3), point(c / 3, (r + 1) / 3)])

def _rectify_empty(source: np.ndarray, index: int) -> Image.Image:
    quad = _cell_quad(index)
    dest = np.float32([[0, 0], [SIZE - 1, 0], [SIZE - 1, SIZE - 1], [0, SIZE - 1]])
    result = cv2.warpPerspective(source, cv2.getPerspectiveTransform(quad, dest),
                                 (SIZE, SIZE), flags=cv2.INTER_CUBIC,
                                 borderMode=cv2.BORDER_REPLICATE)
    return Image.fromarray(result, "RGB")

def _empty_paper(donor: Image.Image) -> Image.Image:
    """Remove only donor's dark mountain ink, keeping its exact source frame."""
    rgb = np.asarray(donor)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    yy, xx = np.indices(gray.shape)
    mask = np.uint8((gray < 115) & (xx > 14) & (xx < 178) &
                    (yy > 14) & (yy < 178)) * 255
    mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    return Image.fromarray(cv2.inpaint(rgb, mask, 4, cv2.INPAINT_TELEA), "RGB")

def _motif(source: Image.Image, rect: tuple[int, int, int, int], max_size: tuple[int, int]) -> Image.Image:
    crop = source.crop(rect)
    rgb = np.asarray(crop, dtype=np.float32)
    # The source parchment is orange; actual cartographic ink is very dark.
    # Threshold the INK, not the screenshot, so no rectangular photo cutout,
    # occupied piece or copied interface can appear in a live cell.
    ink = np.maximum(np.clip((160.0 - rgb[:, :, 0]) * 2.5, 0, 255),
                     np.clip((110.0 - rgb[:, :, 1]) * 3.2, 0, 255))
    ink = np.clip((ink - 52.0) * 255.0 / 203.0, 0, 255)
    h, w = ink.shape
    # Feather the SOURCE crop perimeter; otherwise an exterior chart border
    # can leave a hard rectangular seam inside a gameplay tile.
    margin = min(11.0, min(w, h) / 8.0)
    yy, xx = np.indices((h, w))
    distance = np.minimum.reduce([xx, yy, w - 1 - xx, h - 1 - yy]).astype(float)
    ink *= np.clip(distance / margin, 0, 1)
    alpha = Image.fromarray(np.uint8(np.clip(ink, 0, 255)), "L")
    scale = min(max_size[0] / w, max_size[1] / h)
    new_size = (round(w * scale), round(h * scale))
    alpha = alpha.resize(new_size, Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(0.30))
    stamp = Image.new("RGBA", new_size, (60, 35, 23, 0))
    stamp.putalpha(alpha)
    return stamp

def build() -> list[dict]:
    actual_sha = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    assert actual_sha == EXPECTED_SOURCE_SHA256, "Approved Pirate PNG has changed"
    source = Image.open(SOURCE).convert("RGB")
    assert source.size == (1672, 941)
    pixels = np.asarray(source)
    # Only the two EMPTY source cells may be copied without modification.
    original_empty = {i: _rectify_empty(pixels, i) for i in (0, 4)}
    # Perspective spill from the rank-5 piece in the cell BELOW the genuinely
    # empty center tile crosses its lower 20px. Restore that BORDER only from
    # the other empty source tile; otherwise the live empty center displays a
    # ghost number "5" even when gameplay has no piece there.
    middle = np.asarray(original_empty[4]).copy()
    safe_bottom = np.asarray(original_empty[0])
    for y in range(163, SIZE):
        blend = min(1.0, max(0.0, (y - 163) / 13.0))
        middle[y] = np.uint8(np.round(middle[y] * (1.0 - blend) + safe_bottom[y] * blend))
    original_empty[4] = Image.fromarray(middle, "RGB")
    paper = _empty_paper(original_empty[0])
    OUTPUT.mkdir(parents=True, exist_ok=True)
    contact = Image.new("RGB", (3 * SIZE, 3 * SIZE))
    records: list[dict] = []
    for i in range(9):
        if i in original_empty:
            image = original_empty[i]
            treatment = "original_empty_cell_unrotated"
        else:
            x0, y0, x1, y1, name = MOTIFS[i]
            image_rgba = paper.copy().convert("RGBA")
            max_size = (135, 116) if i != 5 else (140, 121)
            stamp = _motif(source, (x0, y0, x1, y1), max_size)
            x = (SIZE - stamp.width) // 2
            y = (SIZE - stamp.height) // 2
            image_rgba.alpha_composite(stamp, (x, y))
            image = image_rgba.convert("RGB")
            treatment = name
        path = OUTPUT / f"cell_{i:02d}.png"
        image.save(path, optimize=False)
        contact.paste(image, ((i % 3) * SIZE, (i // 3) * SIZE))
        records.append({"cell": i, "file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "treatment": treatment, "donor_empty_cell": 4 if i == 4 else 0,
                        "turns_ccw": 0, "occupied_reference_cell_baked": False})
    assert len({x["sha256"] for x in records}) == 9, "Repeated live Pirate cell texture"
    contact.save(OUTPUT / "pirate_empty_cells_preview.jpg", quality=94)
    manifest = {
        "version": "A5-v105", "world": "pirate_sea", "source_file": SOURCE.name,
        "source_sha256": actual_sha, "source_size": list(source.size),
        "donor_cells": [0, 4], "source_board_corners": BOARD_CORNERS.astype(int).tolist(),
        "output_size": [SIZE, SIZE],
        "use": "Nine distinct LIVE Godot chart cells; occupancy, ranks, AI and touch dynamic",
        "source_motif_regions": {str(k): list(v[:4]) for k, v in MOTIFS.items()},
        "cells": records,
    }
    (OUTPUT / "asset_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == actual_sha
    return records

if __name__ == "__main__":
    print("A5_V105_PIRATE_UNIQUE_LIVE_CHART", len(build()))
