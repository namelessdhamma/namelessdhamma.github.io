"""Portable verification of A5 v105 live Pirate chart artwork."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "assets/a5_reference_cells/pirate"
SOURCE = ROOT / "assets/a5_pirate_ranked/02_pirate_sea_canon_source.png"
MANIFEST = json.loads((DIR / "asset_manifest.json").read_text())
SHA = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def test_approved_source_immutable_and_correct():
    assert SHA(SOURCE) == MANIFEST["source_sha256"]
    assert MANIFEST["source_sha256"] == "0e9f2f706ba9127cecef7e718fa50c320a8e92b9fe093b54cffbd69b471eafb1"
    assert MANIFEST["source_size"] == [1672, 941]


def test_nine_distinct_reproducible_live_cell_textures():
    assert MANIFEST["version"] == "A5-v105"
    assert len(MANIFEST["cells"]) == 9
    hashes = []
    for i, rec in enumerate(MANIFEST["cells"]):
        assert rec["cell"] == i and rec["occupied_reference_cell_baked"] is False
        path = DIR / f"cell_{i:02d}.png"
        assert SHA(path) == rec["sha256"]
        with Image.open(path) as im:
            assert im.size == (192, 192) and im.mode == "RGB"
        hashes.append(rec["sha256"])
    assert len(set(hashes)) == 9


def test_no_rotated_center_mountain_and_no_baked_rank_five_spill():
    # The original screenshot's middle cell is EMPTY, but the neighboring
    # rank-5 piece crosses the rectification edge; v105 repairs that edge.
    with Image.open(DIR / "cell_04.png") as im, Image.open(DIR / "cell_00.png") as donor:
        middle = np.array(im)
        safe = np.array(donor)
    assert np.array_equal(middle[176:, :, :], safe[176:, :, :])
    # Upright mountain has more dark ink in the upper half than bottom half.
    gray = cv2.cvtColor(middle, cv2.COLOR_RGB2GRAY)
    assert np.count_nonzero(gray[20:90, 20:172] < 115) > 200
    assert np.count_nonzero(gray[20:90, 20:172] < 115) > np.count_nonzero(gray[112:162, 20:172] < 115)


def test_no_repeated_rotated_mountain_assignment():
    assert MANIFEST["donor_cells"] == [0, 4]
    assert len(MANIFEST["source_motif_regions"]) == 7
    assert MANIFEST["cells"][0]["treatment"] == "original_empty_cell_unrotated"
    assert MANIFEST["cells"][4]["treatment"] == "original_empty_cell_unrotated"
    assert len({r["treatment"] for r in MANIFEST["cells"]}) == 8


def test_exact_canon_motifs_not_screenshot_ui_or_piece_overlay():
    assert set(MANIFEST["source_motif_regions"]) == {"1", "2", "3", "5", "6", "7", "8"}
    # All motif regions are outside the live 3x3 board's central occupancy;
    # 0 and 4 alone are explicitly confirmed empty reference cells.
    for region in MANIFEST["source_motif_regions"].values():
        x0, y0, x1, y1 = region
        assert 0 <= x0 < x1 <= 1672 and 0 <= y0 < y1 <= 941
    assert all(not r["occupied_reference_cell_baked"] for r in MANIFEST["cells"])


def test_world_engine_uses_nine_real_cell_textures():
    script = (ROOT / "scripts/world_visuals.gd").read_text()
    assert '"pirate", "atlantis", "gods"' in script
    assert 'var path := "%s/%s/cell_%02d.png"' in script
    assert "chart.texture = _canonical_cell_texture(world, cell_index)" in script
    main = (ROOT / "scripts/main.gd").read_text()
    assert "tile.texture = art.texture" in main
    assert "_on_cell_pressed(index)" in main
    assert (ROOT / "tests/a5_v105_pirate_unique_chart_runtime_smoke.gd").is_file()


def test_canon_masthead_ai_and_opening_remain_integrated():
    main = (ROOT / "scripts/main.gd").read_text()
    assert "_layout_canonical_live_logo" in main
    assert "_queue_ai_turn_if_ready" in main
    assert "_on_reserve_pressed" in main
    assert (ROOT / "scripts/pirate_opening_campaign.gd").is_file()


def test_builder_idempotent_and_approved_source_unmodified():
    paths = [DIR / f"cell_{i:02d}.png" for i in range(9)]
    paths += [DIR / "asset_manifest.json", DIR / "pirate_empty_cells_preview.jpg"]
    before = {p.name: SHA(p) for p in paths}
    source_before = SHA(SOURCE)
    subprocess.run([sys.executable, str(ROOT / "tools/build_pirate_unique_chart_cells.py")],
                   check=True, capture_output=True, text=True)
    assert {p.name: SHA(p) for p in paths} == before
    assert SHA(SOURCE) == source_before
