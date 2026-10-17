"""A5 v57: sound/haptic parity integrated into the same seven-world game.
No native Godot execution is claimed by this offline test.
"""
import hashlib
import re
import struct
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'scripts/main.gd').read_text()


def fn(name):
    start = SOURCE.index(f'func {name}(')
    end = SOURCE.find('\nfunc ', start + 1)
    if end < 0:
        end = SOURCE.find('\nstatic func ', start + 1)
    return SOURCE[start:end if end >= 0 else None]


class SharedFeedback(unittest.TestCase):
    def test_audio_files_are_real_pcm(self):
        for name in ('select', 'place', 'invalid', 'win'):
            with self.subTest(name=name):
                path = ROOT / 'assets/a5_feedback' / f'{name}.wav'
                with wave.open(str(path), 'rb') as audio:
                    self.assertEqual(audio.getnchannels(), 1)
                    self.assertEqual(audio.getsampwidth(), 2)
                    self.assertEqual(audio.getframerate(), 22050)
                    self.assertLessEqual(audio.getnframes(), 22050 // 2)
                    pcm = audio.readframes(audio.getnframes())
                samples = struct.unpack('<%dh' % (len(pcm)//2), pcm)
                self.assertGreater(max(map(abs, samples)), 1200)
                self.assertLess(max(map(abs, samples)), 32000)
                self.assertLess(sum(abs(x) for x in samples[-100:]), sum(abs(x) for x in samples[:100]) + 150000)

    def test_one_shared_player_and_no_world_forks(self):
        self.assertIn('var feedback_player: AudioStreamPlayer', SOURCE)
        self.assertIn('feedback_player = AudioStreamPlayer.new()', fn('_prepare_feedback'))
        self.assertIn('_prepare_feedback()', fn('_ready'))
        self.assertLess(fn('_ready').index('_prepare_feedback()'), fn('_ready').index('_set_world(current_world)'))
        self.assertNotIn('AudioStreamPlayer', (ROOT / 'scripts/world_visuals.gd').read_text())

    def test_headless_is_quiet(self):
        self.assertIn('if DisplayServer.get_name() == "headless":', fn('_prepare_feedback'))
        self.assertIn('if DisplayServer.get_name() == "headless":', fn('_play_feedback'))
        self.assertIn('return', fn('_play_feedback'))

    def test_only_native_human_haptics(self):
        f = fn('_play_feedback')
        self.assertIn('human_action and haptics_enabled', f)
        self.assertIn('DisplayServer.get_name() in ["Android", "iOS"]', f)
        self.assertIn('Input.vibrate_handheld(duration)', f)
        self.assertIn('not (ai_enabled and moving_player == 2)', fn('_on_primary'))

    def test_persistent_independent_settings(self):
        self.assertIn('sound_enabled = bool(settings.get_value("free_play", "sound_enabled", true))', fn('_load_preferences'))
        self.assertIn('haptics_enabled = bool(settings.get_value("free_play", "haptics_enabled", true))', fn('_load_preferences'))
        self.assertIn('settings.set_value("free_play", "sound_enabled", sound_enabled)', fn('_save_preferences'))
        self.assertIn('settings.set_value("free_play", "haptics_enabled", haptics_enabled)', fn('_save_preferences'))
        self.assertIn('sound_enabled = not sound_enabled', fn('_on_game_menu_item'))
        self.assertIn('haptics_enabled = not haptics_enabled', fn('_on_game_menu_item'))

    def test_mobile_and_desktop_settings_routes(self):
        for marker in ('_mobile_menu_add("Звук:', '_mobile_menu_add("Вибрация:', 'popup.add_check_item("Звук", 103)', 'popup.add_check_item("Вибрация", 104)'):
            self.assertIn(marker, SOURCE)
        self.assertIn('_on_game_menu_item(id)', fn('_on_mobile_menu_action'))
        self.assertIn('_render_mobile_menu_page("main")', fn('_on_mobile_menu_action'))
        self.assertIn('elif id == 103:', fn('_on_game_menu_item'))
        self.assertIn('elif id == 104:', fn('_on_game_menu_item'))

    def test_gameplay_feedback_not_replacing_gameplay(self):
        self.assertIn('_play_feedback("select")', fn('_on_reserve_pressed'))
        self.assertIn('_play_feedback("invalid")', fn('_on_primary'))
        self.assertIn('_play_feedback("win" if game_over and winner != 0 else "place"', fn('_on_primary'))
        self.assertIn('_play_feedback("select")', fn('_confirm_reset_match'))
        self.assertIn('board_stacks[selected_cell].append', fn('_on_primary'))
        self.assertIn('ai_engine.choose_move', fn('_play_ai_turn'))

    def test_all_referenced_files_exist(self):
        for event, path in re.findall(r'"(select|place|invalid|win)": preload\("res://([^"]+)"\)', SOURCE):
            with self.subTest(event=event):
                self.assertTrue((ROOT / path).is_file())

    def test_feedback_is_small_and_deterministic(self):
        paths = list((ROOT / 'assets/a5_feedback').glob('*.wav'))
        self.assertEqual(len(paths), 4)
        self.assertLess(sum(p.stat().st_size for p in paths), 40000)
        self.assertEqual(len({hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}), 4)

if __name__ == '__main__':
    unittest.main()
