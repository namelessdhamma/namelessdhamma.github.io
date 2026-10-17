"""v140: mobile invalid-rank notice and rank-number contrast are real shared UI.

These are source-contract tests; native Godot smoke remains a separate gate.
"""
from pathlib import Path
import pytest

MAIN = (Path(__file__).resolve().parents[1] / "scripts/main.gd").read_text(encoding="utf-8")


def body(name):
    token = f"func {name}("
    assert MAIN.count(token) == 1
    start = MAIN.index(token)
    end = MAIN.find("\nfunc ", start + 1)
    return MAIN[start:end if end >= 0 else None]


def test_mobile_notice_matches_exact_production_rejection():
    rejection = body("_on_reserve_pressed")
    notice = body("_hud_notice_for_event")
    assert '"для ранга %d нет допустимой клетки" % (index + 1)' in rejection
    assert 'event.begins_with("для ранга ") and event.ends_with(" нет допустимой клетки")' in notice
    assert 'return "НЕТ ХОДА"' in notice
    assert 'if notice != "" and not game_over and _use_mobile_menu():' in body("_update_status")
    assert '_hud_notice_text = notice' in body("_update_status")
    assert '_refresh_match_hud()' in body("_update_status")


def test_silhouette_only_dim_no_parent_fade_or_target_change():
    surface = body("_refresh_surface")
    assert 'piece.modulate = Color.WHITE' in surface
    assert 'rank_art := piece.get_node_or_null("RankArt") as TextureRect' in surface
    assert 'rank_art.modulate.a = 0.53 if show_rank and not can_place_rank else 1.0' in surface
    assert 'piece.modulate = Color.WHITE if not show_rank or can_place_rank' not in surface
    assert 'piece.disabled = not can_place_rank' not in surface
    assert 'piece.tooltip_text = "" if not show_rank or can_place_rank' in surface
    assert 'reserve.visible = player == turn' in surface
    assert 'piece.custom_minimum_size =' not in surface


def test_native_smoke_checks_real_number_and_art_nodes():
    smoke = body("_run_headless_unplayable_rank_smoke")
    assert 'for world in range(WorldVisuals.WORLDS.size()):' in smoke
    assert 'low.get_node("RankArt") as TextureRect' in smoke
    assert 'low.get_node("RankNumber") as Label' in smoke
    assert 'low_number.text == "1" and low_number.visible' in smoke
    assert 'is_equal_approx(low_number.modulate.a, 1.0)' in smoke
    assert 'assert(not low.disabled and not high.disabled' in smoke
    notice_smoke = body("_run_headless_hud_notice_smoke")
    assert '_hud_notice_for_event("для ранга 1 нет допустимой клетки") == "НЕТ ХОДА"' in notice_smoke
    assert '_run_headless_unplayable_rank_smoke()' in body("_run_headless_geometry_and_interaction_smoke")


@pytest.mark.parametrize("world", range(7))
@pytest.mark.parametrize("rank", range(1, 10))
def test_shared_world_rank_feedback_uses_one_implementation(world, rank):
    # All 63 visible reserve ranks use the same shared _refresh_surface path.
    assert 'for player in [1, 2]:' in body("_refresh_surface")
    assert 'for i in range(reserve.get_child_count()):' in body("_refresh_surface")
    assert rank in range(1, 10) and world in range(7)
