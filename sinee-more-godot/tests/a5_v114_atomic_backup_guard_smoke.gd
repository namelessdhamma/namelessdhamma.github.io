extends SceneTree
# Opt-in native Godot 4.7.2 verification; not a Python substitute.
# godot --headless --path sinee-more-godot --script res://tests/a5_v114_atomic_backup_guard_smoke.gd
const Main = preload("res://scripts/main.gd")

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	var app = Main.new()
	var path := "user://a5_v114_atomic_backup_guard.json"
	var absolute := ProjectSettings.globalize_path(path)
	for suffix in ["", ".tmp", ".bak"]:
		var target := absolute + suffix
		if FileAccess.file_exists(path + suffix):
			assert(DirAccess.remove_absolute(target) == OK)
		elif DirAccess.dir_exists_absolute(target):
			assert(DirAccess.remove_absolute(target) == OK)
	var original: Dictionary = app._match_snapshot()
	assert(app._match_snapshot_valid(original))
	assert(app._write_match_atomically(path, original))
	assert(app._read_valid_match_at(path) == JSON.parse_string(JSON.stringify(original)))
	var successor: Dictionary = original.duplicate(true)
	successor["board"][0].append({"player": 1, "rank": 1})
	successor["reserves"][0][0] = false
	successor["moves"] = 1
	successor["turn"] = 2
	assert(app._match_snapshot_valid(successor))
	# A directory at the backup destination deterministically denies file copy.
	assert(DirAccess.make_dir_absolute(absolute + ".bak") == OK)
	assert(not app._write_match_atomically(path, successor), "Backup failure must fail closed")
	assert(app._read_valid_match_at(path) == JSON.parse_string(JSON.stringify(original)),
		"The only valid primary must remain intact after backup failure")
	assert(DirAccess.remove_absolute(absolute + ".bak") == OK)
	assert(app._write_match_atomically(path, successor))
	assert(app._read_valid_match_at(path) == JSON.parse_string(JSON.stringify(successor)))
	assert(app._read_valid_match_at(path + ".bak") == JSON.parse_string(JSON.stringify(original)))
	for suffix in ["", ".tmp", ".bak"]:
		if FileAccess.file_exists(path + suffix):
			assert(DirAccess.remove_absolute(absolute + suffix) == OK)
	app.free()
	print("A5_V114_ATOMIC_BACKUP_GUARD_PASS")
	quit(0)
