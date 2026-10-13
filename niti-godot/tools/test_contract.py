from pathlib import Path
root=Path(__file__).resolve().parent.parent
p=(root/'scripts'/'threads_stage.gd').read_text()
assert (root/'project.godot').exists()
assert (root/'main.tscn').exists()
assert 'extends Node2D' in p
assert 'NITI_PREVIEW_RELIEF' in p
assert 'NITI_RENDER_PREVIEW' in p
assert 'InputEventScreenTouch' in p
assert 'draw_polyline' in p
assert 'THREAD_COUNT := 52' in p
assert 'res://scripts/threads_stage.gd' in (root/'main.tscn').read_text()
assert 'run/main_scene="res://main.tscn"' in (root/'project.godot').read_text()
print('NITI_GODOT_STATIC_CONTRACT=PASS')