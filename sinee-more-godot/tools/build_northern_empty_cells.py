"""A5 v110: nine upright, distinct LIVE Northern Sea rune-circle cells.

Use ONLY two genuinely empty cells of the exact user-approved 16:9 art.
Perspective rectification and conservative centered zooms preserve the upright
compass/rune orientation; no occupied screenshot pieces, ranks, or UI are baked.
The approved reference is an immutable input, never a generated output.
"""
from pathlib import Path
import hashlib
import json
import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'assets/a5_northern_ranked/07_northern_sea_canon_source.png'
DEST = ROOT / 'assets/a5_reference_cells/north'
SHA = '3289a2a7eeed5fca9426e8e3af515a504a1658e0e450327dd22e26f44e664775'
SIZE = 192
# TL, TR, BR, BL in the original accepted 1672x941 art.
# The remaining seven cells contain a live rune stone in the concept image.
DONORS = {
    'top_middle': [[709,246],[973,245],[989,375],[698,376]],
    'bottom_left': [[386,534],[691,533],[677,719],[323,719]],
}
# The donor rune compass is intentionally NEVER rotated. The distinct centered
# zooms keep the stone center readable and avoid copying snow/other cells.
ASSIGN = [
    ('top_middle', 0.89), ('top_middle', 0.96), ('top_middle', 0.86),
    ('bottom_left', 0.93), ('top_middle', 0.99), ('bottom_left', 0.87),
    ('bottom_left', 0.97), ('bottom_left', 0.90), ('top_middle', 0.93),
]

def extract(source: np.ndarray, donor: str, inset: float) -> np.ndarray:
    assert donor in DONORS and 0.80 <= inset <= 1.0
    quad = np.float32(DONORS[donor])
    center = quad.mean(axis=0)
    quad = center + (quad - center) * inset
    output = np.float32([[0,0],[SIZE-1,0],[SIZE-1,SIZE-1],[0,SIZE-1]])
    transform = cv2.getPerspectiveTransform(quad, output)
    return cv2.warpPerspective(source, transform, (SIZE,SIZE),
                               flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_REPLICATE)

def build() -> list[dict]:
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == SHA, 'Northern canon changed'
    with Image.open(SOURCE) as img:
        assert img.size == (1672, 941)
        source = np.asarray(img.convert('RGB'))
    DEST.mkdir(parents=True, exist_ok=True)
    records = []
    contact = Image.new('RGB', (SIZE*3, SIZE*3))
    for index, (name, inset) in enumerate(ASSIGN):
        tile = Image.fromarray(extract(source, name, inset), 'RGB')
        target = DEST / f'cell_{index:02d}.png'
        tile.save(target, optimize=False)
        contact.paste(tile, ((index%3)*SIZE, (index//3)*SIZE))
        records.append({
            'file': target.name, 'cell': index,
            'empty_source_cell': name, 'inset': inset,
            'rotation_ccw_quarters': 0,
            'occupied_reference_cell_baked': False,
            'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
        })
    manifest = {
        'version': 'A5-v110', 'world': 'northern_sea',
        'source_file': SOURCE.name, 'source_sha256': SHA,
        'source_size': [1672, 941],
        'purpose': 'LIVE empty-board cell textures; no figures, ranks, UI or occupancy',
        'donors': DONORS, 'output_size': [SIZE,SIZE], 'assets': records,
    }
    (DEST/'asset_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    contact.save(DEST/'northern_empty_cells_preview.jpg', quality=94)
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == SHA
    return records

if __name__ == '__main__':
    print('A5_NORTHERN_EMPTY_CANONICAL_CELLS_PASS', len(build()))
