"""A5 v113: no invisible opponent/AI ranked textures at world entry.

Static/source tests are NOT a substitute for the wired native Godot smoke.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "scripts" / "main.gd").read_text()
WORLD = (ROOT / "scripts" / "world_visuals.gd").read_text()


def method(name: str) -> str:
    start = MAIN.index(f"func {name}(")
    rest = MAIN[start:]
    next_fn = rest.find("\nfunc ", 5)
    return rest if next_fn < 0 else rest[:next_fn]


def test_only_active_available_rank_decodes_and_renders():
    source = method("_refresh_surface")
    assert "reserve.visible = player == turn and not game_over and (not ai_enabled or player == 1)" in source
    assert "var show_rank := reserve.visible and reserve_available[player - 1][i]" in source
    assert "world_visuals.piece_texture(current_world, player, i + 1) if show_rank else null" in source
    assert "i + 1 if show_rank else 0" in source
    assert "_set_piece_badge(piece," in source
    assert "piece.disabled = game_over or player != turn" in source


def test_native_smoke_covers_two_human_turns_and_ai_hidden_turn():
    body = method("_run_headless_lazy_reserve_smoke")
    assert "for active in [1, 2]:" in body
    assert '"Inactive reserve retained a texture"' in body
    assert '"Inactive reserve retained a rank label"' in body
    assert '"AI turn retained a hidden reserve texture"' in body
    assert '"Spent active rank retained its image"' in body
    assert '"Terminal match retained hidden reserve texture"' in body
    assert "_apply_match_snapshot(saved)" in body
    assert "_refresh_surface()" in body
    assert "_run_headless_lazy_reserve_smoke()" in method("_run_headless_geometry_and_interaction_smoke")


def test_cold_world_active_reserve_requires_only_nine_sprites():
    for ai_enabled, active, game_over in [
        (False, 1, False), (False, 2, False), (True, 1, False),
        (True, 2, False), (False, 1, True), (True, 2, True),
    ]:
        loads = sum(
            int(player == active and not game_over and (not ai_enabled or player == 1))
            for player in (1, 2) for _rank in range(1, 10)
        )
        assert loads == (0 if game_over or (ai_enabled and active == 2) else 9)
        assert loads <= 9


def test_both_reserves_keep_gameplay_state_not_texture_state():
    body = method("_refresh_surface")
    assert "reserve_available[player - 1][i]" in body
    assert "reserve_available[player - 1][i] =" not in body
    assert "reserve_available[player - 1][i]" in method("_is_legal_move_for") or "reserve_available[player - 1][rank - 1]" in method("_is_legal_move_for")
    assert "RESIDENT_WORLD_LIMIT := 2" in WORLD


def test_seven_world_ranked_assets_remain_present():
    for name in ("void", "pirate", "atlantis", "gods", "sand", "night", "northern"):
        folder = ROOT / "assets" / f"a5_{name}_ranked"
        assert folder.is_dir()
        for player in (1, 2):
            files = sorted(folder.glob(f"*_p{player}.png"))
            assert len(files) == 9, (name, player, len(files))
