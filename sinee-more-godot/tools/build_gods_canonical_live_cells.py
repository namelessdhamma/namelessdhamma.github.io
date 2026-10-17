"""A5 v106: reconstruct the nine LIVE Gods of the Deep board cells.

The three reference cells that are genuinely unoccupied (spiral at top middle,
trident at middle right, eye at bottom left) are extracted from the exact
SHA-locked accepted PNG. Six occupied positions borrow *only* those empty
source cells; no creature, rank, reserve, or UI is baked into live art.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'assets/a5_gods_ranked/04_gods_of_the_deep_canon_source.png'
OUTPUT = ROOT / 'assets/a5_reference_cells/gods'
EXPECTED_SHA = '10ddb91c1ddf75d6faaec496600419ae9483a02453f38e81f44bbc7ee1903f4d'
CORNERS = np.float32([[385, 278], [1280, 279], [1410, 730], [265, 730]])
SIZE = 192
# Source occupancy: [occupied, spiral, occupied, occupied, occupied,
# trident, eye, occupied, occupied]. NEVER sample an occupied source cell.
EMPTY_SOURCE_CELLS = {1: 'spiral', 5: 'trident', 6: 'eye'}
# Per-cell donor/inset. Distinct insets retain source-derived stone texture
# without duplicating or rotating a carved symbol upside-down.
CELL_DESIGN = [
    (5, .76), (1, .82), (6, .78),
    (6, .80), (1, .79), (5, .82),
    (6, .82), (5, .77), (1, .77),
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quad(index: int) -> np.ndarray:
    col, row = index % 3, index // 3
    def point(u: float, v: float) -> np.ndarray:
        a, b, c, d = CORNERS
        return (1 - v) * ((1 - u) * a + u * b) + v * ((1 - u) * d + u * c)
    return np.float32([point(col/3, row/3), point((col+1)/3, row/3),
                       point((col+1)/3, (row+1)/3), point(col/3, (row+1)/3)])


def extract(pixels: np.ndarray, index: int, inset: float) -> np.ndarray:
    q = quad(index)
    q = q.mean(axis=0) + (q - q.mean(axis=0)) * inset
    target = np.float32([[0, 0], [SIZE-1, 0], [SIZE-1, SIZE-1], [0, SIZE-1]])
    transform = cv2.getPerspectiveTransform(q, target)
    return cv2.warpPerspective(pixels, transform, (SIZE, SIZE),
                               flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_REPLICATE)


def clean_spiral_spill(spiral: np.ndarray, clean_trident: np.ndarray) -> np.ndarray:
    """Replace lower-row intruding jellyfish from adjacent occupied cell.

    The source spiral is intact in its upper 60%, but the adjacent live rank
    crosses the bottom edge of the screenshot's empty top-middle square.
    Only the lower border is restored from the other *empty* source cell.
    """
    out = spiral.astype(np.float32).copy()
    donor = clean_trident.astype(np.float32)
    for y in range(122, SIZE):
        alpha = min(1.0, max(0.0, (y - 122) / 22.0))
        out[y] = (1.0 - alpha) * out[y] + alpha * donor[y]
    return np.uint8(np.clip(np.rint(out), 0, 255))


def build() -> list[dict]:
    assert sha(SOURCE) == EXPECTED_SHA, 'Accepted Gods PNG changed'
    with Image.open(SOURCE) as image:
        assert image.size == (1672, 941)
        pixels = np.array(image.convert('RGB'))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    original_spiral = extract(pixels, 1, CELL_DESIGN[1][1])
    trident_for_repair = extract(pixels, 5, CELL_DESIGN[5][1])
    clean_spiral = clean_spiral_spill(original_spiral, trident_for_repair)
    contact = Image.new('RGB', (SIZE * 3, SIZE * 3))
    records: list[dict] = []
    for index, (donor, inset) in enumerate(CELL_DESIGN):
        image = clean_spiral if index == 1 else extract(pixels, donor, inset)
        # Keep the three accepted empty motifs at their ACTUAL reference
        # positions; all six occupied slots use only unoccupied donors.
        path = OUTPUT / f'cell_{index:02d}.png'
        Image.fromarray(image, 'RGB').save(path, optimize=False)
        contact.paste(Image.fromarray(image, 'RGB'), ((index % 3) * SIZE, (index // 3) * SIZE))
        records.append({
            'cell': index, 'file': path.name, 'sha256': sha(path),
            'donor_empty_cell': donor, 'donor_symbol': EMPTY_SOURCE_CELLS[donor],
            'inset': inset, 'turns_ccw': 0,
            'reference_cell_is_empty': index in EMPTY_SOURCE_CELLS,
            'reference_spill_repaired': index == 1,
            'occupied_reference_cell_baked': False,
        })
    assert len({r['sha256'] for r in records}) == 9
    contact.save(OUTPUT / 'gods_empty_cells_preview.jpg', quality=94)
    manifest = {
        'version': 'A5-v106', 'world': 'gods_of_the_deep',
        'source_file': SOURCE.name, 'source_sha256': EXPECTED_SHA,
        'source_size': [1672, 941], 'source_board_corners': CORNERS.astype(int).tolist(),
        'donor_cells': [1, 5, 6], 'canonical_empty_motifs':
        {'1': 'spiral', '5': 'trident', '6': 'eye'},
        'output_size': [SIZE, SIZE],
        'use': 'Nine live Godot cells; pieces/ranks/occupancy/AI are dynamic',
        'cells': records,
    }
    (OUTPUT / 'asset_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    assert sha(SOURCE) == EXPECTED_SHA
    return records


if __name__ == '__main__':
    print('A5_V106_GODS_LIVE_CELLS', len(build()))
