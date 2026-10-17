extends Control

const WorldVisuals = preload("res://scripts/world_visuals.gd")
const AIOpponent = preload("res://scripts/ai_opponent.gd")
const PerspectiveGeometry = preload("res://scripts/perspective_board_geometry.gd")
const PieceGrounding = preload("res://scripts/piece_grounding.gd")
# Six solid worlds share one physical tabletop/stone support, aligned to the live grid.
const SUPPORT_SURFACE_COLORS := [Color.TRANSPARENT, Color("#5c351f"), Color("#315964"), Color("#263d48"), Color("#ae8751"), Color("#363443"), Color("#829da8")]
var world_visuals = WorldVisuals.new()
var ai_engine = AIOpponent.new()
var current_world := 1
var ai_enabled := false
var ai_difficulty := 2
var ai_persona := 0
# Exactly one deferred AI action may be queued. A visible menu/rotation gate
# suspends the opponent instead of advancing the board behind the overlay.
var _ai_turn_queued := false
# The OS may suspend the app after an AI move was deferred but before it
# executes. Pause and focus are separate: Android/iOS can resume BEFORE
# reporting focus-in, so one "active" boolean would release the AI too early.
var _app_paused := false
var _app_unfocused := false
# Deferred AI turns that meet a modal are resumed on its real close signal.
# Never let a phone-menu AI toggle leave P2 hidden and the match stranded.
# Shared, optional native feedback for all seven worlds. No world owns audio.
var sound_enabled := true
var haptics_enabled := true
var feedback_player: AudioStreamPlayer
const FEEDBACK_SOUNDS := {
	"select": preload("res://assets/a5_feedback/select.wav"),
	"place": preload("res://assets/a5_feedback/place.wav"),
	"invalid": preload("res://assets/a5_feedback/invalid.wav"),
	"win": preload("res://assets/a5_feedback/win.wav"),
}
var world_picker: MenuButton
var ai_toggle: Button
var top_menu: MenuButton
var rule_submenu: PopupMenu
var difficulty_submenu: PopupMenu
var persona_submenu: PopupMenu
# At 746x280 native PopupMenu theme metrics may shrink below safe touch size.
# The phone route is a real in-scene Control with physical-size buttons.
var mobile_menu_button: Button
var mobile_world_button: Button
var mobile_menu_panel: PanelContainer
var mobile_menu_list: VBoxContainer
var mobile_menu_heading: Label
var _mobile_menu_page := "main"
var _mobile_menu_last_scale := -1.0
var _mobile_menu_last_density := -1.0
var reset_dialog: ConfirmationDialog
var rules_dialog: AcceptDialog
const PREFERENCES_PATH := "user://blue_sea_freeplay_v1.cfg"
const MATCH_STATE_PATH := "user://blue_sea_match_v1.json"
const MATCH_STATE_BACKUP_PATH := "user://blue_sea_match_v1.json.bak"
# Optional bounded undo journal. It is NEVER authoritative for the saved game.
const UNDO_STATE_PATH := "user://blue_sea_undo_v1.json"
var next_round_button: Button
var match_hud: PanelContainer
var match_hud_label: Label
# The low-height phone hides Status; previously invalid taps had only an
# invisible tooltip. Brief, compact notices reuse the live score HUD's SECOND
# line while the score remains visible. No board/modal layout is added.
var _hud_notice_text := ""
var _hud_notice_deadline_msec := 0
const HUD_NOTICE_DURATION_MS := 1700
var reserve_scroller: ScrollContainer
var _last_reserve_scroll_player := 0
# A deferred restore/tutorial reveal must not undo a later user scroll or
# reserve selection. Only real input increments this token; layout-driven
# scrollbar changes and programmatic restore never invalidate one another.
var _reserve_scroll_user_epoch := 0
# On a narrow phone, the reserve must scroll to reach rank 9. A ScrollContainer
# can deliver a delayed Button.pressed after a drag on some touch backends.
# Reject ONLY that GUI echo; keyboard selection and real next taps still work.
var _reserve_touch_active := false
var _reserve_touch_origin := Vector2.ZERO
var _reserve_touch_swiped := false
var _reserve_touch_block_until_msec := 0
# Mouse/trackpad drags may also end in a delayed Button.pressed. Track only
# left-button gestures STARTED inside the visible reserve; an independent
# desktop click outside the reserve or a keyboard selection stays unaffected.
var _reserve_pointer_active := false
var _reserve_pointer_origin := Vector2.ZERO
var _reserve_pointer_dragged := false
var _reserve_pointer_block_until_msec := 0
const RESERVE_SWIPE_CANCEL_DP := 12.0
# One physical scroller serves both players. Remember each player's position
# before hiding their reserve; otherwise rank 8/9 requires another long swipe
# every time an AI turn or local two-player turn completes on dense phones.
var _reserve_scroll_by_player: Array[int] = [0, 0]
# Pure reserve scrolling must survive a reload even when no piece was placed.
# Debounce one atomic snapshot after scrolling settles, never one write/tick.
var reserve_scroll_save_timer: Timer
var _last_persisted_scroll_positions: Array[int] = [0, 0]
# Atomic saves can fail (browser quota, storage permissions, transient mobile
# filesystem errors). Never silently pretend a move is durable: keep a visible
# warning and retry the CURRENT whole-match snapshot, not a stale saved copy.
const MATCH_SAVE_RETRY_MAX := 3
var match_save_retry_timer: Timer
var _match_save_dirty := false
var _match_save_retry_attempts := 0
# Canonical reference art includes a top-left menu glyph. Keep its pixels intact
# and give it a real, touch-safe action rather than leaving dead screenshot UI.
var reference_menu_hotspot: Button
# Source-extracted canonical plate is separate from the scene perimeter.
# In Void the perimeter is intentionally hidden; without this plate the
# otherwise functional mobile menu hotspot is completely invisible.
var reference_menu_art: TextureRect
var orientation_overlay: ColorRect
var canonical_live_logo: TextureRect
var _last_logo_viewport := Vector2.ZERO
var reference_menu_clearance: Control
var _last_reference_hotspot_viewport := Vector2.ZERO
var _last_reference_hotspot_scale := -1.0
var _last_reference_hotspot_density := -1.0

const CELL_NAMES: Array[String] = ["Cell00", "Cell01", "Cell02", "Cell10", "Cell11", "Cell12", "Cell20", "Cell21", "Cell22"]
var selected_cell := -1
var selected_reserve := -1
var turn := 1
var moves := 0
var current_rule := "CD"
const LINES: Array[Array] = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]]
var board_stacks: Array[Array] = [[],[],[],[],[],[],[],[],[]]
var reserve_available: Array[Array] = [[true,true,true,true,true,true,true,true,true],[true,true,true,true,true,true,true,true,true]]
var winner := 0
var win_line: Array = []
var game_over := false
var round_draw := false
const MATCH_TARGET := 3
var round_number := 1
var match_score: Array[int] = [0, 0]
var match_winner := 0
var blocked_player := 0
# Website RC2.6 parity: one bounded in-session undo history, shared across
# all seven worlds. Each entry is a validated PRE-MOVE core snapshot, never a
# second rules engine. As in the accepted web game, reload restores the match
# but starts a fresh undo history; no unvalidated nested save schema is added.
var _undo_history: Array[Dictionary] = []
var _last_touch_scale := -1.0
var _last_touch_density := -1.0
# Browser rotation can change the logical viewport/mobile menu profile while
# keeping DPR and device density unchanged. Both are layout inputs: caching
# only scale/density left the live HUD and reserve badge geometry stale.
var _last_touch_viewport_size := Vector2(-1.0, -1.0)
var _last_touch_mobile_profile := false
# A touch can be followed by a Godot-emulated left mouse press in the same
# input frame. The board is handled in _input, before GUI dispatch, so both
# events otherwise act as two independent taps and ghost-select the next turn.
var _last_board_press_frame := -100
var _last_board_press_position := Vector2(-10000.0, -10000.0)
var _last_board_press_kind := "none"
# Touch gameplay commits on RELEASE, not on finger-down: a drag across the
# perspective board must never spend a rank. This state is shared by all worlds.
var _touch_board_pending := false
# Track the complete primary-finger gesture, including touches that start in
# the reserve/menu. Otherwise a release onto the board can become a synthetic
# mouse click and place a previously selected rank without a board touch-down.
var _touch_primary_active := false
# Godot indexes each finger separately. A non-primary finger can arrive BEFORE
# index 0; merely cancelling on a later secondary press is insufficient.
# Keep active secondary indices until their release or a focus-loss reset.
var _touch_secondary_indices: Dictionary = {}
var _touch_board_started := false
var _touch_board_origin := Vector2.ZERO
var _touch_board_cell := -1
# Bind a finger-down to the exact live turn, selected rank, round, world and
# rule. Keyboard, AI, rotation, or menu changes during a hold must not spend a
# DIFFERENT piece when the finger finally lifts over the original cell.
var _touch_board_state_at_press: Array = []
# Godot/web touch emulation may send a synthetic mouse-down before OR after
# release. Suppress only its nearby echo, not independent mouse clicks.
var _touch_mouse_echo_position := Vector2(-10000.0, -10000.0)
var _touch_mouse_echo_origin := Vector2(-10000.0, -10000.0)
var _touch_mouse_echo_deadline_msec := 0
const TOUCH_MOUSE_ECHO_MS := 350
# Once two fingers have participated, a delayed synthetic mouse-down can be
# delivered at ANY of their traversed positions, not only the final point.
# Bound this board-only suppression; ordinary pointer play resumes afterward.
var _touch_multifinger_mouse_echo_deadline_msec := 0
const TOUCH_TAP_DRIFT_DP := 16.0
# Android Back is navigation, not an implicit discard/exit of a live match.
# A physical key and WM_GO_BACK_REQUEST may describe the same single press.
var _last_mobile_back_frame := -100

# Native visual evidence is opt-in. The normal player launch never takes
# screenshots or changes how its match/preferences are persisted.
func _is_visual_capture_run() -> bool:
	return "--nd-capture-seven" in OS.get_cmdline_user_args()

func _headless_run_mode() -> String:
	# Never run destructive gameplay fixtures merely because a CI capture or
	# export process has no display. Qualification must be explicitly requested.
	if DisplayServer.get_name() != "headless":
		return ""
	var args := OS.get_cmdline_user_args()
	if "--nd-run-full-match" in args:
		return "full_match"
	if "--nd-run-smoke" in args:
		return "smoke"
	return ""

func _preferences_path() -> String:
	# Only explicit headless qualification writes to a disposable test config.
	return "user://blue_sea_freeplay_v1_test.cfg" if DisplayServer.get_name() == "headless" else PREFERENCES_PATH

func _load_preferences() -> void:
	if _is_visual_capture_run():
		return
	# A fresh CI screenshot starts from an empty, deterministic match, never a
	# previous test's mutable user:// state. Real player preferences are intact.
	if DisplayServer.get_name() == "headless":
		return
	var settings := ConfigFile.new()
	if settings.load(_preferences_path()) != OK:
		return
	current_world = clampi(int(settings.get_value("free_play", "world", 1)), 0, WorldVisuals.WORLDS.size() - 1)
	ai_enabled = bool(settings.get_value("free_play", "ai_enabled", false))
	ai_difficulty = clampi(int(settings.get_value("free_play", "ai_difficulty", 2)), 1, 3)
	ai_persona = clampi(int(settings.get_value("free_play", "ai_persona", 0)), 0, 2)
	sound_enabled = bool(settings.get_value("free_play", "sound_enabled", true))
	haptics_enabled = bool(settings.get_value("free_play", "haptics_enabled", true))
	var loaded_rule := str(settings.get_value("free_play", "rule", "CD"))
	current_rule = loaded_rule if loaded_rule in ["C", "D", "CD"] else "CD"

func _save_preferences() -> void:
	if _is_visual_capture_run():
		return
	# Ordinary headless import/rendering is read-only. The explicit smoke mode
	# may still exercise ConfigFile persistence in its isolated test path.
	if DisplayServer.get_name() == "headless" and _headless_run_mode() == "":
		return
	var settings := ConfigFile.new()
	settings.set_value("free_play", "version", 1)
	settings.set_value("free_play", "world", current_world)
	settings.set_value("free_play", "ai_enabled", ai_enabled)
	settings.set_value("free_play", "ai_difficulty", ai_difficulty)
	settings.set_value("free_play", "ai_persona", ai_persona)
	settings.set_value("free_play", "sound_enabled", sound_enabled)
	settings.set_value("free_play", "haptics_enabled", haptics_enabled)
	settings.set_value("free_play", "rule", current_rule)
	var err := settings.save(_preferences_path())
	if err != OK:
		push_warning("Blue Sea settings could not be saved: %d" % err)

# Match state is distinct from user preferences. World switches and device rotation
# preserve the live game, and a real app/browser reload restores the same round.
# Headless imports and qualification NEVER read/write a user's saved match.
# Keep the current player's live scroller offset as well as the last hidden
# opponent offset. A saved move can be reloaded on Android without making
# the player swipe back to rank 8/9. No extra save is written per scroll tick.
func _snapshot_reserve_scroll() -> Array[int]:
	var positions: Array[int] = [_reserve_scroll_by_player[0], _reserve_scroll_by_player[1]]
	if reserve_scroller != null and reserve_scroller.visible and _last_reserve_scroll_player in [1, 2]:
		positions[_last_reserve_scroll_player - 1] = maxi(0, reserve_scroller.scroll_horizontal)
	return positions

func _match_snapshot() -> Dictionary:
	return {
		"schema": 1, "rule": current_rule,
		"board": board_stacks.duplicate(true),
		"reserves": reserve_available.duplicate(true),
		"turn": turn, "moves": moves, "round": round_number,
		"score": match_score.duplicate(), "winner": winner,
		"win_line": win_line.duplicate(), "game_over": game_over,
		"draw": round_draw, "match_winner": match_winner,
		"blocked_player": blocked_player,
		"reserve_scroll": _snapshot_reserve_scroll()
	}

func _match_snapshot_valid(state: Dictionary) -> bool:
	var required := ["schema", "rule", "board", "reserves", "turn", "moves", "round", "score", "winner", "win_line", "game_over", "draw", "match_winner", "blocked_player"]
	if not state.has_all(required) or int(state["schema"]) != 1:
		return false
	# The persisted match is authoritative for its rule. Preferences can be
	# missing/stale after a browser crash or interrupted settings write; do not
	# discard a legal C/D round merely because preferences defaulted to CD.
	if typeof(state["rule"]) != TYPE_STRING:
		return false
	var snapshot_rule: String = state["rule"]
	if not (snapshot_rule in ["C", "D", "CD"]):
		return false
	if not (state["board"] is Array and state["reserves"] is Array and state["score"] is Array and state["win_line"] is Array):
		return false
	var stacks: Array = state["board"]
	var reserves: Array = state["reserves"]
	var score: Array = state["score"]
	if stacks.size() != 9 or reserves.size() != 2 or score.size() != 2:
		return false
	# Optional additive field: every v81-v90 save remains valid. Reject
	# malformed or negative scroll offsets rather than silently coercing
	# them into large/invalid native ScrollBar positions on next launch.
	if state.has("reserve_scroll"):
		if not (state["reserve_scroll"] is Array) or state["reserve_scroll"].size() != 2:
			return false
		for offset in state["reserve_scroll"]:
			if not (typeof(offset) in [TYPE_INT, TYPE_FLOAT]) or float(offset) != float(int(offset)) or int(offset) < 0 or int(offset) > 1000000:
				return false
	for key in ["turn", "moves", "round", "winner", "match_winner", "blocked_player"]:
		if not (typeof(state[key]) in [TYPE_INT, TYPE_FLOAT]) or float(state[key]) != float(int(state[key])):
			return false
	if typeof(state["game_over"]) != TYPE_BOOL or typeof(state["draw"]) != TYPE_BOOL:
		return false
	var active := int(state["turn"])
	var count := int(state["moves"])
	var round_id := int(state["round"])
	var winner_id := int(state["winner"])
	var match_id := int(state["match_winner"])
	var blocked := int(state["blocked_player"])
	if not (active in [1, 2]) or count < 0 or count > 18 or round_id < 1 or round_id > 1000000:
		return false
	if not (winner_id in [0, 1, 2]) or not (match_id in [0, 1, 2]) or not (blocked in [0, 1, 2]):
		return false
	if blocked != 0 and (blocked == active or bool(state["game_over"])):
		return false
	var used := [[false, false, false, false, false, false, false, false, false],
		[false, false, false, false, false, false, false, false, false]]
	var piece_count := 0
	for stack in stacks:
		if not (stack is Array) or (snapshot_rule != "D" and stack.size() > 2):
			return false
		var prior_rank := 0
		var prior_player := 0
		for piece in stack:
			if not (piece is Dictionary) or not piece.has_all(["player", "rank"]):
				return false
			if not (typeof(piece["player"]) in [TYPE_INT, TYPE_FLOAT]) or not (typeof(piece["rank"]) in [TYPE_INT, TYPE_FLOAT]):
				return false
			var owner := int(piece["player"])
			var rank := int(piece["rank"])
			if float(piece["player"]) != float(owner) or float(piece["rank"]) != float(rank):
				return false
			if not (owner in [1, 2]) or rank < 1 or rank > 9:
				return false
			if rank <= prior_rank or owner == prior_player or used[owner - 1][rank - 1]:
				return false
			used[owner - 1][rank - 1] = true
			prior_rank = rank
			prior_player = owner
			piece_count += 1
	if piece_count != count:
		return false
	for player in range(2):
		if not (reserves[player] is Array) or reserves[player].size() != 9:
			return false
		for rank in range(9):
			if typeof(reserves[player][rank]) != TYPE_BOOL or bool(reserves[player][rank]) == used[player][rank]:
				return false
	for value in score:
		if not (typeof(value) in [TYPE_INT, TYPE_FLOAT]) or float(value) != float(int(value)) or int(value) < 0 or int(value) > MATCH_TARGET:
			return false
	if int(score[0]) + int(score[1]) > round_id:
		return false
	var over := bool(state["game_over"])
	var draw := bool(state["draw"])
	var line: Array = state["win_line"]
	if not over and (winner_id != 0 or draw or match_id != 0 or not line.is_empty()):
		return false
	if over and ((winner_id == 0) != draw):
		return false
	if winner_id == 0 and not line.is_empty():
		return false
	if winner_id != 0:
		if line.size() != 3 or not LINES.has(line) or int(score[winner_id - 1]) < 1:
			return false
		var ranks: Array[int] = []
		for cell in line:
			if stacks[cell].is_empty() or int(stacks[cell][-1]["player"]) != winner_id:
				return false
			ranks.append(int(stacks[cell][-1]["rank"]))
		if snapshot_rule != "C" and not ((ranks[0] < ranks[1] and ranks[1] < ranks[2]) or (ranks[0] > ranks[1] and ranks[1] > ranks[2])):
			return false
	if match_id != 0 and (match_id != winner_id or int(score[match_id - 1]) != MATCH_TARGET):
		return false
	if match_id == 0 and (int(score[0]) >= MATCH_TARGET or int(score[1]) >= MATCH_TARGET):
		return false
	return true

func _apply_match_snapshot(state: Dictionary, preserve_undo: bool = false) -> void:
	if not preserve_undo:
		_undo_history.clear()
	# Called ONLY after validation. Rebuild typed arrays from JSON's untyped data.
	# The round's rule travels with the round, independent of stale preferences.
	current_rule = str(state["rule"])
	board_stacks.clear()
	for source_stack in state["board"]:
		var stack: Array = []
		for piece in source_stack:
			stack.append({"player": int(piece["player"]), "rank": int(piece["rank"])})
		board_stacks.append(stack)
	reserve_available.clear()
	for source_row in state["reserves"]:
		var row: Array = []
		for flag in source_row:
			row.append(bool(flag))
		reserve_available.append(row)
	turn = int(state["turn"])
	moves = int(state["moves"])
	round_number = int(state["round"])
	match_score.clear()
	match_score.append(int(state["score"][0]))
	match_score.append(int(state["score"][1]))
	winner = int(state["winner"])
	win_line = state["win_line"].duplicate()
	game_over = bool(state["game_over"])
	round_draw = bool(state["draw"])
	match_winner = int(state["match_winner"])
	blocked_player = int(state["blocked_player"])
	# Restored before _prepare_world_shell creates the actual ScrollContainer.
	# The first _refresh_surface() schedules a layout-safe clamped restore.
	_reserve_scroll_by_player = [0, 0]
	if state.has("reserve_scroll"):
		_reserve_scroll_by_player = [int(state["reserve_scroll"][0]), int(state["reserve_scroll"][1])]
	_last_reserve_scroll_player = 0
	_last_persisted_scroll_positions = _reserve_scroll_by_player.duplicate()
	selected_reserve = -1
	selected_cell = -1


# A valid legacy/interrupted snapshot can still point at a player with no
# legal move. Repair this BEFORE the first visible frame, regardless of whether
# that player is human or AI. Otherwise a human turn can remain unplayable
# forever (the AI-only v85 guard cannot run on P1's turn).
func _reconcile_restored_turn() -> bool:
	if game_over or _has_legal_move(turn):
		return false
	var exhausted := turn
	var other := 2 if turn == 1 else 1
	if _has_legal_move(other):
		blocked_player = exhausted
		turn = other
	else:
		# Neither player can move: a real terminal draw, not a blank reserve.
		blocked_player = 0
		game_over = true
		round_draw = true
	selected_reserve = -1
	selected_cell = -1
	return true

# Never truncate the sole valid save. The previous valid snapshot is kept as a
# recoverable backup; a flushed temporary snapshot replaces the primary only
# after a complete parse/validation readback. Existing v81 saves are compatible.
func _read_valid_match_at(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var parsed = JSON.parse_string(file.get_as_text())
	file.close()
	if parsed is Dictionary and _match_snapshot_valid(parsed):
		return parsed
	return {}

func _write_match_atomically(path: String, state: Dictionary) -> bool:
	if not _match_snapshot_valid(state):
		push_warning("Blue Sea: invalid match state was not saved")
		return false
	var temporary := path + ".tmp"
	var file := FileAccess.open(temporary, FileAccess.WRITE)
	if file == null:
		push_warning("Blue Sea: temporary match save unavailable")
		return false
	var payload := JSON.stringify(state)
	file.store_string(payload)
	file.flush()
	file.close()
	# Compare normalized JSON values, not typed-vs-untyped GDScript arrays.
	var expected_snapshot = JSON.parse_string(payload)
	# Validation alone is insufficient: a readable but older/different temp
	# snapshot must never be reported as the newly committed match.
	if _read_valid_match_at(temporary) != expected_snapshot:
		push_warning("Blue Sea: temporary match save failed exact state readback")
		return false
	var primary_absolute := ProjectSettings.globalize_path(path)
	# Preserve the last known-good primary until its backup is independently
	# verified. Previously a failed backup copy was logged but the only valid
	# primary was still replaced, silently losing the recovery generation.
	var previous_snapshot := _read_valid_match_at(path)
	if not previous_snapshot.is_empty():
		var backup_result := DirAccess.copy_absolute(primary_absolute, ProjectSettings.globalize_path(path + ".bak"))
		if backup_result != OK:
			push_warning("Blue Sea: backup copy failed; preserving last valid primary: %d" % backup_result)
			return false
		if _read_valid_match_at(path + ".bak") != previous_snapshot:
			push_warning("Blue Sea: backup readback mismatch; preserving last valid primary")
			return false
	var result := DirAccess.rename_absolute(ProjectSettings.globalize_path(temporary), primary_absolute)
	if result != OK:
		push_warning("Blue Sea: atomic match save replace failed: %d" % result)
		return false
	# Do not clear the UNSAVED warning merely because the filesystem reported
	# success. The next launch can recover the independently checked backup.
	if _read_valid_match_at(path) != expected_snapshot:
		push_warning("Blue Sea: primary match readback mismatch after replace")
		return false
	return true

# The match save remains the only gameplay authority. A separate, optional
# bounded journal restores the Website RC2.6 Undo action after a browser reload
# or Android process restart. Its fingerprint is derived from canonical game
# fields (not scroll position or JSON dictionary insertion order). Stale or
# malformed journals are discarded without discarding the actual saved game.
static func _undo_match_fingerprint(state: Dictionary) -> String:
	var cells: Array = []
	for stack in state["board"]:
		var ranks: Array = []
		for piece in stack:
			ranks.append([int(piece["player"]), int(piece["rank"])])
		cells.append(ranks)
	var normalized_line: Array = []
	for cell in state["win_line"]:
		normalized_line.append(int(cell))
	return JSON.stringify([state["rule"], cells, state["reserves"],
		int(state["turn"]), int(state["moves"]), int(state["round"]),
		[int(state["score"][0]), int(state["score"][1])], int(state["winner"]), normalized_line,
		bool(state["game_over"]), bool(state["draw"]),
		int(state["match_winner"]), int(state["blocked_player"])]).sha256_text()

# A journal must be a real reverse chain of one-piece placements, not merely
# a collection of individually legal-looking boards. Otherwise a corrupt
# sidecar could undo into a different valid match while its fingerprint still
# matches the final state.
static func _undo_single_placement_valid(before: Dictionary, after: Dictionary, player: int) -> bool:
	if int(after["moves"]) != int(before["moves"]) + 1 or int(before["turn"]) != player:
		return false
	if bool(before["game_over"]) or int(before["round"]) != int(after["round"]) or str(before["rule"]) != str(after["rule"]):
		return false
	var changed_cell := -1
	var used_rank := -1
	for cell in range(9):
		var prior: Array = before["board"][cell]
		var current: Array = after["board"][cell]
		if prior == current:
			continue
		if changed_cell != -1 or current.size() != prior.size() + 1:
			return false
		for index in range(prior.size()):
			if prior[index] != current[index]:
				return false
		var placed: Dictionary = current[-1]
		if int(placed["player"]) != player:
			return false
		changed_cell = cell
		used_rank = int(placed["rank"])
	if changed_cell == -1 or used_rank < 1 or used_rank > 9:
		return false
	for owner in range(2):
		for rank_index in range(9):
			var prior_available: bool = before["reserves"][owner][rank_index]
			var current_available: bool = after["reserves"][owner][rank_index]
			if owner == player - 1 and rank_index == used_rank - 1:
				if not prior_available or current_available:
					return false
			elif prior_available != current_available:
				return false
	for owner in range(2):
		var expected_score := int(before["score"][owner]) + (1 if int(after["winner"]) == owner + 1 else 0)
		if int(after["score"][owner]) != expected_score:
			return false
	return true

func _undo_journal_valid(history: Variant, state: Dictionary) -> bool:
	if not (history is Array) or history.size() > 18:
		return false
	var after := state
	for index in range(history.size() - 1, -1, -1):
		var item = history[index]
		if not (item is Dictionary) or not item.has_all(["before", "player", "was_ai"]):
			return false
		if not (typeof(item["player"]) in [TYPE_INT, TYPE_FLOAT]) or float(item["player"]) != float(int(item["player"])) or typeof(item["was_ai"]) != TYPE_BOOL:
			return false
		var player: int = item["player"]
		if not (player in [1, 2]) or (bool(item["was_ai"]) and player != 2):
			return false
		if not (item["before"] is Dictionary):
			return false
		var before: Dictionary = item["before"]
		if not _match_snapshot_valid(before) or not _undo_single_placement_valid(before, after, player):
			return false
		after = before
	return true

func _write_undo_journal(path: String, state: Dictionary, history: Array) -> bool:
	if not _match_snapshot_valid(state) or not _undo_journal_valid(history, state):
		return false
	var payload := {"schema": 1, "fingerprint": _undo_match_fingerprint(state),
		"history": history.duplicate(true)}
	var temporary := path + ".tmp"
	var file := FileAccess.open(temporary, FileAccess.WRITE)
	if file == null:
		return false
	file.store_string(JSON.stringify(payload))
	file.flush()
	file.close()
	var check := FileAccess.open(temporary, FileAccess.READ)
	if check == null:
		return false
	var parsed = JSON.parse_string(check.get_as_text())
	check.close()
	if not (parsed is Dictionary) or parsed != JSON.parse_string(JSON.stringify(payload)):
		return false
	if DirAccess.rename_absolute(ProjectSettings.globalize_path(temporary), ProjectSettings.globalize_path(path)) != OK:
		return false
	return _read_undo_journal(path, state) == JSON.parse_string(JSON.stringify(history))

func _read_undo_journal(path: String, state: Dictionary) -> Array:
	if not FileAccess.file_exists(path):
		return []
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return []
	var parsed = JSON.parse_string(file.get_as_text())
	file.close()
	if not (parsed is Dictionary) or not parsed.has_all(["schema", "fingerprint", "history"]):
		return []
	if not (typeof(parsed["schema"]) in [TYPE_INT, TYPE_FLOAT]) or float(parsed["schema"]) != 1.0:
		return []
	if typeof(parsed["fingerprint"]) != TYPE_STRING or parsed["fingerprint"] != _undo_match_fingerprint(state):
		return []
	if not _undo_journal_valid(parsed["history"], state):
		return []
	return parsed["history"].duplicate(true)

func _restore_undo_journal(state: Dictionary) -> void:
	_undo_history.clear()
	for entry in _read_undo_journal(UNDO_STATE_PATH, state):
		_undo_history.append(entry)

func _load_match() -> bool:
	if _is_visual_capture_run():
		return false
	if DisplayServer.get_name() == "headless":
		return false
	var restored: Dictionary = {}
	if FileAccess.file_exists(MATCH_STATE_PATH):
		restored = _read_valid_match_at(MATCH_STATE_PATH)
	var recovered_from_backup := false
	if restored.is_empty():
		restored = _read_valid_match_at(MATCH_STATE_BACKUP_PATH)
		recovered_from_backup = not restored.is_empty()
	if restored.is_empty():
		if FileAccess.file_exists(MATCH_STATE_PATH) or FileAccess.file_exists(MATCH_STATE_BACKUP_PATH):
			push_warning("Blue Sea: no valid match snapshot; starting a clean round")
		return false
	var recovered_rule_differs := current_rule != str(restored["rule"])
	_apply_match_snapshot(restored)
	var repaired_turn := _reconcile_restored_turn()
	# A repaired turn invalidates the previous fingerprint, deliberately
	# discarding stale Undo while keeping the recovered legal match intact.
	_restore_undo_journal(_match_snapshot())
	if repaired_turn:
		assert(_match_snapshot_valid(_match_snapshot()), "Restored turn repair must preserve valid state")
	if recovered_rule_differs:
		# Converge the settings file AFTER the valid match has been restored.
		# No rule-selection UI is bypassed: the rule belongs to the saved round.
		_save_preferences()
	if recovered_from_backup:
		push_warning("Blue Sea: match restored from last valid backup")
	if repaired_turn or recovered_from_backup:
		# Persist the repaired turn before UI/AI setup; a second crash must not
		# reopen the same impossible turn on the next launch.
		_save_match()
	return true

static func _match_save_retry_delay(attempts: int) -> float:
	# Bounded 1s/2s/4s backoff, with no permanent disk-writing loop.
	return minf(8.0, pow(2.0, float(maxi(0, attempts))))

func _retry_failed_match_save() -> void:
	if not _match_save_dirty or _match_save_retry_attempts >= MATCH_SAVE_RETRY_MAX:
		return
	_match_save_retry_attempts += 1
	# Rebuild from live state: AI/human moves during backoff must never be
	# replaced with the stale snapshot that originally failed to save.
	_save_match()

# After the three automatic retries have been exhausted, the game stays
# honestly marked UNSAVED. A deliberate menu action provides a new bounded
# attempt when the user has restored storage/quota/network availability.
# Never silently loop forever or replay a stale board snapshot.
func _retry_unsaved_match_on_request() -> void:
	if not _match_save_dirty:
		return
	if match_save_retry_timer != null:
		match_save_retry_timer.stop()
	_match_save_retry_attempts = 0
	_save_match()
	_update_status("save recovered" if not _match_save_dirty else "save retry failed")

func _save_match() -> void:
	if _is_visual_capture_run():
		return
	if DisplayServer.get_name() == "headless":
		return
	if _write_match_atomically(MATCH_STATE_PATH, _match_snapshot()):
		# Undo is auxiliary. A journal failure must NEVER mark a valid game
		# snapshot unsaved or cause a loop of match writes.
		if not _write_undo_journal(UNDO_STATE_PATH, _match_snapshot(), _undo_history):
			push_warning("Blue Sea: optional Undo journal unavailable; match is safe")
		# No yield or event dispatch occurs between snapshot and this read.
		_last_persisted_scroll_positions = _snapshot_reserve_scroll()
		_match_save_dirty = false
		_match_save_retry_attempts = 0
		if match_save_retry_timer != null:
			match_save_retry_timer.stop()
	else:
		_match_save_dirty = true
		if match_save_retry_timer != null and _match_save_retry_attempts < MATCH_SAVE_RETRY_MAX and match_save_retry_timer.is_stopped():
			match_save_retry_timer.start(_match_save_retry_delay(_match_save_retry_attempts))
	_refresh_match_hud()

# ScrollBar.value_changed fires on drag, wheel, inertia and programmatic restore.
# Only the active human's visible reserve is eligible; a turn transition already
# persists its offset through the ordinary atomic move save.
func _on_reserve_scroll_changed(_value: float) -> void:
	if DisplayServer.get_name() == "headless" or reserve_scroll_save_timer == null:
		return
	if game_over or reserve_scroller == null or not reserve_scroller.visible:
		return
	if _last_reserve_scroll_player != turn or not (turn in [1, 2]):
		return
	if ai_enabled and turn == 2:
		return
	reserve_scroll_save_timer.start()

func _persist_idle_reserve_scroll() -> void:
	if DisplayServer.get_name() == "headless" or game_over:
		return
	if reserve_scroller == null or not reserve_scroller.visible or _last_reserve_scroll_player != turn:
		return
	if ai_enabled and turn == 2:
		return
	var offsets := _snapshot_reserve_scroll()
	if offsets != _last_persisted_scroll_positions:
		_save_match()

# Android/iOS can suspend or kill a backgrounded process before the 0.65s
# scroll-idle timer fires. Persist the active player's scroll offset
# synchronously on lifecycle transitions, using the SAME validated atomic
# match snapshot as ordinary moves. This never commits a board move.
# OS suspension is a gameplay boundary, not just a save trigger. A queued
# computer move must not commit behind the Android app switcher or a desktop
# focus loss. Resume only after BOTH independent OS gates have cleared.
func _interaction_suspended() -> bool:
	return _app_paused or _app_unfocused

func _notification(what: int) -> void:
	if what == NOTIFICATION_APPLICATION_RESUMED:
		_app_paused = false
		if not _interaction_suspended() and is_node_ready() and reserve_scroller != null:
			call_deferred("_queue_ai_turn_if_ready")
		return
	if what == NOTIFICATION_APPLICATION_FOCUS_IN:
		_app_unfocused = false
		if not _interaction_suspended() and is_node_ready() and reserve_scroller != null:
			call_deferred("_queue_ai_turn_if_ready")
		return
	if not (what in [
		NOTIFICATION_APPLICATION_PAUSED,
		NOTIFICATION_APPLICATION_FOCUS_OUT,
		NOTIFICATION_WM_CLOSE_REQUEST,
		NOTIFICATION_WM_GO_BACK_REQUEST,
	]):
		return
	if what == NOTIFICATION_APPLICATION_PAUSED:
		_app_paused = true
	elif what == NOTIFICATION_APPLICATION_FOCUS_OUT:
		_app_unfocused = true
	# A backgrounded reserve swipe/press cannot become a stale GUI Button
	# click after foreground resume. The next fresh touch clears this guard.
	if _reserve_touch_active:
		_reserve_touch_block_until_msec = Time.get_ticks_msec() + TOUCH_MOUSE_ECHO_MS
	_reserve_touch_active = false
	_reserve_touch_swiped = false
	if _reserve_pointer_active:
		_reserve_pointer_block_until_msec = Time.get_ticks_msec() + TOUCH_MOUSE_ECHO_MS
	_reserve_pointer_active = false
	_reserve_pointer_dragged = false
	# A backgrounded touch cannot become a new move on foreground resume.
	_cancel_pending_board_touch()
	_touch_primary_active = false
	_touch_secondary_indices.clear()
	_touch_board_started = false
	_touch_board_cell = -1
	_touch_mouse_echo_deadline_msec = Time.get_ticks_msec() + TOUCH_MOUSE_ECHO_MS
	_touch_multifinger_mouse_echo_deadline_msec = _touch_mouse_echo_deadline_msec
	# Lifecycle notifications can arrive while this scene is being created.
	if not is_node_ready() or reserve_scroller == null:
		return
	if reserve_scroll_save_timer != null:
		reserve_scroll_save_timer.stop()
	_persist_idle_reserve_scroll()
	# A failed prior move-save matters even if the reserve did not scroll.
	# Try one bounded synchronous flush before mobile suspension/close.
	if _match_save_dirty and _match_save_retry_attempts < MATCH_SAVE_RETRY_MAX:
		_retry_failed_match_save()
	# The system Back gesture/key is an in-game navigation action on phones.
	# Keep the durable flush above even if this press only closes a menu.
	if what == NOTIFICATION_WM_GO_BACK_REQUEST:
		_handle_mobile_back()


# Reuse the SAME canonical top-left menu rather than adding Back/Reset/Next
# under the live reserve. A Back press cancels a reset confirmation, returns
# from a submenu, or opens/closes the main menu without touching game state.
# Suppress the paired Android Escape + OS notification within two frames.
func _handle_mobile_back() -> void:
	if not _use_mobile_menu() or mobile_menu_panel == null:
		return
	var frame := Engine.get_process_frames()
	if frame >= _last_mobile_back_frame and frame - _last_mobile_back_frame <= 2:
		return
	if orientation_overlay != null and orientation_overlay.visible:
		return
	var pirate_choice := get_node_or_null("PirateOpeningChoiceSurface/PirateOpeningChoice") as Control
	if pirate_choice != null and pirate_choice.visible:
		return
	_last_mobile_back_frame = frame
	if reset_dialog != null and reset_dialog.visible:
		reset_dialog.hide()
		return
	if rules_dialog != null and rules_dialog.visible:
		rules_dialog.hide()
		return
	if mobile_menu_panel.visible:
		if _mobile_menu_page == "main":
			mobile_menu_panel.hide()
		elif _mobile_menu_page.begins_with("tutorial_") and _mobile_menu_page != "tutorial_1":
			var page_number := int(_mobile_menu_page.trim_prefix("tutorial_"))
			_render_mobile_menu_page("tutorial_%d" % (page_number - 1))
		else:
			_render_mobile_menu_page("main")
		return
	_open_mobile_menu()


func _rules_help_text() -> String:
	return """СИНЕЕ МОРЕ — ПРАВИЛА

Выберите фигуру из девяти под доской, затем коснитесь клетки.
На поле показан только верхний жетон каждой стопки.
Фигура может накрыть только меньшую фигуру противника.
Каждая фигура ранга 1–9 используется один раз за раунд.

C: победа — любые три свои верхние фигуры в ряд; стопка до 2.
D: победа — три свои верхние фигуры в ряд по возрастанию или убыванию ранга; глубокие стопки разрешены.
CD: условие ряда D + ограничение стопки C (до 2).

Партия идёт до трёх побед в раундах; первый ход чередуется.
Правила можно менять только до первого хода партии.
Верхнее меню: настройки ИИ, сброс с подтверждением.
После конца раунда появляется кнопка продолжения.
Клавиатура: 1–9 — фигура; стрелки — клетка; Enter/Пробел — ход;
Esc — снять выбор; M — открыть меню.
Android: системная «Назад» открывает меню, возвращает на предыдущий экран или отменяет сброс."""

func _physical_pixel_scale() -> float:
	var logical := get_viewport_rect().size
	var physical := get_window().size
	if logical.y <= 0.0 or physical.y <= 0:
		return 1.0
	return maxf(0.01, float(physical.y) / logical.y)

func _native_touch_density() -> float:
	# Godot window sizes are physical pixels on native mobile exports.
	# A 44-pixel hit target is only ~15 dp on a 3x-density Android phone.
	# Browser viewports already use their own CSS-pixel scaling contract.
	match DisplayServer.get_name():
		"Android":
			return clampf(float(DisplayServer.screen_get_dpi()) / 160.0, 1.0, 4.0)
		"iOS":
			return clampf(DisplayServer.screen_get_scale(), 1.0, 4.0)
	return 1.0

func _minimum_touch_physical_px() -> float:
	return 44.0 * _native_touch_density()

func _ensure_physical_touch_targets() -> void:
	var scale := _physical_pixel_scale()
	var density := _native_touch_density()
	var viewport_size := get_viewport_rect().size
	var phone_profile := _use_mobile_menu()
	var geometry_changed := viewport_size != _last_touch_viewport_size or phone_profile != _last_touch_mobile_profile
	if not geometry_changed and absf(scale - _last_touch_scale) < 0.0001 and absf(density - _last_touch_density) < 0.0001:
		return
	_last_touch_scale = scale
	_last_touch_density = density
	_last_touch_viewport_size = viewport_size
	_last_touch_mobile_profile = phone_profile
	var logical_touch := ceilf(_minimum_touch_physical_px() / scale)
	var logical_rank := maxi(16, ceili(14.0 * density / scale))
	var title := get_node("SafeArea/Landscape/Center/TopBar/Title") as Label
	title.add_theme_font_size_override("font_size", maxi(20, ceili(18.0 * density / scale)))
	for button in [mobile_world_button if _use_mobile_menu() else world_picker, ai_toggle, mobile_menu_button if _use_mobile_menu() else top_menu]:
		button.custom_minimum_size = Vector2(maxf(button.custom_minimum_size.x, logical_touch), logical_touch)
	for player in [1, 2]:
		var reserve := _reserve_node(player)
		for piece in reserve.get_children():
			var control := piece as Button
			control.custom_minimum_size = Vector2(logical_touch, logical_touch)
			var number := control.get_node_or_null("RankNumber") as Label
			if number != null:
				number.add_theme_font_size_override("font_size", logical_rank)
	var dock := get_node("SafeArea/Landscape/Center/ReserveDock") as HBoxContainer
	dock.custom_minimum_size = Vector2(0, logical_touch)
	if reserve_scroller != null:
		# A 3x-DPI phone needs nine 44dp pieces (>1,180 physical px).
		# The scroll viewport grows vertically with the actual tap targets.
		reserve_scroller.custom_minimum_size.y = logical_touch
	next_round_button.custom_minimum_size = Vector2(maxf(176.0, logical_touch * 2.5), logical_touch)
	# Keep the turn/score legible when the low-height mobile status row is hidden.
	# Noninteractive HUD needs physical font size, not a second tap target.
	if match_hud != null:
		# The HUD is a compact two-line status, not a fourth 100dp button.
		# Keep it legible without forcing the accepted central red logo off-screen.
		var hud_width := ceilf(76.0 * density / scale) if _use_mobile_menu() else ceilf(100.0 * density / scale)
		if _use_mobile_menu():
			# On very dense devices the full 76dp HUD could still cover the
			# right edge of the approved central masthead. Prefer a compact HUD
			# rather than painting over the canon or clipping the topbar.
			var logo_right := 1107.0 / 1672.0 * get_viewport_rect().size.x
			hud_width = minf(hud_width, maxf(logical_touch, get_viewport_rect().size.x - logo_right - 20.0))
		match_hud.custom_minimum_size = Vector2(hud_width, logical_touch)
		match_hud_label.add_theme_font_size_override("font_size", maxi(16, ceili(13.0 * density / scale)))
	for rank in perspective_ranks:
		rank.add_theme_font_size_override("font_size", logical_rank)
	# Header clearance depends on the final density-aware HUD minimum width.
	_last_reference_hotspot_viewport = Vector2.ZERO
	_refresh_selection_feedback()
	if geometry_changed:
		# HBox/ScrollContainer sizes settle after this layout pass. Refitting
		# now would reuse the PRE-rotation 44dp button height and could clip
		# the numeral at 746x280 despite unchanged DPR/font size.
		call_deferred("_refit_live_reserve_badges_after_layout", viewport_size, current_world)
	print("BLUE_SEA_TOUCH_SCALE", " logical=", logical_touch, " physical=", logical_touch * scale, " density=", density, " font_px=", logical_rank * scale)

func _refit_live_reserve_badges_after_layout(expected_size: Vector2, expected_world: int) -> void:
	await get_tree().process_frame
	# A second rotation/world switch supersedes this deferred layout job.
	# The current frame owns the only live reserve geometry and art anchors.
	if get_viewport_rect().size != expected_size or current_world != expected_world:
		return
	var font_px := _live_rank_font_px()
	for player in [1, 2]:
		var reserve := _reserve_node(player)
		for piece in reserve.get_children():
			var button := piece as Button
			var number := button.get_node_or_null("RankNumber") as Label
			if number != null and number.visible:
				_fit_reserve_rank_label(button, number, button.get_index() + 1, font_px)

# Short deterministic cues are WAV resources (not screenshots or runtime synthesis).
# Audio and vibration never run in CI headless qualification.
func _prepare_feedback() -> void:
	if DisplayServer.get_name() == "headless":
		return
	feedback_player = AudioStreamPlayer.new()
	feedback_player.name = "SharedGameplayFeedback"
	feedback_player.volume_db = -12.0
	add_child(feedback_player)

func _play_feedback(kind: String, human_action: bool = true) -> void:
	if DisplayServer.get_name() == "headless":
		return
	if sound_enabled and feedback_player != null and FEEDBACK_SOUNDS.has(kind):
		var cue: AudioStream = FEEDBACK_SOUNDS[kind]
		if cue != null:
			feedback_player.stop()
			feedback_player.stream = cue
			feedback_player.play()
	if human_action and haptics_enabled and DisplayServer.get_name() in ["Android", "iOS"]:
		# No vibration on desktop/web or AI-only turns. Duration is milliseconds.
		var duration := 28 if kind == "win" else (15 if kind == "invalid" else 9)
		Input.vibrate_handheld(duration)

func _ready() -> void:
	# On Android, SceneTree's default WM_GO_BACK_REQUEST behavior exits the
	# app before the in-game menu can protect the current unsaved round.
	# Desktop window close retains its normal operating-system semantics.
	if DisplayServer.get_name() == "Android":
		get_tree().auto_accept_quit = false
	set_process(true)
	_apply_requested_test_viewport()
	_load_preferences()
	var resumed_match := _load_match()
	_prepare_world_shell()
	_prepare_feedback()
	_create_reference_menu_hotspot()
	_create_canonical_live_logo()
	_create_perspective_layer()
	_create_orientation_overlay()
	var pirate_modal := get_node_or_null("PirateOpeningChoiceSurface/PirateOpeningChoice") as Control
	if pirate_modal != null:
		pirate_modal.visibility_changed.connect(_resume_ai_after_modal_close)
	_ensure_physical_touch_targets()
	for i in range(CELL_NAMES.size()):
		var cell := get_node("SafeArea/Landscape/Center/BoardAspect/Board/" + CELL_NAMES[i]) as Button
		cell.pressed.connect(_on_cell_pressed.bind(i))
	for player in [1, 2]:
		var reserve := _reserve_node(player)
		for i in range(reserve.get_child_count()):
			(reserve.get_child(i) as Button).pressed.connect(_on_reserve_gui_pressed.bind(player, i))
	(get_node("SafeArea/Landscape/RightRail/Actions/ActionPrimary") as Button).pressed.connect(_on_primary)
	(get_node("SafeArea/Landscape/RightRail/Actions/ActionSecondary") as Button).pressed.connect(_on_secondary)
	(get_node("SafeArea/Landscape/RightRail/Actions/ActionMenu") as Button).pressed.connect(_on_menu)
	# WorldVisuals.apply_world creates PhysicalSupport and its material texture.
	# _set_world applies those resources AND refreshes the live board/reserve;
	# refreshing first dereferences a support node absent from main.tscn.
	_set_world(current_world)
	_sync_orientation_gate()
	_update_status("ready")
	if resumed_match:
		_update_status("match resumed")
	print("BLUE_SEA_GODOT_GAME_SURFACE_READY ", get_viewport_rect().size)
	if _is_visual_capture_run():
		# This uses the REAL live game scene. It never reads/writes a player's
		# saved match, and never runs in the headless dummy renderer.
		call_deferred("_run_seven_world_visual_capture")
		return
	if DisplayServer.get_name() == "headless":
		match _headless_run_mode():
			"smoke":
				call_deferred("_run_headless_geometry_and_interaction_smoke")
			"full_match":
				call_deferred("_run_headless_full_match_smoke")
			_:
				# No game-state mutation during ordinary CI screenshot or import.
				print("BLUE_SEA_HEADLESS_RENDER_READY_NO_TEST_MUTATION")

func _prepare_world_shell() -> void:
	var center := get_node("SafeArea/Landscape/Center") as VBoxContainer
	var title := center.get_node("Title") as Label
	var topbar := HBoxContainer.new()
	topbar.name = "TopBar"
	center.add_child(topbar)
	center.move_child(topbar, 0)
	title.reparent(topbar, false)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	reference_menu_clearance = Control.new()
	reference_menu_clearance.name = "ReferenceMenuClearance"
	topbar.add_child(reference_menu_clearance)
	topbar.move_child(reference_menu_clearance, 0)
	title.add_theme_color_override("font_color", Color("#e32729"))
	world_picker = MenuButton.new()
	world_picker.name = "WorldPicker"
	world_picker.text = "МИР"
	world_picker.custom_minimum_size = Vector2(56, 44)
	topbar.add_child(world_picker)
	var popup := world_picker.get_popup()
	for i in range(WorldVisuals.WORLDS.size()):
		popup.add_radio_check_item(WorldVisuals.WORLDS[i], i)
	popup.id_pressed.connect(_prepare_world_switch_input)
	popup.id_pressed.connect(_set_world)
	# Popup may open and close within one frame; invalidate finger-down now.
	popup.about_to_popup.connect(_cancel_pending_board_touch)
	popup.about_to_popup.connect(_invalidate_input_on_modal_open)
	# The native seven-item popup cannot guarantee legible 44px rows in a
	# 746x280 landscape browser. Phone world selection reuses the live
	# touch-safe modal and the SAME _set_world game/visual binding.
	mobile_world_button = Button.new()
	mobile_world_button.name = "MobileWorldPicker"
	mobile_world_button.text = "МИР"
	mobile_world_button.custom_minimum_size = Vector2(56, 44)
	topbar.add_child(mobile_world_button)
	mobile_world_button.pressed.connect(_open_mobile_worlds)
	ai_toggle = Button.new()
	ai_toggle.name = "AIToggle"
	ai_toggle.text = "ИИ: ВКЛ" if ai_enabled else "ИИ: ВЫКЛ"
	ai_toggle.custom_minimum_size = Vector2(74, 44)
	topbar.add_child(ai_toggle)
	ai_toggle.pressed.connect(_toggle_ai)
	top_menu = MenuButton.new()
	top_menu.name = "GameMenu"
	top_menu.text = "МЕНЮ"
	top_menu.custom_minimum_size = Vector2(60, 44)
	topbar.add_child(top_menu)
	var game_popup := top_menu.get_popup()
	game_popup.about_to_popup.connect(_populate_game_menu)
	game_popup.about_to_popup.connect(_cancel_pending_board_touch)
	game_popup.about_to_popup.connect(_invalidate_input_on_modal_open)
	game_popup.id_pressed.connect(_on_game_menu_item)
	game_popup.popup_hide.connect(_resume_ai_after_modal_close)
	# Keep the top-level menu short enough for 746x280 landscape phones.
	# Three stable submenus retain the existing settings IDs and callbacks.
	rule_submenu = PopupMenu.new()
	rule_submenu.name = "RuleChoices"
	difficulty_submenu = PopupMenu.new()
	difficulty_submenu.name = "DifficultyChoices"
	persona_submenu = PopupMenu.new()
	persona_submenu.name = "PersonaChoices"
	for submenu in [rule_submenu, difficulty_submenu, persona_submenu]:
		game_popup.add_child(submenu)
		submenu.id_pressed.connect(_on_game_menu_item)
		submenu.popup_hide.connect(_resume_ai_after_modal_close)
		submenu.about_to_popup.connect(_cancel_pending_board_touch)
		submenu.about_to_popup.connect(_invalidate_input_on_modal_open)
	mobile_menu_button = Button.new()
	mobile_menu_button.name = "MobileGameMenu"
	mobile_menu_button.text = "МЕНЮ"
	mobile_menu_button.custom_minimum_size = Vector2(60, 44)
	topbar.add_child(mobile_menu_button)
	mobile_menu_button.pressed.connect(_open_mobile_menu)
	# The legacy Status row is hidden on narrow phones. A persistent, readable
	# score/turn indicator is therefore part of the LIVE topbar in every world.
	match_hud = PanelContainer.new()
	match_hud.name = "MatchHUD"
	match_hud.mouse_filter = Control.MOUSE_FILTER_IGNORE
	match_hud.custom_minimum_size = Vector2(100, 44)
	var hud_style := StyleBoxFlat.new()
	hud_style.bg_color = Color(0.02, 0.06, 0.11, 0.88)
	hud_style.border_color = Color("#d5b982")
	hud_style.set_border_width_all(1)
	hud_style.set_corner_radius_all(6)
	hud_style.set_content_margin_all(3)
	match_hud.add_theme_stylebox_override("panel", hud_style)
	topbar.add_child(match_hud)
	match_hud_label = Label.new()
	match_hud_label.name = "LiveMatchState"
	match_hud_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	match_hud_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	match_hud_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	match_hud_label.add_theme_font_size_override("font_size", 16)
	match_hud_label.add_theme_color_override("font_color", Color("#fff6d9"))
	match_hud_label.add_theme_color_override("font_outline_color", Color("#09111d"))
	match_hud_label.add_theme_constant_override("outline_size", 2)
	match_hud.add_child(match_hud_label)
	_create_mobile_menu_panel()
	_sync_mobile_menu_trigger()
	reset_dialog = ConfirmationDialog.new()
	reset_dialog.dialog_text = "Сбросить текущий матч?"
	add_child(reset_dialog)
	reset_dialog.confirmed.connect(_confirm_reset_match)
	reset_dialog.visibility_changed.connect(_resume_ai_after_modal_close)
	rules_dialog = AcceptDialog.new()
	rules_dialog.title = "Синее море — как играть"
	rules_dialog.dialog_text = _rules_help_text()
	rules_dialog.get_label().autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(rules_dialog)
	rules_dialog.visibility_changed.connect(_resume_ai_after_modal_close)
	center.get_node("WorldStrip").hide()
	var board := center.get_node("BoardAspect/Board") as GridContainer
	for i in range(CELL_NAMES.size()):
		board.move_child(board.get_node(CELL_NAMES[i]), i)
	var aspect := center.get_node("BoardAspect") as AspectRatioContainer
	aspect.custom_minimum_size = Vector2(0, 132)
	aspect.size_flags_vertical = Control.SIZE_EXPAND_FILL
	var dock := HBoxContainer.new()
	dock.name = "ReserveDock"
	dock.alignment = BoxContainer.ALIGNMENT_CENTER
	dock.custom_minimum_size = Vector2(0, 44)
	center.add_child(dock)
	center.move_child(dock, aspect.get_index() + 1)
	# One shared scroll viewport holds ONLY the current player's reserve.
	# Nine 44dp controls cannot fit in one row on a 360dp-wide phone;
	# horizontal scrolling preserves all ranks and the physical hit size.
	reserve_scroller = ScrollContainer.new()
	reserve_scroller.name = "ReserveScroll"
	reserve_scroller.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	reserve_scroller.custom_minimum_size = Vector2(0, 44)
	reserve_scroller.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	reserve_scroller.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	reserve_scroller.mouse_filter = Control.MOUSE_FILTER_STOP
	reserve_scroller.follow_focus = true
	reserve_scroller.scroll_deadzone = 8
	dock.add_child(reserve_scroller)
	reserve_scroll_save_timer = Timer.new()
	reserve_scroll_save_timer.name = "ReserveScrollIdleSave"
	reserve_scroll_save_timer.one_shot = true
	reserve_scroll_save_timer.wait_time = 0.65
	add_child(reserve_scroll_save_timer)
	reserve_scroll_save_timer.timeout.connect(_persist_idle_reserve_scroll)
	match_save_retry_timer = Timer.new()
	match_save_retry_timer.name = "MatchSaveRetry"
	match_save_retry_timer.one_shot = true
	add_child(match_save_retry_timer)
	match_save_retry_timer.timeout.connect(_retry_failed_match_save)
	if _match_save_dirty:
		# Recovery can repair a match before the shell/timer exists.
		match_save_retry_timer.start(_match_save_retry_delay(_match_save_retry_attempts))
	reserve_scroller.get_h_scroll_bar().value_changed.connect(_on_reserve_scroll_changed)
	var reserve_row := HBoxContainer.new()
	reserve_row.name = "ReserveRow"
	reserve_row.add_theme_constant_override("separation", 0)
	reserve_scroller.add_child(reserve_row)
	next_round_button = Button.new()
	next_round_button.name = "NextRound"
	next_round_button.text = "СЛЕДУЮЩИЙ РАУНД"
	next_round_button.custom_minimum_size = Vector2(176, 44)
	next_round_button.visible = false
	dock.add_child(next_round_button)
	next_round_button.pressed.connect(_on_menu)
	for player in [1, 2]:
		var rail := get_node("SafeArea/Landscape/LeftRail" if player == 1 else "SafeArea/Landscape/RightRail") as VBoxContainer
		var reserve := rail.get_node("ReserveOne" if player == 1 else "ReserveTwo") as GridContainer
		reserve.reparent(reserve_row, false)
		reserve.columns = 9
		reserve.add_theme_constant_override("h_separation", 1)
		for piece in reserve.get_children():
			(piece as Button).custom_minimum_size = Vector2(44, 44)
	get_node("SafeArea/Landscape/LeftRail").hide()
	get_node("SafeArea/Landscape/RightRail").hide()
	# Mobile/desktop is determined by the physical short edge, not by the
	# fixed 1280x720 design viewport used by canvas_items stretch.
	center.get_node("Status").visible = not _use_mobile_menu()

# The approved world-specific red logo and subtitle are not generic font text.
# Only this noninteractive masthead is sourced from the seven reference PNGs;
# the board, pieces, menu, settings and occupancy remain fully live controls.
# Portrait browser windows are not a playable 16:9 surface. Keep the match
# intact, block all hidden input, and show an explicit rotation instruction.
# This is a live UI layer, not a replacement for any approved world art.
func _create_orientation_overlay() -> void:
	# The Pirate opening is itself a CanvasLayer. A root z_index alone would
	# not cover it; use a higher CanvasLayer so portrait blocks every surface.
	var overlay_layer := CanvasLayer.new()
	overlay_layer.name = "RotateDeviceCanvasLayer"
	overlay_layer.layer = 100
	add_child(overlay_layer)
	orientation_overlay = ColorRect.new()
	orientation_overlay.name = "RotateDeviceOverlay"
	orientation_overlay.color = Color(0.015, 0.035, 0.060, 0.96)
	orientation_overlay.mouse_filter = Control.MOUSE_FILTER_STOP
	orientation_overlay.z_index = 30
	overlay_layer.add_child(orientation_overlay)
	orientation_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var message := Label.new()
	message.name = "RotateDeviceMessage"
	message.text = "СИНЕЕ МОРЕ\nПоверните телефон горизонтально"
	message.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	message.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	message.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	message.mouse_filter = Control.MOUSE_FILTER_IGNORE
	message.add_theme_font_size_override("font_size", 22)
	message.add_theme_color_override("font_color", Color("#f7eee0"))
	orientation_overlay.add_child(message)
	message.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	orientation_overlay.hide()
	orientation_overlay.visibility_changed.connect(_resume_ai_after_modal_close)

func _sync_orientation_gate() -> void:
	if orientation_overlay == null:
		return
	var physical := get_window().size
	var portrait := physical.x < physical.y
	if orientation_overlay.visible != portrait:
		# A finger-down in the old geometry cannot be replayed after rotation.
		_cancel_pending_board_touch()
		orientation_overlay.visible = portrait
		# Close transient menu state; preserve the actual match and settings.
		if portrait and mobile_menu_panel != null and mobile_menu_panel.visible:
			mobile_menu_panel.hide()

func _create_canonical_live_logo() -> void:
	canonical_live_logo = TextureRect.new()
	canonical_live_logo.name = "CanonicalLiveLogo"
	canonical_live_logo.mouse_filter = Control.MOUSE_FILTER_IGNORE
	canonical_live_logo.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	canonical_live_logo.stretch_mode = TextureRect.STRETCH_SCALE
	canonical_live_logo.z_index = 6
	add_child(canonical_live_logo)
	_layout_canonical_live_logo()

# The approved masthead is a 542x150 image. Its source-reference bounding
# box changes shape on 746x280/844x390 browsers; independently scaling x/y
# used to widen the red title by up to 50%. Keep the real image INSIDE the
# original box without changing its source aspect ratio or the live board.
static func _canonical_logo_rect(viewport: Vector2) -> Rect2:
	var source := Vector2(542.0, 150.0)
	var box := Rect2(Vector2(565.0 / 1672.0 * viewport.x, 0.0),
		Vector2(source.x / 1672.0 * viewport.x, source.y / 941.0 * viewport.y))
	var factor := minf(box.size.x / source.x, box.size.y / source.y)
	var rendered := source * maxf(0.0, factor)
	return Rect2(Vector2(box.position.x + (box.size.x - rendered.x) * 0.5,
		box.position.y + (box.size.y - rendered.y) * 0.5), rendered)

func _layout_canonical_live_logo() -> void:
	if canonical_live_logo == null:
		return
	var viewport := get_viewport_rect().size
	if viewport == _last_logo_viewport:
		return
	_last_logo_viewport = viewport
	var logo_rect := _canonical_logo_rect(viewport)
	canonical_live_logo.position = logo_rect.position
	canonical_live_logo.size = logo_rect.size

func _create_reference_menu_hotspot() -> void:
	# A transparent functional control sits precisely on the accepted image's
	# hamburger glyph; the reference pixels are never edited or flattened.
	reference_menu_hotspot = Button.new()
	reference_menu_hotspot.name = "ReferenceMenuHotspot"
	reference_menu_hotspot.flat = true
	reference_menu_hotspot.focus_mode = Control.FOCUS_NONE
	reference_menu_hotspot.mouse_filter = Control.MOUSE_FILTER_STOP
	reference_menu_hotspot.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	reference_menu_hotspot.tooltip_text = "Открыть меню"
	reference_menu_hotspot.z_index = 7
	add_child(reference_menu_hotspot)
	# Render only the accepted plate pixels, never a baked screenshot UI.
	# The Button remains the full 44dp-equivalent hit target on phones.
	reference_menu_art = TextureRect.new()
	reference_menu_art.name = "CanonicalMenuPlate"
	reference_menu_art.mouse_filter = Control.MOUSE_FILTER_IGNORE
	reference_menu_art.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	reference_menu_art.stretch_mode = TextureRect.STRETCH_SCALE
	reference_menu_hotspot.add_child(reference_menu_art)
	reference_menu_art.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	reference_menu_hotspot.pressed.connect(_on_reference_menu_hotspot_pressed)
	_layout_reference_menu_hotspot()

func _layout_reference_menu_hotspot() -> void:
	if reference_menu_hotspot == null:
		return
	var viewport := get_viewport_rect().size
	var scale := _physical_pixel_scale()
	var density := _native_touch_density()
	if viewport == _last_reference_hotspot_viewport and absf(scale - _last_reference_hotspot_scale) < 0.0001 and absf(density - _last_reference_hotspot_density) < 0.0001:
		return
	_last_reference_hotspot_viewport = viewport
	_last_reference_hotspot_scale = scale
	_last_reference_hotspot_density = density
	# Approved source pixels are 1672x941. The original menu plate occupies
	# approximately x18..106 / y13..96. Preserve its aspect-dependent position.
	var center := Vector2(62.0 / 1672.0 * viewport.x, 54.5 / 941.0 * viewport.y)
	var logical_touch := ceilf(_minimum_touch_physical_px() / scale)
	var width := maxf(logical_touch, 88.0 / 1672.0 * viewport.x)
	var height := maxf(logical_touch, 83.0 / 941.0 * viewport.y)
	var origin := Vector2(
		clampf(center.x - width * 0.5, 0.0, maxf(0.0, viewport.x - width)),
		clampf(center.y - height * 0.5, 0.0, maxf(0.0, viewport.y - height))
	)
	reference_menu_hotspot.position = origin
	reference_menu_hotspot.size = Vector2(width, height)
	# The red logo occupies x=565..1107 in the 1672px canonical reference.
	# On phones place the compact HUD to its RIGHT. The logo and the exact
	# left menu glyph remain visible; no second menu button competes for room.
	var clearance := origin.x + width + 6.0
	if _use_mobile_menu() and match_hud != null:
		var hud_width := match_hud.custom_minimum_size.x
		clearance = maxf(clearance, minf(viewport.x * 0.75, viewport.x - hud_width - 20.0))
	reference_menu_clearance.custom_minimum_size = Vector2(maxf(0.0, clearance), 0.0)

func _on_reference_menu_hotspot_pressed() -> void:
	if _modal_blocks_board_input():
		return
	# Menu is real game UI: reset requires confirmation, next appears only
	# after the round, and Pirate opening remains available in its own world.
	if _use_mobile_menu():
		_open_mobile_menu()
	else:
		_populate_game_menu()
		top_menu.get_popup().popup_centered()

# Opening ANY gameplay modal is an input-transaction boundary. A finger can
# start on the board/reserve and a second input can open the menu before the
# first finger lifts. Closing the menu must not resurrect that old placement,
# late Button.pressed, or a deferred automatic reserve scroll. Preserve the
# selected rank and the actual match; only gesture/scroll intent is invalidated.
func _invalidate_input_on_modal_open() -> void:
	_cancel_pending_board_touch()
	var now := Time.get_ticks_msec()
	if _reserve_touch_active:
		_reserve_touch_block_until_msec = now + TOUCH_MOUSE_ECHO_MS
	if _reserve_pointer_active:
		_reserve_pointer_block_until_msec = now + TOUCH_MOUSE_ECHO_MS
	_reserve_touch_active = false
	_reserve_touch_swiped = false
	_reserve_pointer_active = false
	_reserve_pointer_dragged = false
	_reserve_scroll_user_epoch += 1

# Only real UI world changes need to close an in-flight input transaction.
# Keep _set_world itself byte-exact: it remains the protected visual renderer
# used by native gameplay fixtures, and never resets a saved match.
func _prepare_world_switch_input(world: int) -> void:
	if world < 0 or world >= WorldVisuals.WORLDS.size() or world == current_world:
		return
	_cancel_pending_board_touch()
	var now := Time.get_ticks_msec()
	if _reserve_touch_active:
		_reserve_touch_block_until_msec = now + TOUCH_MOUSE_ECHO_MS
	if _reserve_pointer_active:
		_reserve_pointer_block_until_msec = now + TOUCH_MOUSE_ECHO_MS
	_reserve_touch_active = false
	_reserve_touch_swiped = false
	_reserve_pointer_active = false
	_reserve_pointer_dragged = false
	# A world change invalidates old deferred scroll/reveal requests.
	_reserve_scroll_user_epoch += 1
	selected_reserve = -1
	selected_cell = -1

func _set_world(world: int) -> void:
	if world < 0 or world >= WorldVisuals.WORLDS.size():
		return
	current_world = world
	_save_preferences()
	world_visuals.apply_world(self, current_world)
	if reference_menu_art != null:
		# All seven exact source plates are now visible on the same live button.
		# The six supported-world scenery derivatives omit this one region
		# to avoid doubled menu glyphs at 746x280 and other aspect ratios.
		var menu_path := "res://assets/a5_menu_plates/world_%02d.png" % current_world
		reference_menu_art.texture = ResourceLoader.load(menu_path, "Texture2D", ResourceLoader.CACHE_MODE_IGNORE) as Texture2D
		assert(reference_menu_art.texture != null, "Missing canonical live menu: " + menu_path)
	if canonical_live_logo != null:
		var logo_path := "res://assets/a5_live_logos/world_%02d.png" % current_world
		canonical_live_logo.texture = ResourceLoader.load(logo_path, "Texture2D", ResourceLoader.CACHE_MODE_IGNORE) as Texture2D
		# Invisible HBox children still consume width. Hide the fallback label
		# entirely when the exact approved red masthead texture is present.
		var title := get_node("SafeArea/Landscape/Center/TopBar/Title") as Label
		title.visible = canonical_live_logo.texture == null
		assert(canonical_live_logo.texture != null, "Missing exact-canon masthead: " + logo_path)
	if world_picker != null:
		var popup := world_picker.get_popup()
		for i in range(popup.item_count):
			popup.set_item_checked(i, i == current_world)
	_refresh_surface()
	_refresh_perspective_layer()

func _toggle_ai() -> void:
	ai_enabled = not ai_enabled
	# Taking control of P2 from a human invalidates that human's selected
	# reserve/cell and any held board gesture. The AI must start from its own
	# live legality evaluation, never from an invisible old human selection.
	if ai_enabled and turn == 2:
		_cancel_pending_board_touch()
		selected_reserve = -1
		selected_cell = -1
	_save_preferences()
	ai_toggle.text = "ИИ: ВКЛ" if ai_enabled else "ИИ: ВЫКЛ"
	# Opponent reserve must disappear immediately when AI control is enabled.
	_refresh_surface()
	_queue_ai_turn_if_ready()

func _resume_ai_after_modal_close() -> void:
	# Modal visibility changes invalidate a held board tap permanently, even
	# if the overlay opens AND closes before the next _process frame. The
	# finger-up event must not spend a rank on the now-uncovered board.
	_cancel_pending_board_touch()
	# Both an already-queued turn and a newly enabled AI may have been paused
	# by a mobile menu, rules dialog, confirmation, portrait gate or Pirate UI.
	# Only the LAST modal to close can restart it; the deferred turn rechecks
	# visibility immediately before committing any gameplay state.
	if not _modal_blocks_board_input():
		call_deferred("_queue_ai_turn_if_ready")

func _queue_ai_turn_if_ready() -> void:
	if _is_visual_capture_run():
		return
	if _ai_turn_queued or not ai_enabled or game_over or turn != 2 or _modal_blocks_board_input():
		return
	_ai_turn_queued = true
	call_deferred("_play_ai_turn")

# The production strategy is allowed to fail, but the active match must not
# become stuck in an unbounded deferred-AI retry. Validate the entire proposal
# BEFORE any rank/cell indexing, then use the exact live legality predicate.
# Deterministic rank/cell order is an emergency fallback, not a new persona.
func _resolve_ai_move(proposed: Dictionary) -> Dictionary:
	if proposed.has("rank") and proposed.has("cell"):
		var raw_rank = proposed["rank"]
		var raw_cell = proposed["cell"]
		if typeof(raw_rank) == TYPE_INT and typeof(raw_cell) == TYPE_INT:
			var rank: int = raw_rank
			var cell: int = raw_cell
			if _is_legal_move(2, rank, cell):
				return {"rank": rank, "cell": cell}
	for rank in range(1, 10):
		for cell in range(9):
			if _is_legal_move(2, rank, cell):
				push_warning("Blue Sea AI strategy returned an invalid move; using legal fallback")
				return {"rank": rank, "cell": cell}
	return {}

func _play_ai_turn() -> void:
	# A modal can open after the deferred action was scheduled. Do not let
	# the opponent silently change the game while a menu is being read.
	_ai_turn_queued = false
	if not ai_enabled or game_over or turn != 2 or _modal_blocks_board_input():
		return
	var proposed: Dictionary = ai_engine.choose_move(board_stacks, reserve_available, 2, current_rule, ai_difficulty, ai_persona)
	# If the strategy returns an empty, malformed or stale proposal despite
	# legal choices, commit a legal fallback in this SAME turn. The previous
	# error-and-return path requeued the same impossible AI action every frame.
	# This does not replace strategy scoring during ordinary successful play.
	var move: Dictionary = _resolve_ai_move(proposed)
	if move.is_empty():
		# Fail closed if the two independent legality paths ever disagree.
		# Hand control to local P2 instead of endlessly retrying an AI error.
		if _has_legal_move(2):
			push_error("Blue Sea AI legality disagreement; switching to local two-player control")
			ai_enabled = false
			_save_preferences()
			_refresh_surface()
			return
		# No move exists under the live shared rule predicate. Only here may
		# the AI yield the turn (or end a mutually blocked round).
		blocked_player = 2
		turn = 1
		selected_reserve = -1
		selected_cell = -1
		if not _has_legal_move(1):
			game_over = true
			round_draw = true
			blocked_player = 0
		_refresh_surface()
		_save_match()
		_update_status("AI blocked; human continues" if not game_over else "no legal moves: draw")
		return
	selected_reserve = int(move["rank"]) - 1
	selected_cell = int(move["cell"])
	assert(_is_legal_move(2, selected_reserve + 1, selected_cell))
	_on_primary()

static func _mobile_profile(backend: String, short_side: int, display_scale: float, touch_available: bool) -> bool:
	# Pure classifier also allows headless fixture testing of native exports.
	if backend == "Android" or backend == "iOS":
		return true
	if short_side <= 360:
		return true
	# Many accepted 16:9 phone browsers have a 390-430 CSS-pixel short
	# edge (844x390, 932x430). The old 360px cutoff silently routed
	# those real touch phones into desktop PopupMenus with tiny rows,
	# competing with the canonical masthead and hiding the live score.
	# Keep pointer-only desktop windows on their existing route.
	return backend == "web" and touch_available and float(short_side) / maxf(1.0, display_scale) <= 480.0

func _use_mobile_menu() -> bool:
	# Native phone exports report hardware pixels, not 360px CSS viewports.
	var physical := get_window().size
	return _mobile_profile(DisplayServer.get_name(), mini(physical.x, physical.y), DisplayServer.screen_get_scale(), DisplayServer.is_touchscreen_available())

func _create_mobile_menu_panel() -> void:
	mobile_menu_panel = PanelContainer.new()
	mobile_menu_panel.name = "MobileSettingsOverlay"
	mobile_menu_panel.mouse_filter = Control.MOUSE_FILTER_STOP
	mobile_menu_panel.z_index = 20
	add_child(mobile_menu_panel)
	mobile_menu_panel.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var style := StyleBoxFlat.new()
	style.bg_color = Color("#101c29")
	style.set_content_margin_all(8)
	mobile_menu_panel.add_theme_stylebox_override("panel", style)
	var column := VBoxContainer.new()
	column.name = "MobileMenuColumn"
	mobile_menu_panel.add_child(column)
	mobile_menu_heading = Label.new()
	mobile_menu_heading.name = "MobileMenuHeading"
	mobile_menu_heading.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	column.add_child(mobile_menu_heading)
	var scroller := ScrollContainer.new()
	scroller.name = "MobileMenuScroll"
	scroller.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroller.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	column.add_child(scroller)
	mobile_menu_list = VBoxContainer.new()
	mobile_menu_list.name = "MobileMenuChoices"
	mobile_menu_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroller.add_child(mobile_menu_list)
	mobile_menu_panel.hide()
	mobile_menu_panel.visibility_changed.connect(_resume_ai_after_modal_close)

func _sync_mobile_menu_trigger() -> void:
	if mobile_menu_button == null:
		return
	var phone := _use_mobile_menu()
	# Recompute on every physical resize/rotation; hiding the status frees
	# vertical space for the live board and reserve at 746x280.
	var status := get_node("SafeArea/Landscape/Center/Status") as Label
	if status.visible == phone:
		status.visible = not phone
	# The accepted reference already contains a functional 44dp menu glyph.
	# Four more mobile topbar buttons + HUD cover the central red masthead at
	# 746x280. Route world and AI settings through that SAME real menu.
	mobile_menu_button.visible = false
	mobile_world_button.visible = false
	world_picker.visible = not phone
	top_menu.visible = not phone
	ai_toggle.visible = not phone
	var scale := _physical_pixel_scale()
	if phone and mobile_menu_panel.visible and (absf(scale - _mobile_menu_last_scale) > 0.0001 or absf(_native_touch_density() - _mobile_menu_last_density) > 0.0001):
		_render_mobile_menu_page(_mobile_menu_page)
	elif not phone and mobile_menu_panel.visible:
		mobile_menu_panel.hide()

func _mobile_menu_add(label: String, item_id: int, disabled: bool = false) -> void:
	var button := Button.new()
	button.name = "MobileChoice_%d" % item_id
	button.text = label
	button.disabled = disabled
	button.focus_mode = Control.FOCUS_NONE
	button.custom_minimum_size = Vector2(0, ceilf(_minimum_touch_physical_px() / _physical_pixel_scale()))
	button.add_theme_font_size_override("font_size", maxi(16, ceili(14.0 * _native_touch_density() / _physical_pixel_scale())))
	button.pressed.connect(_on_mobile_menu_action.bind(item_id))
	mobile_menu_list.add_child(button)

# A real phone-landscape tutorial uses the same scrollable, 44dp-safe modal as
# settings. The desktop AcceptDialog remains unchanged. No tutorial page is a
# flattened screenshot or a second game board.
func _mobile_menu_add_explanation(copy: String) -> void:
	var explanation := Label.new()
	explanation.name = "TutorialExplanation"
	explanation.text = copy
	explanation.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	explanation.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	explanation.mouse_filter = Control.MOUSE_FILTER_IGNORE
	explanation.add_theme_font_size_override("font_size", maxi(16, ceili(14.0 * _native_touch_density() / _physical_pixel_scale())))
	explanation.add_theme_color_override("font_color", Color("#f3e8ce"))
	mobile_menu_list.add_child(explanation)

func _render_mobile_menu_page(page: String) -> void:
	_mobile_menu_page = page
	_mobile_menu_last_scale = _physical_pixel_scale()
	_mobile_menu_last_density = _native_touch_density()
	for child in mobile_menu_list.get_children():
		mobile_menu_list.remove_child(child)
		child.queue_free()
	mobile_menu_heading.add_theme_font_size_override("font_size", maxi(18, ceili(16.0 * _native_touch_density() / _physical_pixel_scale())))
	mobile_menu_heading.text = "СИНЕЕ МОРЕ · " + page.to_upper()
	if page == "main":
		_mobile_menu_add("Закрыть", -2)
		# The current world is a real, persistent gameplay configuration. At 746x280
		# it must be visible without entering a second scrollable settings page.
		_mobile_menu_add("Мир · " + WorldVisuals.WORLDS[current_world], 105)
		_mobile_menu_add("ИИ: " + ("ВКЛ" if ai_enabled else "ВЫКЛ"), 106)
		_mobile_menu_add("Отменить ход", 108, _undo_steps() == 0)
		_mobile_menu_add("Сбросить матч…", 1)
		if _match_save_dirty:
			_mobile_menu_add("Повторить сохранение", 107)
		_mobile_menu_add("Как играть", 3)
		if current_world == 1:
			_mobile_menu_add("История · Рифы", 4)
		if game_over:
			_mobile_menu_add("Новый матч" if match_winner != 0 else "Следующий раунд", 2)
		var locked := moves != 0 or round_number != 1 or game_over or match_score[0] != 0 or match_score[1] != 0
		_mobile_menu_add("Правила · " + current_rule, 100, locked)
		# Expose the selected strategy/persona on the main phone menu; the
		# existing submenus still own all edits and checked-state semantics.
		_mobile_menu_add("Сложность ИИ · " + ["Лёгкая", "Обычная", "Сложная"][ai_difficulty - 1], 101)
		_mobile_menu_add("Характер ИИ · " + ["Баланс", "Атака", "Защита"][ai_persona], 102)
		_mobile_menu_add("Звук: " + ("ВКЛ" if sound_enabled else "ВЫКЛ"), 103)
		_mobile_menu_add("Вибрация: " + ("ВКЛ" if haptics_enabled else "ВЫКЛ"), 104)
	elif page == "worlds":
		_mobile_menu_add("← Назад", -1)
		for world_id in range(WorldVisuals.WORLDS.size()):
			var mark := " ✓" if world_id == current_world else ""
			_mobile_menu_add(WorldVisuals.WORLDS[world_id] + mark, 500 + world_id)
	elif page == "rules":
		_mobile_menu_add("← Назад", -1)
		for id in range(3):
			_mobile_menu_add(["C", "D", "CD"][id] + (" ✓" if current_rule == ["C", "D", "CD"][id] else ""), 300 + id)
	elif page == "difficulty":
		_mobile_menu_add("← Назад", -1)
		for id in range(1, 4):
			_mobile_menu_add(["Лёгкая", "Обычная", "Сложная"][id - 1] + (" ✓" if ai_difficulty == id else ""), 399 + id)
	elif page == "persona":
		_mobile_menu_add("← Назад", -1)
		for id in range(3):
			_mobile_menu_add(["Сбалансированный", "Агрессивный", "Защитный"][id] + (" ✓" if ai_persona == id else ""), 410 + id)
	elif page == "tutorial_1":
		_mobile_menu_add("← Меню", -1)
		_mobile_menu_add_explanation("1 / 4 · ВЫБЕРИТЕ ФИГУРУ\nПод доской находится резерв только того, чей сейчас ход. Нажмите фигуру ранга 1–9. Большие ранги сильнее, но каждый ранг можно использовать лишь однажды за раунд. Тусклая фигура сейчас не имеет допустимого хода. Список листается вбок.")
		_mobile_menu_add("Далее · игровая доска →", 701)
	elif page == "tutorial_2":
		_mobile_menu_add("← Назад", 700)
		_mobile_menu_add_explanation("2 / 4 · СДЕЛАЙТЕ ХОД\nПосле выбора фигуры подсвечиваются допустимые клетки. Коснитесь клетки на доске. Пустая клетка доступна; чужую фигуру можно накрыть только СТРОГО большим рангом. Свои фигуры накрывать нельзя.")
		_mobile_menu_add("Далее · победа →", 702)
	elif page == "tutorial_3":
		_mobile_menu_add("← Назад", 701)
		_mobile_menu_add_explanation("3 / 4 · ПОБЕДИТЕ\nC: три своих верхних фигуры в линию, стопка не глубже двух. D: три своих верхних ранга строго возрастают или убывают, глубокие стопки разрешены. CD: линия по D и ограничение стопки по C. Матч — до трёх побед.")
		_mobile_menu_add("Далее · управление →", 703)
	elif page == "tutorial_4":
		_mobile_menu_add("← Назад", 702)
		_mobile_menu_add_explanation("4 / 4 · ИГРАЙТЕ\nМир, сложность и характер ИИ меняются в меню. Отмена хода находится в меню (в одиночной игре отменяет пару человек+ИИ). Сброс требует подтверждения; кнопка продолжения появляется только после раунда. Партия сохраняется автоматически. На Android кнопка «Назад» управляет меню без сброса партии. Попробуйте выбрать доступную фигуру: игра подсветит законные ходы, но НЕ поставит её за вас.")
		_mobile_menu_add("Показать допустимые клетки", 704, game_over or (ai_enabled and turn == 2) or not _has_legal_move(turn))
		_mobile_menu_add("Закрыть обучение", -2)
	elif page == "confirm_reset":
		# Native ConfirmationDialog buttons can be <44 physical px at 746x280.
		# Reuse the same full-screen modal and touch-safe choice factory.
		mobile_menu_heading.text = "СБРОСИТЬ ТЕКУЩИЙ МАТЧ?"
		_mobile_menu_add("Отмена · продолжить игру", -2)
		_mobile_menu_add("Да · сбросить матч и счёт", 600)

func _open_mobile_menu() -> void:
	if mobile_menu_panel == null or not _use_mobile_menu() or _modal_blocks_board_input():
		return
	_invalidate_input_on_modal_open()
	_render_mobile_menu_page("main")
	mobile_menu_panel.show()

func _open_mobile_worlds() -> void:
	if mobile_menu_panel == null or not _use_mobile_menu() or _modal_blocks_board_input():
		return
	_invalidate_input_on_modal_open()
	_render_mobile_menu_page("worlds")
	mobile_menu_panel.show()

func _on_mobile_menu_action(id: int) -> void:
	if id == -2:
		mobile_menu_panel.hide()
	elif id == -1:
		_render_mobile_menu_page("main")
	elif id == 105:
		_render_mobile_menu_page("worlds")
	elif id == 3:
		# Phone tutorial stays inside the real, scrollable settings modal.
		# Native AcceptDialog cannot guarantee a readable/usable 746x280 page.
		_render_mobile_menu_page("tutorial_1")
	elif id >= 700 and id <= 703:
		_render_mobile_menu_page("tutorial_%d" % (1 if id == 700 else id - 699))
	elif id == 704:
		# Tutorial practice is idempotent. A player may have selected rank 9
		# before reading help; choosing "show legal cells" must NOT toggle it
		# off or silently replace it with rank 1. This is selection only.
		mobile_menu_panel.hide()
		if not game_over and not (ai_enabled and turn == 2):
			var practice_index := -1
			if selected_reserve >= 0 and selected_reserve < 9 and _rank_has_legal_cell(turn, selected_reserve + 1):
				practice_index = selected_reserve
			else:
				for rank in range(1, 10):
					if _rank_has_legal_cell(turn, rank):
						practice_index = rank - 1
						break
			if practice_index >= 0:
				if selected_reserve == practice_index:
					# No stale keyboard cell target survives the help overlay.
					selected_cell = -1
					_refresh_selection_feedback()
				else:
					_on_reserve_pressed(turn, practice_index)
				# At 746x280/high DPI, the selected rank can be outside the
				# horizontally scrolled reserve. Reveal the real live button
				# after layout, never moving or consuming any game piece.
				call_deferred("_ensure_tutorial_rank_visible", turn, practice_index,
					current_world, moves, round_number, _reserve_scroll_user_epoch)
	elif id == 106:
		# The menu remains modal until the player closes it; a newly enabled
		# AI cannot commit a hidden move behind the settings page.
		_toggle_ai()
		_render_mobile_menu_page("main")
	elif id == 100:
		_render_mobile_menu_page("rules")
	elif id == 101:
		_render_mobile_menu_page("difficulty")
	elif id == 102:
		_render_mobile_menu_page("persona")
	elif id == 103 or id == 104:
		_on_game_menu_item(id)
		_render_mobile_menu_page("main")
	elif id == 600:
		# A reset is consequential: accept it only from the visible confirmation.
		if mobile_menu_panel.visible and _mobile_menu_page == "confirm_reset":
			mobile_menu_panel.hide()
			_confirm_reset_match()
	elif id >= 500 and id < 500 + WorldVisuals.WORLDS.size():
		# Switching the visual world never resets board stacks, reserve, turn,
		# score or AI. The shared gameplay remains authoritative.
		mobile_menu_panel.hide()
		_prepare_world_switch_input(id - 500)
		_set_world(id - 500)
	else:
		# Close the in-scene modal before invoking the existing settings contract.
		# This keeps reset/help/campaign dialogs interactive and preserves rules.
		mobile_menu_panel.hide()
		_on_game_menu_item(id)

# A deferred scroll must never overwrite a player's later manual scroll,
# world switch, AI turn or rank choice. It is only for the tutorial's exact
# just-selected rank, after the in-scene modal has finished hiding.
func _ensure_tutorial_rank_visible(player: int, rank_index: int, world: int,
		move_count: int, round_id: int, user_epoch: int) -> void:
	await get_tree().process_frame
	if reserve_scroller == null or not reserve_scroller.visible or mobile_menu_panel.visible:
		return
	if turn != player or current_world != world or moves != move_count or selected_reserve != rank_index:
		return
	# The player may already have dragged the reserve after dismissing help.
	# That newer explicit input outranks our delayed convenience scroll.
	if not _reserve_scroll_request_current(player, world, round_id, move_count, rank_index, user_epoch):
		return
	if game_over or player < 1 or player > 2 or rank_index < 0 or rank_index >= 9:
		return
	var reserve := _reserve_node(player)
	if not reserve.visible or reserve.get_child_count() <= rank_index:
		return
	var button := reserve.get_child(rank_index) as Button
	if button != null and button.visible:
		reserve_scroller.ensure_control_visible(button)

func _configure_mobile_popup(menu: PopupMenu) -> void:
	# PopupMenu has built-in scrolling when max_size clips the item list.
	# Keep it inside the actual physical landscape window, including 746x280.
	menu.max_size = Vector2i(0, maxi(180, get_window().size.y - 12))
	menu.add_theme_font_size_override("font_size", 17)
	menu.add_theme_constant_override("v_separation", 22)

func _populate_game_menu() -> void:
	var popup := top_menu.get_popup()
	popup.clear() # Keep the three stable child PopupMenu nodes and signals.
	for menu in [popup, rule_submenu, difficulty_submenu, persona_submenu]:
		_configure_mobile_popup(menu)
	popup.add_item("Отменить ход", 108)
	popup.set_item_disabled(popup.item_count - 1, _undo_steps() == 0)
	popup.add_item("Сбросить матч…", 1)
	if _match_save_dirty:
		popup.add_item("Повторить сохранение", 107)
	popup.add_item("Как играть · правила C/D/CD", 3)
	# The original WorldStrip/Pirate trigger is hidden in the seven-world shell.
	# Restore access to the existing qualified opening controller via top menu.
	if current_world == 1:
		popup.add_item("История · Рифы", 4)
	if game_over:
		# The same action starts a NEW MATCH after the third win, not another
		# round. Match the mobile menu and live terminal Next button exactly.
		popup.add_item("Новый матч" if match_winner != 0 else "Следующий раунд", 2)
	popup.add_separator()
	var can_change := moves == 0 and round_number == 1 and not game_over and match_score[0] == 0 and match_score[1] == 0
	rule_submenu.clear()
	for mode_id in range(3):
		var mode: String = ["C", "D", "CD"][mode_id]
		rule_submenu.add_radio_check_item(mode, 300 + mode_id)
		rule_submenu.set_item_checked(rule_submenu.item_count - 1, current_rule == mode)
		rule_submenu.set_item_disabled(rule_submenu.item_count - 1, not can_change)
	popup.add_submenu_node_item("Правила · " + current_rule, rule_submenu, 100)
	popup.set_item_disabled(popup.item_count - 1, not can_change)
	difficulty_submenu.clear()
	var difficulties := ["лёгкая", "обычная", "сложная"]
	for level in range(1, 4):
		difficulty_submenu.add_radio_check_item(difficulties[level - 1], 399 + level)
		difficulty_submenu.set_item_checked(difficulty_submenu.item_count - 1, ai_difficulty == level)
	popup.add_submenu_node_item("ИИ сложность · " + difficulties[ai_difficulty - 1], difficulty_submenu, 101)
	persona_submenu.clear()
	var personas := ["сбалансированный", "агрессивный", "защитный"]
	for persona_id in range(3):
		persona_submenu.add_radio_check_item(personas[persona_id], 410 + persona_id)
		persona_submenu.set_item_checked(persona_submenu.item_count - 1, ai_persona == persona_id)
	popup.add_submenu_node_item("ИИ характер · " + personas[ai_persona], persona_submenu, 102)
	popup.add_separator()
	popup.add_check_item("Звук", 103)
	popup.set_item_checked(popup.item_count - 1, sound_enabled)
	popup.add_check_item("Вибрация", 104)
	popup.set_item_checked(popup.item_count - 1, haptics_enabled)

func _on_game_menu_item(id: int) -> void:
	if id == 108:
		_undo_last_move()
	elif id == 107:
		_retry_unsaved_match_on_request()
	elif id == 1:
		if _use_mobile_menu():
			_render_mobile_menu_page("confirm_reset")
			mobile_menu_panel.show()
		else:
			_invalidate_input_on_modal_open()
			reset_dialog.popup_centered()
	elif id == 3:
		# Scaled window width keeps the help readable without obscuring a whole phone screen.
		rules_dialog.get_label().add_theme_font_size_override("font_size", maxi(16, ceili(14.0 / _physical_pixel_scale())))
		_invalidate_input_on_modal_open()
		rules_dialog.popup_centered_ratio(0.90)
	elif id == 2 and game_over:
		_on_menu()
	elif id == 4 and current_world == 1:
		var pirate_surface := get_node_or_null("PirateOpeningChoiceSurface")
		if pirate_surface != null:
			_invalidate_input_on_modal_open()
			pirate_surface.call("show_opening_choice")
	elif id == 103:
		sound_enabled = not sound_enabled
		_save_preferences()
		if sound_enabled:
			_play_feedback("select", false)
	elif id == 104:
		haptics_enabled = not haptics_enabled
		_save_preferences()
	elif id >= 300 and id <= 302:
		if moves != 0 or round_number != 1 or game_over or match_score[0] != 0 or match_score[1] != 0:
			_update_status("Правила можно менять только до первого хода матча")
			return
		current_rule = ["C", "D", "CD"][id - 300]
		_save_preferences()
		_save_match()
		_update_status("Правила: " + current_rule)
	elif id >= 400 and id <= 402:
		ai_difficulty = id - 399
		_save_preferences()
		_update_status("ИИ сложность: %d" % ai_difficulty)
	elif id >= 410 and id <= 412:
		ai_persona = id - 410
		_save_preferences()
		_update_status("ИИ характер: %d" % ai_persona)

func _confirm_reset_match() -> void:
	_play_feedback("select")
	match_score = [0, 0]
	match_winner = 0
	round_number = 1
	_reset_round()

# A live DPR/zoom change must not leave reserve numerals at their original
# font size while the perspective board uses the new physical density.
# These helpers change text only; rank silhouettes and 44dp hit targets stay
# exactly as before. They are shared by all seven worlds.
func _live_rank_font_px() -> int:
	return maxi(16, ceili(14.0 * _native_touch_density() / _physical_pixel_scale()))

func _live_rank_outline_px() -> int:
	return maxi(4, ceili(3.0 * _native_touch_density() / _physical_pixel_scale()))

func _sync_live_reserve_rank_typography() -> void:
	var font_px := _live_rank_font_px()
	var outline_px := _live_rank_outline_px()
	if font_px == _last_reserve_rank_font_px and outline_px == _last_reserve_rank_outline_px:
		return
	_last_reserve_rank_font_px = font_px
	_last_reserve_rank_outline_px = outline_px
	# Do not call _refresh_surface(): it changes scroll/selection timing and
	# may load large art textures. Update only existing, noninteractive labels.
	for player in [1, 2]:
		var reserve := _reserve_node(player)
		for piece in reserve.get_children():
			var reserve_button := piece as Button
			var number := reserve_button.get_node_or_null("RankNumber") as Label
			if number != null:
				number.add_theme_font_size_override("font_size", font_px)
				number.add_theme_constant_override("outline_size", outline_px)
				# A DPR change can make a previously narrow stone/beacon badge
				# smaller than its new number. Fit the same live label in place.
				_fit_reserve_rank_label(reserve_button, number, reserve_button.get_index() + 1, font_px)

# Reference-derived Atlantis/Sand/Night medallions are only 26-30% of a
# reserve button. At 746x280 that is 11-13px, less than the 16px live
# numeral. Keep each world's ORIGINAL vertical badge CENTER but enlarge
# its transparent label box (never the art, touch target or rank glyph).
# Rebuild from canonical anchors each time: otherwise repeated DPR changes
# progressively enlarge the label and can drift into the adjacent rune/art.
func _reserve_rank_label_band(rank: int) -> Vector2:
	match current_world:
		1:
			return Vector2(0.0, 0.48)  # Pirate: upper brass badge.
		2:
			return _atlantis_rank_band(rank)
		3:
			return Vector2(0.59, 1.0)  # Gods: lower medallion.
		4:
			return _sand_rank_band(rank)
		5:
			return _night_rank_band(rank)
		6:
			return Vector2(0.68, 1.0)  # North: lower rune-free tier.
	return Vector2(0.0, 1.0)  # Void: full glass dome.

func _fit_reserve_rank_label(button: Button, number: Label, rank: int, font_px: int) -> void:
	if rank < 1 or rank > 9:
		return
	var source_band := _reserve_rank_label_band(rank)
	# The first refresh can precede layout; custom_minimum_size already
	# encodes the safe physical touch target, so this is never a zero divide.
	var button_height := maxf(1.0, maxf(button.size.y, button.custom_minimum_size.y))
	var needed_fraction := minf(1.0, 1.25 * float(font_px) / button_height)
	var height_fraction := maxf(source_band.y - source_band.x, needed_fraction)
	var center_fraction := (source_band.x + source_band.y) * 0.5
	var top_fraction := clampf(center_fraction - height_fraction * 0.5, 0.0, 1.0 - height_fraction)
	number.anchor_top = top_fraction
	number.anchor_bottom = top_fraction + height_fraction
	# These are the SAME noninteractive labels. No scroll, world reload,
	# texture decode, selected-rank mutation or input hit-area adjustment.

func _set_piece_badge(button: Button, texture: Texture2D, rank: int) -> void:
	button.text = ""
	button.icon = null
	button.clip_contents = true
	var art := button.get_node_or_null("RankArt") as TextureRect
	if art == null:
		art = TextureRect.new()
		art.name = "RankArt"
		art.mouse_filter = Control.MOUSE_FILTER_IGNORE
		art.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		art.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT
		button.add_child(art)
		art.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	art.texture = texture
	art.visible = texture != null
	var number := button.get_node_or_null("RankNumber") as Label
	if number == null:
		number = Label.new()
		number.name = "RankNumber"
		number.mouse_filter = Control.MOUSE_FILTER_IGNORE
		number.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		number.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		number.add_theme_color_override("font_color", Color("#fff8df"))
		number.add_theme_color_override("font_outline_color", Color("#142332"))
		button.add_child(number)
		number.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	# A browser DPR/Android display-scale change can occur without a move or
	# world switch. Recompute on every actual badge refresh, not only creation.
	number.add_theme_font_size_override("font_size", _live_rank_font_px())
	number.add_theme_constant_override("outline_size", _live_rank_outline_px())
	number.text = str(rank) if rank > 0 else ""
	number.visible = rank > 0
	# Pirate cap numerals belong on the top badge, not over the gold anchor.
	# The same live number remains legible for both reserve and board pieces.
	number.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	# Source-derived Gods beings carry the live number on the LOWER medallion.
	number.anchor_top = 0.59 if current_world == 3 else 0.0
	number.anchor_bottom = 0.48 if current_world == 1 else 1.0
	# Northern Sea's actual rune is engraved on the upper face. Keep the
	# numeric rank in the lower band, rather than painting over that rune.
	# This changes only the noninteractive label; button hit boxes stay equal.
	if current_world == 6:
		number.anchor_top = 0.68
		number.anchor_bottom = 1.0
	# Atlantis trident artwork stays visible. The live rank occupies the top
	# stone tier, following each rank's increasing silhouette height.
	if current_world == 2 and rank > 0:
		var rank_band := _atlantis_rank_band(rank)
		number.anchor_top = rank_band.x
		number.anchor_bottom = rank_band.y
	# Night Sea: replace concept-screen numerals with the actual game rank,
	# placed on each source-derived beacon's dark lower medallion.
	if current_world == 5 and rank > 0:
		var night_band := _night_rank_band(rank)
		number.anchor_top = night_band.x
		number.anchor_bottom = night_band.y
	# Sand pyramids carry ankh artwork on the door; put live rank on the
	# upper limestone tier, rising with the strictly growing silhouette.
	if current_world == 4 and rank > 0:
		var sand_band := _sand_rank_band(rank)
		number.anchor_top = sand_band.x
		number.anchor_bottom = sand_band.y
	if rank > 0:
		_fit_reserve_rank_label(button, number, rank, _live_rank_font_px())

func _atlantis_rank_band(rank: int) -> Vector2:
	assert(rank >= 1 and rank <= 9)
	var center := 0.70 - 0.049 * float(rank - 1)
	return Vector2(center - 0.15, center + 0.15)

func _sand_rank_band(rank: int) -> Vector2:
	assert(rank >= 1 and rank <= 9)
	var center := 0.68 - 0.047 * float(rank - 1)
	return Vector2(center - 0.14, center + 0.14)

func _night_rank_band(rank: int) -> Vector2:
	assert(rank >= 1 and rank <= 9)
	var center := 0.803 - 0.0063 * float(rank - 1)
	return Vector2(center - 0.13, center + 0.13)

func _apply_requested_test_viewport() -> void:
	var args := OS.get_cmdline_user_args()
	for arg in args:
		if arg.begins_with("--nd-test-size="):
			var parts := arg.trim_prefix("--nd-test-size=").split("x")
			if parts.size() == 2:
				var requested := Vector2i(int(parts[0]), int(parts[1]))
				if requested.x > 0 and requested.y > 0:
					get_window().content_scale_size = requested
					get_window().size = requested
					print("BLUE_SEA_TEST_VIEWPORT_REQUEST ", requested)

# Keyboard parity with the nine live reserve buttons and perspective cells.
# Digits 1..9 select a rank; arrows move a visible 3x3 cursor; Enter commits.
# These call the SAME human handlers as touch. No keyboard-only game engine.
func _select_keyboard_rank(index: int) -> void:
	if game_over or (ai_enabled and turn == 2) or _modal_blocks_board_input() or index < 0 or index >= 9:
		return
	# A consumed rank is still addressable by its keyboard digit. Never let
	# that failed selection silently retain an earlier, playable rank: the
	# next Enter/cell tap could otherwise commit an unintended piece.
	if not reserve_available[turn - 1][index]:
		_on_secondary()
		_play_feedback("invalid")
		_update_status("piece already played")
		return
	_on_reserve_pressed(turn, index)
	# At native phone density the nine equal-size 44dp targets exceed a
	# 360dp viewport. Keyboard-selected ranks 8/9 must be brought into view,
	# just as they are reachable by manual horizontal touch scrolling.
	# A keyboard-triggered rank reveal is also an automatic scroll. Capture the
	# SAME input epoch as tutorial and turn-scroll restore: a later finger swipe
	# or mouse-wheel action must take precedence even if rank/turn are unchanged.
	call_deferred("_reveal_keyboard_rank", turn, index, current_world,
		round_number, moves, _reserve_scroll_user_epoch)

func _reveal_keyboard_rank(player: int, index: int, world: int, round_id: int,
		move_count: int, user_epoch: int) -> void:
	# Deferred callbacks can run after a new world, round, turn, selected rank
	# or manual reserve scroll. Reuse the one shared validity predicate rather
	# than a weaker keyboard-only rule. No game state or rank is modified.
	if reserve_scroller == null or game_over or _modal_blocks_board_input():
		return
	if player < 1 or player > 2 or index < 0 or index >= 9:
		return
	if not _reserve_scroll_request_current(player, world, round_id, move_count,
			index, user_epoch):
		return
	var reserve := _reserve_node(player)
	if not reserve.visible or reserve.get_child_count() <= index:
		return
	var button := reserve.get_child(index) as Button
	if button != null and button.visible:
		reserve_scroller.ensure_control_visible(button)

func _move_keyboard_cell(dx: int, dy: int) -> void:
	if game_over or (ai_enabled and turn == 2) or _modal_blocks_board_input():
		return
	if selected_cell < 0:
		selected_cell = 4
	else:
		var col := selected_cell % 3
		var row := int(selected_cell / 3)
		selected_cell = clampi(row + dy, 0, 2) * 3 + clampi(col + dx, 0, 2)
	_refresh_selection_feedback()
	_update_status("keyboard cell %d" % selected_cell)

func _unhandled_key_input(event: InputEvent) -> void:
	if not (event is InputEventKey) or not event.pressed or event.echo:
		return
	# Android Back is often delivered as Escape before (or instead of) the
	# window notification. The shared handler deduplicates the OS echo.
	if DisplayServer.get_name() == "Android" and event.keycode in [KEY_ESCAPE, KEY_BACKSPACE]:
		_handle_mobile_back()
		get_viewport().set_input_as_handled()
		return
	# Modal help/confirmation/campaign UI owns its keys; never commit a hidden move.
	if _modal_blocks_board_input():
		return
	if event.keycode >= KEY_1 and event.keycode <= KEY_9:
		_select_keyboard_rank(int(event.keycode - KEY_1))
		get_viewport().set_input_as_handled()
		return
	if event.keycode >= KEY_KP_1 and event.keycode <= KEY_KP_9:
		_select_keyboard_rank(int(event.keycode - KEY_KP_1))
		get_viewport().set_input_as_handled()
		return
	match event.keycode:
		KEY_LEFT:
			_move_keyboard_cell(-1, 0)
			get_viewport().set_input_as_handled()
		KEY_RIGHT:
			_move_keyboard_cell(1, 0)
			get_viewport().set_input_as_handled()
		KEY_UP:
			_move_keyboard_cell(0, -1)
			get_viewport().set_input_as_handled()
		KEY_DOWN:
			_move_keyboard_cell(0, 1)
			get_viewport().set_input_as_handled()
		KEY_ENTER, KEY_KP_ENTER, KEY_SPACE:
			if not game_over and not (ai_enabled and turn == 2):
				_on_primary()
			get_viewport().set_input_as_handled()
		KEY_ESCAPE, KEY_BACKSPACE:
			_on_secondary()
			get_viewport().set_input_as_handled()
		KEY_M:
			if _use_mobile_menu():
				_open_mobile_menu()
			else:
				_populate_game_menu()
				top_menu.get_popup().popup_centered()
			get_viewport().set_input_as_handled()


# A5 interactive perspective layer: one shared live board, not a screenshot.
# Native 3x3 buttons remain the semantic/test nodes; their visual layer is hidden.
var perspective_support_shadow: Polygon2D
var perspective_support_surface: Polygon2D
var perspective_plinth: Polygon2D
# Six grounded worlds: a real front/right board fascia and a tight contact
# shadow. The floating Void never creates or displays a physical sidewall.
var perspective_board_front_fascia: Polygon2D
var perspective_board_right_fascia: Polygon2D
var perspective_tiles: Array[Polygon2D] = []
# The two approved submerged worlds, Atlantis and Gods of the Deep, both
# require a continuous electric 3x3 lattice on LIVE stone, not broken seams
# baked into individually warped cell textures. Reuse one shared geometry
# layer: 8 lines (soft glow + crisp core) and 16 junctions; world-specific
# color and width, all cleared for the other five worlds.
var perspective_atlantis_seam_glows: Array[Line2D] = []
var perspective_atlantis_seam_cores: Array[Line2D] = []
var perspective_atlantis_junctions: Array[Polygon2D] = []
# Northern Sea's approved ice/stone board has a WARM luminous 4x4 rune-grid
# lattice. Its gold seams and 16 light knots must track the same nine LIVE
# touch cells as the underwater lattice, but keep independent palette/nodes
# so changing worlds cannot mutate the qualified Atlantis/Gods treatment.
var perspective_northern_grid_glows: Array[Line2D] = []
var perspective_northern_grid_cores: Array[Line2D] = []
var perspective_northern_grid_junctions: Array[Polygon2D] = []
# Sand Sea reference has a lapis/turquoise-and-gold cartouche framing the
# PHYSICAL sandstone board. It must follow the live quadrilateral, not a
# screenshot of a pre-populated board. No new gameplay/input layer is added.
var perspective_sand_inlay_band: Line2D
var perspective_sand_inlay_gold: Line2D
var perspective_sand_inlay_glyphs: Array[Polygon2D] = []
var perspective_piece_contacts: Array[Polygon2D] = []
# Night Sea alone has live orange/blue lighthouse rings grounded at the
# actual rank-specific sprite base. Two noninteractive lines per occupied
# cell (soft bloom + crisp rim); no screenshot occupancy or extra game state.
var perspective_night_beacon_blooms: Array[Line2D] = []
var perspective_night_beacon_rims: Array[Line2D] = []
# One reusable 96x96 radial alpha texture, never a flattened reference image.
# The live light pools follow actual occupancy and rank; the rings remain above.
var perspective_night_beacon_pools: Array[Sprite2D] = []
# Northern Sea: a separate live ice-reflection treatment reuses the existing
# small radial texture, without changing Night Sea's qualified light behavior.
# Each reflection is tied to the actual rune stone's rank and player.
var perspective_northern_rune_reflections: Array[Sprite2D] = []
# ND Premium Void alone has no supporting tabletop. Its actual warm/cool
# glass domes illuminate the floating grid with live rank-sized oval halos.
# These are independent of Night's masonry beacons and clear on world switch.
var perspective_void_dome_pools: Array[Sprite2D] = []
var perspective_void_dome_blooms: Array[Line2D] = []
var perspective_void_dome_rims: Array[Line2D] = []
var _night_beacon_pool_texture: ImageTexture
var perspective_icons: Array[TextureRect] = []
var perspective_ranks: Array[Label] = []
var perspective_legal_outlines: Array[Line2D] = []
# One transient visual preview follows a held, LEGAL board touch. It is not
# part of the board state, never consumes input, and disappears before release
# commits. All seven worlds reuse the exact active rank texture/label.
var perspective_touch_preview_contact: Polygon2D
var perspective_touch_preview_bloom: Line2D
var perspective_touch_preview_rim: Line2D
var perspective_touch_preview_pool: Sprite2D
var perspective_touch_preview_northern_reflection: Sprite2D
var perspective_touch_preview_void_pool: Sprite2D
var perspective_touch_preview_void_bloom: Line2D
var perspective_touch_preview_void_rim: Line2D
var perspective_touch_preview_icon: TextureRect
var perspective_touch_preview_rank: Label
var perspective_rect := Rect2()
# _process checks the board rect every frame. The world-aware clearance solver
# must run only when layout/world inputs change, not 60 times a second.
var _board_height_cache_world := -1
var _board_height_cache_size := Vector2.ZERO
var _board_height_cache_dock_top := -INF
var _board_height_cache_height := 0.0
# Native density can change while the logical 1280x720 canvas stays fixed.
# Refresh board numerals/art on that transition, not only on rectangle changes.
var _last_perspective_pixel_scale := -1.0
var _last_perspective_density := -1.0
var _last_reserve_rank_font_px := -1
var _last_reserve_rank_outline_px := -1

# Night reference uses diffuse illumination ON the stone, not only two
# hard-edged rings. Generate a tiny reusable radial falloff once per scene.
# Alpha is zero at the edge; no art from the accepted PNG is replaced.
func _make_night_beacon_pool_texture() -> ImageTexture:
	var dimension := 96
	var img := Image.create(dimension, dimension, false, Image.FORMAT_RGBA8)
	for y in range(dimension):
		for x in range(dimension):
			var dx := (float(x) + 0.5 - 48.0) / 48.0
			var dy := (float(y) + 0.5 - 48.0) / 48.0
			var radius := sqrt(dx * dx + dy * dy)
			var alpha := 0.58 * pow(maxf(0.0, 1.0 - radius), 1.8)
			img.set_pixel(x, y, Color(1.0, 1.0, 1.0, alpha))
	return ImageTexture.create_from_image(img)

func _create_perspective_layer() -> void:
	_night_beacon_pool_texture = _make_night_beacon_pool_texture()
	var board := get_node("SafeArea/Landscape/Center/BoardAspect/Board") as GridContainer
	for cell in board.get_children():
		(cell as Button).modulate.a = 0.0
		(cell as Button).mouse_filter = Control.MOUSE_FILTER_IGNORE
	var topbar := get_node("SafeArea/Landscape/Center/TopBar") as Control
	var dock := get_node("SafeArea/Landscape/Center/ReserveDock") as Control
	topbar.z_index = 5
	dock.z_index = 5
	perspective_support_shadow = Polygon2D.new()
	perspective_support_shadow.z_index = 1
	add_child(perspective_support_shadow)
	perspective_support_surface = Polygon2D.new()
	perspective_support_surface.z_index = 1
	add_child(perspective_support_surface)
	perspective_plinth = Polygon2D.new()
	perspective_plinth.z_index = 1
	add_child(perspective_plinth)
	perspective_board_right_fascia = Polygon2D.new()
	perspective_board_right_fascia.name = "BoardRightContactFascia"
	perspective_board_right_fascia.z_index = 1
	add_child(perspective_board_right_fascia)
	perspective_board_front_fascia = Polygon2D.new()
	perspective_board_front_fascia.name = "BoardFrontContactFascia"
	perspective_board_front_fascia.z_index = 1
	add_child(perspective_board_front_fascia)
	for i in range(9):
		var tile := Polygon2D.new()
		tile.z_index = 2
		add_child(tile)
		perspective_tiles.append(tile)
		# Draw live legal-target outlines above the board, without replacing its art.
		# Line2D does not consume touch or pointer events.
		var outline := Line2D.new()
		outline.name = "LegalTarget%d" % i
		outline.z_index = 4
		outline.default_color = Color("#f5d77e")
		outline.visible = false
		add_child(outline)
		perspective_legal_outlines.append(outline)
		# Actual placed-piece contact/glow follows the LIVE rank and cell,
		# not any frozen occupancy in the approved reference screenshots.
		var contact := Polygon2D.new()
		contact.name = "PerspectivePieceContact%d" % i
		contact.z_index = 3
		contact.visible = false
		add_child(contact)
		perspective_piece_contacts.append(contact)
		# Soft diffuse contact pool, underneath the two existing ring lines.
		var pool := Sprite2D.new()
		pool.name = "NightBeaconPool%d" % i
		pool.texture = _night_beacon_pool_texture
		pool.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
		pool.z_index = 3
		pool.visible = false
		add_child(pool)
		perspective_night_beacon_pools.append(pool)
		# Reflected runic light is a separate layer ON the frozen support.
		# No static occupancy from the Northern reference is ever composited.
		var northern_reflection := Sprite2D.new()
		northern_reflection.name = "NorthernRuneReflection%d" % i
		northern_reflection.texture = _night_beacon_pool_texture
		northern_reflection.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
		northern_reflection.z_index = 3
		northern_reflection.visible = false
		add_child(northern_reflection)
		perspective_northern_rune_reflections.append(northern_reflection)
		# The accepted Night Sea beacons cast an illuminated ring on stone.
		# Lines are Node2D, never controls, and cannot intercept board taps.
		var bloom := Line2D.new()
		bloom.name = "NightBeaconBloom%d" % i
		bloom.z_index = 3
		bloom.closed = true
		bloom.antialiased = true
		bloom.visible = false
		add_child(bloom)
		perspective_night_beacon_blooms.append(bloom)
		var rim := Line2D.new()
		rim.name = "NightBeaconRim%d" % i
		rim.z_index = 3
		rim.closed = true
		rim.antialiased = true
		rim.visible = false
		add_child(rim)
		perspective_night_beacon_rims.append(rim)
		# A distinct floating halo for Void's live glass dome; never a stone
		# contact shadow and never a baked reference-image occupant.
		var void_pool := Sprite2D.new()
		void_pool.name = "VoidDomePool%d" % i
		void_pool.texture = _night_beacon_pool_texture
		void_pool.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
		void_pool.z_index = 3
		void_pool.visible = false
		add_child(void_pool)
		perspective_void_dome_pools.append(void_pool)
		var void_bloom := Line2D.new()
		void_bloom.name = "VoidDomeBloom%d" % i
		void_bloom.z_index = 3
		void_bloom.closed = true
		void_bloom.antialiased = true
		void_bloom.visible = false
		add_child(void_bloom)
		perspective_void_dome_blooms.append(void_bloom)
		var void_rim := Line2D.new()
		void_rim.name = "VoidDomeRim%d" % i
		void_rim.z_index = 3
		void_rim.closed = true
		void_rim.antialiased = true
		void_rim.visible = false
		add_child(void_rim)
		perspective_void_dome_rims.append(void_rim)
		var icon := TextureRect.new()
		icon.name = "PerspectivePiece%d" % i
		icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
		icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT
		icon.z_index = 3
		add_child(icon)
		perspective_icons.append(icon)
		var rank := Label.new()
		rank.name = "PerspectiveRank%d" % i
		rank.mouse_filter = Control.MOUSE_FILTER_IGNORE
		rank.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		rank.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		rank.add_theme_font_size_override("font_size", 16)
		rank.add_theme_color_override("font_color", Color("#fff9df"))
		rank.add_theme_color_override("font_outline_color", Color("#142332"))
		rank.add_theme_constant_override("outline_size", 4)
		rank.z_index = 4
		add_child(rank)
		perspective_ranks.append(rank)
	# Shared underwater seams render AFTER textured tiles but BELOW real
	# pieces and legal-move outlines. No input node or duplicate board.
	# Eight geometric lines: four vertical and four horizontal (outer rim too).
	for seam_index in range(8):
		var seam_glow := Line2D.new()
		seam_glow.name = "AtlantisSeamGlow%d" % seam_index
		seam_glow.z_index = 2
		seam_glow.antialiased = true
		seam_glow.visible = false
		add_child(seam_glow)
		perspective_atlantis_seam_glows.append(seam_glow)
		var seam_core := Line2D.new()
		seam_core.name = "AtlantisSeamCore%d" % seam_index
		seam_core.z_index = 2
		seam_core.antialiased = true
		seam_core.visible = false
		add_child(seam_core)
		perspective_atlantis_seam_cores.append(seam_core)
	for junction_index in range(16):
		var junction := Polygon2D.new()
		junction.name = "AtlantisGridJunction%d" % junction_index
		junction.z_index = 2
		junction.visible = false
		add_child(junction)
		perspective_atlantis_junctions.append(junction)
	# The approved Northern board has bright amber/white seams and sixteen
	# junction stars. Reuse the SAME live quad, never a screenshot or hit layer.
	for north_seam_index in range(8):
		var north_glow := Line2D.new()
		north_glow.name = "NorthernGridGlow%d" % north_seam_index
		north_glow.z_index = 2
		north_glow.antialiased = true
		north_glow.visible = false
		add_child(north_glow)
		perspective_northern_grid_glows.append(north_glow)
		var north_core := Line2D.new()
		north_core.name = "NorthernGridCore%d" % north_seam_index
		north_core.z_index = 2
		north_core.antialiased = true
		north_core.visible = false
		add_child(north_core)
		perspective_northern_grid_cores.append(north_core)
	for north_junction_index in range(16):
		var north_star := Polygon2D.new()
		north_star.name = "NorthernGridStar%d" % north_junction_index
		north_star.z_index = 2
		north_star.visible = false
		add_child(north_star)
		perspective_northern_grid_junctions.append(north_star)
	# Sand's inlaid stone frame shares the actual board quad and lies above
	# empty cell textures but below the placed pyramids and touch outlines.
	perspective_sand_inlay_band = Line2D.new()
	perspective_sand_inlay_band.name = "SandLapisCartoucheBand"
	perspective_sand_inlay_band.z_index = 2
	perspective_sand_inlay_band.closed = true
	perspective_sand_inlay_band.antialiased = true
	perspective_sand_inlay_band.visible = false
	add_child(perspective_sand_inlay_band)
	perspective_sand_inlay_gold = Line2D.new()
	perspective_sand_inlay_gold.name = "SandGoldCartoucheFillet"
	perspective_sand_inlay_gold.z_index = 2
	perspective_sand_inlay_gold.closed = true
	perspective_sand_inlay_gold.antialiased = true
	perspective_sand_inlay_gold.visible = false
	add_child(perspective_sand_inlay_gold)
	for glyph_index in range(12):
		var glyph := Polygon2D.new()
		glyph.name = "SandLapisGlyph%d" % glyph_index
		glyph.z_index = 2
		glyph.visible = false
		add_child(glyph)
		perspective_sand_inlay_glyphs.append(glyph)
	# One noninteractive rank-specific contact shadow/glow for the held piece.
	# Without it a covering preview inherited the SMALLER buried piece's
	# shadow, visibly floating above the supported stone/table/ice until release.
	perspective_touch_preview_contact = Polygon2D.new()
	perspective_touch_preview_contact.name = "HeldTouchContactPreview"
	perspective_touch_preview_contact.z_index = 3
	perspective_touch_preview_contact.modulate.a = 0.57
	perspective_touch_preview_contact.visible = false
	add_child(perspective_touch_preview_contact)
	perspective_touch_preview_pool = Sprite2D.new()
	perspective_touch_preview_pool.name = "HeldNightBeaconPool"
	perspective_touch_preview_pool.texture = _night_beacon_pool_texture
	perspective_touch_preview_pool.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
	perspective_touch_preview_pool.z_index = 3
	perspective_touch_preview_pool.self_modulate.a = 0.57
	perspective_touch_preview_pool.visible = false
	add_child(perspective_touch_preview_pool)
	perspective_touch_preview_northern_reflection = Sprite2D.new()
	perspective_touch_preview_northern_reflection.name = "HeldNorthernRuneReflection"
	perspective_touch_preview_northern_reflection.texture = _night_beacon_pool_texture
	perspective_touch_preview_northern_reflection.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
	perspective_touch_preview_northern_reflection.z_index = 3
	perspective_touch_preview_northern_reflection.self_modulate.a = 0.57
	perspective_touch_preview_northern_reflection.visible = false
	add_child(perspective_touch_preview_northern_reflection)
	perspective_touch_preview_bloom = Line2D.new()
	perspective_touch_preview_bloom.name = "HeldNightBeaconBloom"
	perspective_touch_preview_bloom.z_index = 3
	perspective_touch_preview_bloom.closed = true
	perspective_touch_preview_bloom.antialiased = true
	perspective_touch_preview_bloom.modulate.a = 0.57
	perspective_touch_preview_bloom.visible = false
	add_child(perspective_touch_preview_bloom)
	perspective_touch_preview_rim = Line2D.new()
	perspective_touch_preview_rim.name = "HeldNightBeaconRim"
	perspective_touch_preview_rim.z_index = 3
	perspective_touch_preview_rim.closed = true
	perspective_touch_preview_rim.antialiased = true
	perspective_touch_preview_rim.modulate.a = 0.57
	perspective_touch_preview_rim.visible = false
	add_child(perspective_touch_preview_rim)
	# The held Void dome has the SAME state-derived floating light as a
	# committed piece, but at preview alpha. It never commits occupancy.
	perspective_touch_preview_void_pool = Sprite2D.new()
	perspective_touch_preview_void_pool.name = "HeldVoidDomePool"
	perspective_touch_preview_void_pool.texture = _night_beacon_pool_texture
	perspective_touch_preview_void_pool.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
	perspective_touch_preview_void_pool.z_index = 3
	perspective_touch_preview_void_pool.self_modulate.a = 0.57
	perspective_touch_preview_void_pool.visible = false
	add_child(perspective_touch_preview_void_pool)
	perspective_touch_preview_void_bloom = Line2D.new()
	perspective_touch_preview_void_bloom.name = "HeldVoidDomeBloom"
	perspective_touch_preview_void_bloom.z_index = 3
	perspective_touch_preview_void_bloom.closed = true
	perspective_touch_preview_void_bloom.antialiased = true
	perspective_touch_preview_void_bloom.modulate.a = 0.57
	perspective_touch_preview_void_bloom.visible = false
	add_child(perspective_touch_preview_void_bloom)
	perspective_touch_preview_void_rim = Line2D.new()
	perspective_touch_preview_void_rim.name = "HeldVoidDomeRim"
	perspective_touch_preview_void_rim.z_index = 3
	perspective_touch_preview_void_rim.closed = true
	perspective_touch_preview_void_rim.antialiased = true
	perspective_touch_preview_void_rim.modulate.a = 0.57
	perspective_touch_preview_void_rim.visible = false
	add_child(perspective_touch_preview_void_rim)
	# Single overlay, not nine duplicate sprites or a second gameplay layer.
	perspective_touch_preview_icon = TextureRect.new()
	perspective_touch_preview_icon.name = "HeldTouchPiecePreview"
	perspective_touch_preview_icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
	perspective_touch_preview_icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	perspective_touch_preview_icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT
	perspective_touch_preview_icon.modulate.a = 0.57
	perspective_touch_preview_icon.z_index = 3
	perspective_touch_preview_icon.visible = false
	add_child(perspective_touch_preview_icon)
	perspective_touch_preview_rank = Label.new()
	perspective_touch_preview_rank.name = "HeldTouchRankPreview"
	perspective_touch_preview_rank.mouse_filter = Control.MOUSE_FILTER_IGNORE
	perspective_touch_preview_rank.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	perspective_touch_preview_rank.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	perspective_touch_preview_rank.add_theme_color_override("font_color", Color("#fff9df"))
	perspective_touch_preview_rank.add_theme_color_override("font_outline_color", Color("#142332"))
	perspective_touch_preview_rank.modulate.a = 0.82
	perspective_touch_preview_rank.z_index = 4
	perspective_touch_preview_rank.visible = false
	add_child(perspective_touch_preview_rank)
	call_deferred("_refresh_perspective_layer")

# The perspective grid is not the bottommost rendered element: its plinth
# extends 9 logical pixels, and a supported world's material/contact shadow
# extends up to 13 scaled pixels. Reserve clearance must include those visible
# pixels, not merely the board's geometric corner. The Void has no support.
func _perspective_visual_bottom(world: int, viewport_size: Vector2) -> float:
	var quad := PerspectiveGeometry.board_quad(world, Rect2(Vector2.ZERO, viewport_size))
	var bottom := maxf(maxf(quad[0].y, quad[1].y), maxf(quad[2].y, quad[3].y))
	var overhang := 9.0  # Live plinth (all worlds).
	if world != 0:
		# Supported worlds: 10px surface lip + 3px contact shadow,
		# scaled identically to _refresh_perspective_layer().
		overhang = maxf(overhang, 13.0 * clampf(viewport_size.y / 720.0, 0.35, 1.0))
	return bottom + overhang

func _safe_board_height_for_reserve(world: int, viewport_size: Vector2, reserve_top: float) -> float:
	# Retain the qualified enlarged-board geometry when it already fits.
	var proposed := minf(viewport_size.y, maxf(100.0, (reserve_top - 5.0) / 0.80))
	var allowed_bottom := reserve_top - 6.0
	if _perspective_visual_bottom(world, Vector2(viewport_size.x, proposed)) <= allowed_bottom:
		return proposed
	# Solve only the rare low-height collision, maximizing board area while
	# keeping its visible fascia/support above the active player's reserve.
	var low := 0.0
	var high := proposed
	for _iteration in range(16):
		var candidate := (low + high) * 0.5
		if _perspective_visual_bottom(world, Vector2(viewport_size.x, candidate)) <= allowed_bottom:
			low = candidate
		else:
			high = candidate
	return maxf(1.0, low)

func _perspective_board_rect() -> Rect2:
	var size := get_viewport_rect().size
	var dock := get_node("SafeArea/Landscape/Center/ReserveDock") as Control
	var reserve_top := dock.global_position.y
	if _board_height_cache_world != current_world or _board_height_cache_size != size or _board_height_cache_dock_top != reserve_top:
		_board_height_cache_height = _safe_board_height_for_reserve(current_world, size, reserve_top)
		_board_height_cache_world = current_world
		_board_height_cache_size = size
		_board_height_cache_dock_top = reserve_top
	return Rect2(Vector2.ZERO, Vector2(size.x, _board_height_cache_height))

# Shared placement geometry: held preview and committed sprite must land at
# precisely the same rank-specific baseline. In Northern Sea transparent rune
# bottoms vary by 29px across ranks; borrowing the COVERED piece's rect made
# a rank-9 preview float above its final position when covering rank 1.
func _perspective_piece_rect(world: int, cell: int, rank: int, extent: float) -> Rect2:
	assert(cell >= 0 and cell < 9 and rank >= 0 and rank <= 9)
	var center := PerspectiveGeometry.cell_center(world, cell, perspective_rect)
	var rect := Rect2(center - Vector2.ONE * extent * 0.5, Vector2.ONE * extent)
	if rank > 0:
		rect.position.y += PieceGrounding.baseline_shift(world, rank, extent)
	return rect

# One contact geometry for BOTH held and committed pieces. Void's light
# dome floats; every other world's contact is a physical shadow on its
# supporting surface. Pure presentation, never an extra board occupant.
func _apply_piece_contact(contact: Polygon2D, world: int, rect: Rect2,
		extent: float, rank: int, player: int) -> void:
	var center := rect.position + rect.size * 0.5
	if world == 0:
		center.y += extent * 0.24
		# The approved extracted Void sprites are P1 warm amber, P2 cool
		# blue. The older contact palette was reversed relative to the art.
		contact.color = Color(1.0, 0.74, 0.49, 0.23) if player == 1 else Color(0.57, 0.77, 1.0, 0.23)
		contact.polygon = PieceGrounding.ellipse(center, extent * 0.40, extent * 0.13)
	else:
		center.y = rect.position.y + extent * PieceGrounding.bottom_fraction(world, rank)
		# The Night Sea reference has strong orange/blue light pooling on the
		# masonry around each beacon. Other supported worlds retain shadows.
		# The same qualified contact ellipse is used for every grounded world.
		# Night adds color and a separate live ring; geometry remains stable.
		contact.color = (Color(1.0, 0.46, 0.08, 0.18) if player == 1 else
			Color(0.13, 0.65, 1.0, 0.18)) if world == 5 else Color(0.015, 0.02, 0.035, 0.43)
		contact.polygon = PieceGrounding.ellipse(center, extent * (0.14 + 0.035 * rank), extent * 0.065)

# One shared presentation function for committed beacons AND held previews.
# Rings are constructed from the LIVE sprite baseline, not a screenshot's
# frozen occupancy. A world switch clears both points and visibility.
# Diffuse ground light and hard ring share the same LIVE sprite baseline.
# Texture is reused by all cells; tint, position and projected size are state-
# bound. Sprite2D is Node2D and never intercepts board or reserve input.
func _update_night_beacon_pool(pool: Sprite2D, world: int, rect: Rect2,
		extent: float, rank: int, player: int) -> void:
	var show := world == 5 and rank >= 1 and rank <= 9 and player in [1, 2]
	pool.visible = show
	if not show:
		return
	var base := rect.position + Vector2(extent * 0.5,
		extent * PieceGrounding.bottom_fraction(world, rank))
	var radius_x := extent * (0.28 + 0.015 * rank)
	var radius_y := extent * (0.105 + 0.003 * rank)
	pool.position = base
	# Image diameter is 96; project a broad oval 1.45x the rim's radius.
	pool.scale = Vector2(2.9 * radius_x / 96.0, 2.9 * radius_y / 96.0)
	pool.modulate = Color("#ff9c35") if player == 1 else Color("#4cbcff")

# Northern Sea's frozen stone reflects the live amber/cyan rune, not a
# screenshot-baked light. Share the Night pool's 96x96 radial alpha image but
# keep the two worlds' geometry and visibility independent. On every refresh
# empty cells and all other worlds explicitly clear their previous reflection.
func _update_northern_rune_reflection(pool: Sprite2D, world: int, rect: Rect2,
		extent: float, rank: int, player: int) -> void:
	var show := world == 6 and rank >= 1 and rank <= 9 and player in [1, 2]
	pool.visible = show
	if not show:
		return
	var base := rect.position + Vector2(extent * 0.5,
		extent * PieceGrounding.bottom_fraction(world, rank))
	var radius_x := extent * (0.24 + 0.014 * rank)
	var radius_y := extent * (0.080 + 0.003 * rank)
	pool.position = base + Vector2(0.0, extent * 0.025)
	pool.scale = Vector2(3.1 * radius_x / 96.0, 2.7 * radius_y / 96.0)
	pool.modulate = Color(0.98, 0.55, 0.29, 0.45) if player == 1 else Color(0.32, 0.80, 1.0, 0.45)

func _update_night_beacon_ring(bloom: Line2D, rim: Line2D, world: int,
		rect: Rect2, extent: float, rank: int, player: int) -> void:
	var show := world == 5 and rank >= 1 and rank <= 9 and player in [1, 2]
	bloom.visible = show
	rim.visible = show
	if not show:
		bloom.clear_points()
		rim.clear_points()
		return
	var base := rect.position + Vector2(extent * 0.5,
		extent * PieceGrounding.bottom_fraction(world, rank))
	var radius_x := extent * (0.28 + 0.015 * rank)
	var radius_y := extent * (0.105 + 0.003 * rank)
	# The light ring is NOT another contact shadow. Build its perimeter
	# separately, leaving the shared contact helper and all other worlds intact.
	var points := PackedVector2Array()
	for i in range(16):
		var angle := TAU * float(i) / 16.0
		points.append(base + Vector2(cos(angle) * radius_x, sin(angle) * radius_y))
	bloom.points = points
	rim.points = points
	var light := Color("#ff9c35") if player == 1 else Color("#4cbcff")
	bloom.default_color = Color(light.r, light.g, light.b, 0.25)
	rim.default_color = Color(light.r, light.g, light.b, 0.93)
	bloom.width = maxf(3.0, extent * 0.18)
	rim.width = maxf(1.4, extent * 0.045)

# Void's glass dome casts a floating warm/cool ring into its OWN live cell.
# P1 is amber and P2 blue, matching the extracted accepted sprites. This
# reuses the same tiny radial falloff as Night/North, not their ground-light
# geometry or a flattened image. Rank affects both ellipse radii strictly.
func _update_void_dome_light(pool: Sprite2D, bloom: Line2D, rim: Line2D,
		world: int, rect: Rect2, extent: float, rank: int, player: int) -> void:
	var show := world == 0 and rank >= 1 and rank <= 9 and player in [1, 2]
	pool.visible = show
	bloom.visible = show
	rim.visible = show
	if not show:
		bloom.clear_points()
		rim.clear_points()
		return
	var base := rect.position + Vector2(extent * 0.5, extent * 0.74)
	var radius_x := extent * (0.24 + 0.014 * rank)
	var radius_y := extent * (0.085 + 0.003 * rank)
	pool.position = base
	pool.scale = Vector2(2.9 * radius_x / 96.0, 3.0 * radius_y / 96.0)
	var light := Color("#ff9d42") if player == 1 else Color("#49bfff")
	pool.modulate = Color(light.r, light.g, light.b, 0.70)
	var points := PackedVector2Array()
	for i in range(24):
		var angle := TAU * float(i) / 24.0
		points.append(base + Vector2(cos(angle) * radius_x, sin(angle) * radius_y))
	bloom.points = points
	rim.points = points
	bloom.default_color = Color(light.r, light.g, light.b, 0.30)
	rim.default_color = Color(light.r, light.g, light.b, 0.96)
	bloom.width = maxf(3.0, extent * 0.19)
	rim.width = maxf(1.4, extent * 0.05)

# Restore the reference's uninterrupted cyan grid over NINE independent live
# cell textures. Bilinear lines follow the same quad as touch geometry and
# physically lie on the submerged stone; they never imply floating gameplay.
# World switches clear every seam and junction, including empty-board state.
func _refresh_atlantis_live_seams(quad: PackedVector2Array) -> void:
	if perspective_atlantis_seam_glows.size() != 8 or perspective_atlantis_junctions.size() != 16:
		return
	var show := current_world == 2 or current_world == 3
	var gods := current_world == 3
	var scale := clampf(perspective_rect.size.y / 720.0, 0.35, 1.0)
	for seam_index in range(8):
		var glow := perspective_atlantis_seam_glows[seam_index]
		var core := perspective_atlantis_seam_cores[seam_index]
		glow.visible = show
		core.visible = show
		if not show:
			glow.clear_points()
			core.clear_points()
			continue
		var t := float(seam_index % 4) / 3.0
		var start: Vector2
		var finish: Vector2
		if seam_index < 4:
			start = quad[0].lerp(quad[1], t)
			finish = quad[3].lerp(quad[2], t)
		else:
			start = quad[0].lerp(quad[3], t)
			finish = quad[1].lerp(quad[2], t)
		var points := PackedVector2Array([start, finish])
		glow.points = points
		core.points = points
		# Gods has the stronger cobalt/white lattice visible in its accepted
		# reference; Atlantis keeps its qualified v160 cyan palette unchanged.
		glow.width = maxf(2.4, 8.0 * scale) if gods else maxf(2.2, 7.0 * scale)
		core.width = maxf(1.1, 2.8 * scale) if gods else maxf(1.0, 2.4 * scale)
		glow.default_color = Color(0.02, 0.48, 1.0, 0.41) if gods else Color(0.05, 0.78, 1.0, 0.31)
		core.default_color = Color(0.62, 0.92, 1.0, 0.95) if gods else Color(0.34, 0.96, 1.0, 0.84)
	for junction_index in range(16):
		var junction := perspective_atlantis_junctions[junction_index]
		junction.visible = show
		if not show:
			junction.polygon = PackedVector2Array()
			continue
		var u := float(junction_index % 4) / 3.0
		var v := floorf(float(junction_index) / 4.0) / 3.0
		var top := quad[0].lerp(quad[1], u)
		var bottom := quad[3].lerp(quad[2], u)
		var center := top.lerp(bottom, v)
		var radius := maxf(1.6, 4.3 * scale)
		junction.polygon = PackedVector2Array([
			center + Vector2(0.0, -radius),
			center + Vector2(radius * 0.70, 0.0),
			center + Vector2(0.0, radius),
			center + Vector2(-radius * 0.70, 0.0)
		])
		junction.color = Color(0.72, 0.96, 1.0, 0.96) if gods else Color(0.45, 0.98, 1.0, 0.82)

# Northern Sea's approved glowing seams belong to the PHYSICAL frozen board,
# not a hovering overlay or a frozen occupied screenshot. Perspective edges
# are derived from the exact same quad as the real nine-cell touch surface.
# On leaving North, every line and star is cleared; no other world's seam
# colors, ranked runes, gameplay or input targets are changed.
func _refresh_northern_live_lattice(quad: PackedVector2Array) -> void:
	if perspective_northern_grid_glows.size() != 8 or perspective_northern_grid_cores.size() != 8 or perspective_northern_grid_junctions.size() != 16:
		return
	var show := current_world == 6 and quad.size() == 4
	var scale := clampf(perspective_rect.size.y / 720.0, 0.35, 1.0)
	for seam_index in range(8):
		var glow := perspective_northern_grid_glows[seam_index]
		var core := perspective_northern_grid_cores[seam_index]
		glow.visible = show
		core.visible = show
		if not show:
			glow.clear_points()
			core.clear_points()
			continue
		var t := float(seam_index % 4) / 3.0
		var start: Vector2
		var finish: Vector2
		if seam_index < 4:
			start = quad[0].lerp(quad[1], t)
			finish = quad[3].lerp(quad[2], t)
		else:
			start = quad[0].lerp(quad[3], t)
			finish = quad[1].lerp(quad[2], t)
		glow.points = PackedVector2Array([start, finish])
		core.points = PackedVector2Array([start, finish])
		glow.width = maxf(2.5, 9.0 * scale)
		core.width = maxf(1.2, 3.0 * scale)
		glow.default_color = Color(1.0, 0.52, 0.12, 0.34)
		core.default_color = Color(1.0, 0.86, 0.57, 0.91)
	for junction_index in range(16):
		var star := perspective_northern_grid_junctions[junction_index]
		star.visible = show
		if not show:
			star.polygon = PackedVector2Array()
			continue
		var u := float(junction_index % 4) / 3.0
		var v := floorf(float(junction_index) / 4.0) / 3.0
		var upper := quad[0].lerp(quad[1], u)
		var lower := quad[3].lerp(quad[2], u)
		var center := upper.lerp(lower, v)
		var radius := maxf(1.8, 5.0 * scale)
		star.polygon = PackedVector2Array([
			center + Vector2(0.0, -radius),
			center + Vector2(radius * 0.72, 0.0),
			center + Vector2(0.0, radius),
			center + Vector2(-radius * 0.72, 0.0)
		])
		star.color = Color(1.0, 0.93, 0.71, 0.96)

# The Egyptian reference's turquoise cartouche is a live ornamental rim
# around the nine real sandstone cells. Its four sides follow the SAME
# perspective quad as touch hit-testing; it is not a screenshot border or a
# second board. All geometry is cleared when leaving Sand Sea.
func _refresh_sand_live_cartouche(quad: PackedVector2Array) -> void:
	if perspective_sand_inlay_band == null or perspective_sand_inlay_gold == null or perspective_sand_inlay_glyphs.size() != 12:
		return
	var show := current_world == 4 and quad.size() == 4
	perspective_sand_inlay_band.visible = show
	perspective_sand_inlay_gold.visible = show
	if not show:
		perspective_sand_inlay_band.clear_points()
		perspective_sand_inlay_gold.clear_points()
		for glyph in perspective_sand_inlay_glyphs:
			glyph.visible = false
			glyph.polygon = PackedVector2Array()
		return
	var scale := clampf(perspective_rect.size.y / 720.0, 0.35, 1.0)
	var center := (quad[0] + quad[1] + quad[2] + quad[3]) * 0.25
	var outer := PackedVector2Array()
	for corner in quad:
		# Place the lapis band over the sandstone support, OUTSIDE the nine
		# tappable cells, without expanding the semantic hit-test polygon.
		outer.append(corner + (corner - center).normalized() * 3.0 * scale)
	perspective_sand_inlay_band.points = outer
	perspective_sand_inlay_gold.points = quad
	perspective_sand_inlay_band.width = maxf(3.8, 11.0 * scale)
	perspective_sand_inlay_gold.width = maxf(1.15, 2.3 * scale)
	perspective_sand_inlay_band.default_color = Color(0.025, 0.54, 0.61, 0.97)
	perspective_sand_inlay_gold.default_color = Color(0.94, 0.72, 0.35, 0.98)
	for glyph_index in range(12):
		var glyph := perspective_sand_inlay_glyphs[glyph_index]
		var edge_index := int(glyph_index / 3)
		var fraction := (float(glyph_index % 3) + 0.5) / 3.0
		var a: Vector2 = outer[edge_index]
		var b: Vector2 = outer[(edge_index + 1) % 4]
		var at := a.lerp(b, fraction)
		var tangent := (b - a).normalized()
		var inward := (center - at).normalized()
		var radius := maxf(1.35, 4.6 * scale)
		glyph.polygon = PackedVector2Array([
			at - tangent * radius,
			at + inward * radius * 0.65,
			at + tangent * radius,
			at - inward * radius * 0.65,
		])
		glyph.color = Color(0.96, 0.76, 0.37, 0.96) if glyph_index % 2 == 0 else Color(0.09, 0.80, 0.80, 0.96)
		glyph.visible = true

func _refresh_perspective_layer() -> void:
	if perspective_tiles.size() != 9:
		return
	_last_perspective_pixel_scale = _physical_pixel_scale()
	_last_perspective_density = _native_touch_density()
	# The live board uses Label nodes separate from the reserve buttons.
	# Without density scaling, its fixed 16px numerals are ~5dp at 3x DPI.
	var logical_rank_font := maxi(16, ceili(14.0 * _last_perspective_density / _last_perspective_pixel_scale))
	var logical_rank_outline := _live_rank_outline_px()
	perspective_rect = _perspective_board_rect()
	var base := PerspectiveGeometry.board_quad(current_world, perspective_rect)
	_refresh_atlantis_live_seams(base)
	_refresh_northern_live_lattice(base)
	_refresh_sand_live_cartouche(base)
	var has_support := current_world != 0
	perspective_support_surface.visible = has_support
	perspective_support_shadow.visible = has_support
	if has_support:
		# A solid surface extends beyond the board in the SAME perspective plane.
		# Margins scale down for 746x280 without covering the active reserve.
		var scale := clampf(perspective_rect.size.y / 720.0, 0.35, 1.0)
		var mx := 20.0 * scale
		var my := 10.0 * scale
		var surface := PackedVector2Array([
			base[0] + Vector2(-mx, -my), base[1] + Vector2(mx, -my),
			base[2] + Vector2(mx, my), base[3] + Vector2(-mx, my)
		])
		perspective_support_surface.polygon = surface
		# The visible inclined supporting plane must carry its world's actual
		# leather/chart, submerged stone, sandstone, masonry or Nordic material.
		# The old flat fill obscured the qualified material on the semantic panel.
		var foundation := get_node("SafeArea/Landscape/Center/BoardAspect/PhysicalSupport/NorthernStonePlinth") as TextureRect
		var material := foundation.texture
		assert(material != null, "Supported world is missing its physical surface material")
		perspective_support_surface.texture = material
		var texture_size := material.get_size()
		perspective_support_surface.uv = PackedVector2Array([
			Vector2.ZERO, Vector2(texture_size.x, 0.0),
			texture_size, Vector2(0.0, texture_size.y)
		])
		perspective_support_surface.color = Color.WHITE
		var shadow := PackedVector2Array()
		for corner in surface:
			# Contact shadow, not the old 12px detached/levitating silhouette.
			shadow.append(corner + Vector2(0.0, 3.0 * scale))
		perspective_support_shadow.polygon = shadow
		perspective_support_shadow.color = Color(0.0, 0.0, 0.0, 0.70)
	else:
		# No stale material from a supported world may leak into floating Void.
		perspective_support_surface.texture = null
		perspective_support_surface.uv = PackedVector2Array()
	perspective_plinth.visible = has_support
	var backing := PackedVector2Array()
	for p in base:
		backing.append(p + Vector2(0.0, 9.0))
	perspective_plinth.polygon = backing
	perspective_plinth.color = WorldVisuals.BOARD_COLORS[current_world].darkened(0.47)
	# The board's visible front/right faces connect directly to the textured
	# support plane, so perspective never makes the six grounded boards hover.
	# All coordinates derive from the LIVE board quad, not screenshot pixels.
	perspective_board_front_fascia.visible = has_support
	perspective_board_right_fascia.visible = has_support
	if has_support:
		var contact_scale := clampf(perspective_rect.size.y / 720.0, 0.35, 1.0)
		var contact_depth := maxf(3.0, 11.0 * contact_scale)
		var down := Vector2(0.0, contact_depth)
		perspective_board_front_fascia.polygon = PackedVector2Array([
			base[3], base[2], base[2] + down, base[3] + down
		])
		perspective_board_right_fascia.polygon = PackedVector2Array([
			base[1], base[2], base[2] + down, base[1] + down
		])
		perspective_board_front_fascia.color = WorldVisuals.BOARD_COLORS[current_world].darkened(0.57)
		perspective_board_right_fascia.color = WorldVisuals.BOARD_COLORS[current_world].darkened(0.68)
	else:
		# A Void switch must not retain even an invisible previous-world mesh.
		perspective_board_front_fascia.polygon = PackedVector2Array()
		perspective_board_right_fascia.polygon = PackedVector2Array()
	for i in range(9):
		var quad := PerspectiveGeometry.cell_quad(current_world, i, perspective_rect)
		var tile := perspective_tiles[i]
		var outline := perspective_legal_outlines[i]
		outline.points = PackedVector2Array([quad[0], quad[1], quad[2], quad[3], quad[0]])
		outline.width = maxf(2.0, 2.5 / _physical_pixel_scale())
		tile.polygon = quad
		tile.color = WorldVisuals.BOARD_COLORS[current_world].lightened(0.06)
		var source := get_node("SafeArea/Landscape/Center/BoardAspect/Board/" + CELL_NAMES[i]) as Button
		var art := source.get_node_or_null("WorldCellArt") as TextureRect
		if art != null and art.visible and art.texture != null:
			tile.texture = art.texture
			var ts := art.texture.get_size()
			tile.uv = PackedVector2Array([Vector2.ZERO, Vector2(ts.x, 0), ts, Vector2(0, ts.y)])
			tile.color = Color.WHITE
		else:
			tile.texture = null
		var center := PerspectiveGeometry.cell_center(current_world, i, perspective_rect)
		var width := (quad[1] - quad[0]).length()
		var height := (quad[3] - quad[0]).length()
		# Match the reserve's device-independent target before cell-bound caps.
		# The board itself stays large and uses touch hit expansion separately.
		var extent := minf(ceilf(_minimum_touch_physical_px() / _last_perspective_pixel_scale), minf(width * 0.56, height * 0.88))
		var top := _top_piece(i)
		var rect := _perspective_piece_rect(current_world, i,
			int(top.rank) if not top.is_empty() else 0, extent)
		var contact := perspective_piece_contacts[i]
		contact.visible = not top.is_empty()
		if not top.is_empty():
			# Both the committed piece and its held preview use ONE rank-specific
			# world contact geometry, including Northern transparent rune bottoms.
			_apply_piece_contact(contact, current_world, rect, extent,
				int(top.rank), int(top.player))
		else:
			contact.polygon = PackedVector2Array()
		_update_night_beacon_pool(perspective_night_beacon_pools[i],
			current_world, rect, extent,
			int(top.rank) if not top.is_empty() else 0,
			int(top.player) if not top.is_empty() else 0)
		_update_northern_rune_reflection(perspective_northern_rune_reflections[i],
			current_world, rect, extent,
			int(top.rank) if not top.is_empty() else 0,
			int(top.player) if not top.is_empty() else 0)
		_update_night_beacon_ring(perspective_night_beacon_blooms[i],
			perspective_night_beacon_rims[i], current_world, rect, extent,
			int(top.rank) if not top.is_empty() else 0,
			int(top.player) if not top.is_empty() else 0)
		_update_void_dome_light(perspective_void_dome_pools[i],
			perspective_void_dome_blooms[i], perspective_void_dome_rims[i],
			current_world, rect, extent,
			int(top.rank) if not top.is_empty() else 0,
			int(top.player) if not top.is_empty() else 0)
		var icon := perspective_icons[i]
		var rank := perspective_ranks[i]
		rank.add_theme_font_size_override("font_size", logical_rank_font)
		rank.add_theme_constant_override("outline_size", logical_rank_outline)
		icon.position = rect.position
		icon.size = rect.size
		# The reference's Pirate caps carry their number on the top inset badge.
		# Keep the anchor artwork visible; the rank label is actual game state.
		if current_world == 1:
			rank.position = rect.position + Vector2(0.0, rect.size.y * 0.03)
			rank.size = Vector2(rect.size.x, rect.size.y * 0.45)
		elif current_world == 2 and not top.is_empty():
			var rank_band := _atlantis_rank_band(int(top.rank))
			rank.position = rect.position + Vector2(0.0, rect.size.y * rank_band.x)
			rank.size = Vector2(rect.size.x, rect.size.y * (rank_band.y - rank_band.x))
		elif current_world == 3:
			rank.position = rect.position + Vector2(0.0, rect.size.y * 0.59)
			rank.size = Vector2(rect.size.x, rect.size.y * 0.41)
		elif current_world == 4 and not top.is_empty():
			var sand_band := _sand_rank_band(int(top.rank))
			rank.position = rect.position + Vector2(0.0, rect.size.y * sand_band.x)
			rank.size = Vector2(rect.size.x, rect.size.y * (sand_band.y - sand_band.x))
		elif current_world == 5 and not top.is_empty():
			var night_band := _night_rank_band(int(top.rank))
			rank.position = rect.position + Vector2(0.0, rect.size.y * night_band.x)
			rank.size = Vector2(rect.size.x, rect.size.y * (night_band.y - night_band.x))
		elif current_world == 6:
			# Preserve the distinct Elder Futhark face while keeping the live
			# rank readable at 746x280; this label never changes cell hit areas.
			rank.position = rect.position + Vector2(0.0, rect.size.y * 0.68)
			rank.size = Vector2(rect.size.x, rect.size.y * 0.32)
		else:
			rank.position = rect.position
			rank.size = rect.size
		# A 14dp live number may be taller than the source art's small badge.
		# Enlarge only its noninteractive label region, keeping the rank's
		# world-specific anchor centered and within its OWN perspective cell.
		var number_center_y := rank.position.y + rank.size.y * 0.5
		var cell_top := minf(minf(quad[0].y, quad[1].y), minf(quad[2].y, quad[3].y))
		var cell_bottom := maxf(maxf(quad[0].y, quad[1].y), maxf(quad[2].y, quad[3].y))
		var usable_height := maxf(1.0, cell_bottom - cell_top - 2.0)
		var number_height := minf(usable_height, maxf(rank.size.y, float(logical_rank_font) * 1.25))
		rank.position.y = clampf(number_center_y - number_height * 0.5, cell_top + 1.0, cell_bottom - number_height - 1.0)
		rank.size.y = number_height
		icon.visible = not top.is_empty()
		rank.visible = not top.is_empty()
		if not top.is_empty():
			icon.texture = world_visuals.piece_texture(current_world, int(top.player), int(top.rank))
			rank.text = str(int(top.rank))
		else:
			icon.texture = null
			rank.text = ""
	_refresh_selection_feedback()
	_refresh_touch_preview()

# Preview is strictly presentation: never append to board_stacks, consume a
# reserve, change turn, or authorize an illegal placement. The press-time state
# token prevents a stale gesture from previewing after world/rule/turn changes.
func _refresh_touch_preview() -> void:
	if perspective_touch_preview_contact == null or perspective_touch_preview_icon == null or perspective_touch_preview_rank == null:
		return
	perspective_touch_preview_contact.visible = false
	perspective_touch_preview_pool.visible = false
	perspective_touch_preview_northern_reflection.visible = false
	perspective_touch_preview_bloom.visible = false
	perspective_touch_preview_rim.visible = false
	perspective_touch_preview_bloom.clear_points()
	perspective_touch_preview_rim.clear_points()
	perspective_touch_preview_void_pool.visible = false
	perspective_touch_preview_void_bloom.visible = false
	perspective_touch_preview_void_rim.visible = false
	perspective_touch_preview_void_bloom.clear_points()
	perspective_touch_preview_void_rim.clear_points()
	perspective_touch_preview_icon.visible = false
	perspective_touch_preview_rank.visible = false
	if not _touch_board_pending or _touch_board_cell < 0 or _touch_board_cell >= 9:
		return
	if selected_reserve < 0 or selected_reserve >= 9 or _modal_blocks_board_input():
		return
	if _touch_board_state_at_press.is_empty() or _touch_board_state_at_press != _touch_board_state_token():
		return
	var rank := selected_reserve + 1
	if not _is_legal_move(turn, rank, _touch_board_cell):
		return
	var cell := _touch_board_cell
	# The target cell may already contain a SMALLER rank. Never borrow that
	# occupied icon's y offset: compute the held rank's eventual placement.
	var extent := perspective_icons[cell].size.x
	var preview_rect := _perspective_piece_rect(current_world, cell, rank, extent)
	_apply_piece_contact(perspective_touch_preview_contact, current_world,
		preview_rect, extent, rank, turn)
	_update_night_beacon_pool(perspective_touch_preview_pool,
		current_world, preview_rect, extent, rank, turn)
	_update_northern_rune_reflection(perspective_touch_preview_northern_reflection,
		current_world, preview_rect, extent, rank, turn)
	_update_night_beacon_ring(perspective_touch_preview_bloom,
		perspective_touch_preview_rim, current_world, preview_rect, extent, rank, turn)
	_update_void_dome_light(perspective_touch_preview_void_pool,
		perspective_touch_preview_void_bloom, perspective_touch_preview_void_rim,
		current_world, preview_rect, extent, rank, turn)
	perspective_touch_preview_icon.position = preview_rect.position
	perspective_touch_preview_icon.size = preview_rect.size
	perspective_touch_preview_icon.texture = world_visuals.piece_texture(current_world, turn, rank)
	# Empty cells have no placed-piece label band. Derive the preview numeral
	# from the HELD rank's world-specific brass/stone/rune anchor instead.
	var band := _reserve_rank_label_band(rank)
	# The placed Pirate cap's upper badge begins at 3%, not reserve's 0%.
	if current_world == 1:
		band.x = 0.03
	var center_y := preview_rect.position.y + preview_rect.size.y * (band.x + band.y) * 0.5
	var quad := PerspectiveGeometry.cell_quad(current_world, cell, perspective_rect)
	var cell_top := minf(minf(quad[0].y, quad[1].y), minf(quad[2].y, quad[3].y))
	var cell_bottom := maxf(maxf(quad[0].y, quad[1].y), maxf(quad[2].y, quad[3].y))
	var usable_height := maxf(1.0, cell_bottom - cell_top - 2.0)
	var number_height := minf(usable_height, maxf(preview_rect.size.y * (band.y - band.x), float(_live_rank_font_px()) * 1.25))
	perspective_touch_preview_rank.position = Vector2(preview_rect.position.x,
		clampf(center_y - number_height * 0.5, cell_top + 1.0, cell_bottom - number_height - 1.0))
	perspective_touch_preview_rank.size = Vector2(preview_rect.size.x, number_height)
	perspective_touch_preview_rank.text = str(rank)
	perspective_touch_preview_rank.add_theme_font_size_override("font_size", _live_rank_font_px())
	perspective_touch_preview_rank.add_theme_constant_override("outline_size", _live_rank_outline_px())
	perspective_touch_preview_contact.visible = true
	perspective_touch_preview_icon.visible = true
	perspective_touch_preview_rank.visible = true

func _refresh_selection_feedback() -> void:
	# At 746x280 the status bar is hidden. Selection and legal moves must
	# therefore be legible ON the board and reserve, not only in a tooltip.
	if perspective_legal_outlines.size() != 9:
		return
	var can_select := not game_over and not (ai_enabled and turn == 2)
	var has_piece := can_select and selected_reserve >= 0 and selected_reserve < 9
	var logical_border := maxi(2, ceili(3.0 / _physical_pixel_scale()))
	for player in [1, 2]:
		var reserve := _reserve_node(player)
		for i in range(reserve.get_child_count()):
			var piece := reserve.get_child(i) as Button
			var ring := piece.get_node_or_null("SelectionRing") as Panel
			if ring == null:
				ring = Panel.new()
				ring.name = "SelectionRing"
				ring.mouse_filter = Control.MOUSE_FILTER_IGNORE
				piece.add_child(ring)
				ring.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
			var style := StyleBoxFlat.new()
			style.bg_color = Color.TRANSPARENT
			style.border_color = Color("#ffdf80")
			style.set_border_width_all(logical_border)
			style.set_corner_radius_all(7)
			ring.add_theme_stylebox_override("panel", style)
			piece.move_child(ring, piece.get_child_count() - 1)
			ring.visible = has_piece and player == turn and i == selected_reserve and reserve.visible
	for i in range(9):
		var outline := perspective_legal_outlines[i]
		# The completed line is a real result of _winning_line(), not art
		# copied from the reference PNG. Keep its three cells visible in all
		# seven worlds, including after a world switch or viewport rotation.
		# Draws never invent a winning line; the next round clears it.
		if game_over:
			outline.visible = winner != 0 and win_line.has(i)
			outline.default_color = Color("#ffda73")
			outline.width = maxf(3.5, 4.0 / _physical_pixel_scale())
			continue
		outline.width = maxf(2.0, 2.5 / _physical_pixel_scale())
		var legal := has_piece and _is_legal_move(turn, selected_reserve + 1, i)
		# The keyboard cursor remains visible even after a rank is selected;
		# red warns when Enter would be illegal, cyan means legal/empty.
		var chosen_cell := can_select and selected_cell == i
		perspective_legal_outlines[i].visible = legal or chosen_cell
		outline.default_color = (Color("#ff716b") if has_piece and not legal else Color("#6be7e6")) if chosen_cell else Color("#f5d77e")

func _modal_blocks_board_input() -> bool:
	if _interaction_suspended():
		return true
	if orientation_overlay != null and orientation_overlay.visible:
		return true
	if (rules_dialog != null and rules_dialog.visible) or (reset_dialog != null and reset_dialog.visible):
		return true
	if world_picker != null and world_picker.get_popup().visible:
		return true
	if top_menu != null and top_menu.get_popup().visible:
		return true
	if mobile_menu_panel != null and mobile_menu_panel.visible:
		return true
	# Nested popup windows can outlive the parent's focus for a frame.
	for submenu in [rule_submenu, difficulty_submenu, persona_submenu]:
		if submenu != null and submenu.visible:
			return true
	# The qualified Pirate opening controller is a CanvasLayer above the live board.
	var pirate_choice := get_node_or_null("PirateOpeningChoiceSurface/PirateOpeningChoice") as Control
	return pirate_choice != null and pirate_choice.visible

# A live landscape resize, browser chrome change, DPI change or safe-area
# relayout can move perspective cells while the finger is held. The earlier
# state token bound only gameplay and could spend a rank on finger-up in the
# NEW geometry. Capture the actual hit-test coordinate system as well.
static func _touch_geometry_token(viewport_size: Vector2, physical_size: Vector2i, board_rect: Rect2, density: float) -> Array:
	return [viewport_size, physical_size, board_rect, snappedf(density, 0.001)]

func _touch_board_state_token() -> Array:
	# Nested arrays/Vector2/Rect2 compare by value; no second gameplay engine.
	# _perspective_board_rect() includes live reserve-dock clearance, so a
	# safe-area/layout change invalidates the gesture even before _process.
	return [current_world, current_rule, turn, moves, round_number,
		selected_reserve, selected_cell, ai_enabled, blocked_player,
		match_score.duplicate(),
		_touch_geometry_token(get_viewport_rect().size, get_window().size,
			_perspective_board_rect(), _native_touch_density())]

func _cancel_pending_board_touch() -> void:
	# Preserve _touch_primary_active until its release so the synthetic mouse
	# echo is still recognized; a new touch-down always resets the token.
	_touch_board_pending = false
	_touch_board_state_at_press.clear()
	_refresh_touch_preview()

# Board polygons have 44-physical-pixel touch forgiveness. On a 746x280
# screen that forgiving area can overlap the reserve/topbar despite the
# visible board's 6px clearance. A touch must NEVER spend a rank if its
# RELEASE or DRAG ends on UI, even if it started on a valid board cell and
# remains within the 16dp tap-drift allowance. The two zones are evaluated
# from the LIVE layout, not reference screenshot coordinates.
static func _touch_over_chrome_rects(point: Vector2, topbar_rect: Rect2, dock_rect: Rect2) -> bool:
	return topbar_rect.has_point(point) or dock_rect.has_point(point)

func _touch_over_live_chrome(point: Vector2) -> bool:
	var topbar := get_node("SafeArea/Landscape/Center/TopBar") as Control
	var dock := get_node("SafeArea/Landscape/Center/ReserveDock") as Control
	return _touch_over_chrome_rects(point, topbar.get_global_rect(), dock.get_global_rect())

# A genuine tap and a horizontal reserve swipe can both end over a Button.
# Record the complete primary gesture BEFORE Godot dispatches GUI pressed;
# only a fresh primary press clears a prior swipe's short mouse-echo guard.
# This does not consume input, alter the ScrollContainer, or touch game state.
func _track_reserve_touch_gesture(event: InputEvent) -> void:
	if event is InputEventScreenTouch:
		var touch := event as InputEventScreenTouch
		if touch.index != 0:
			if touch.pressed and (_reserve_touch_active or (reserve_scroller != null
					and reserve_scroller.visible and reserve_scroller.get_global_rect().has_point(touch.position))):
				# Secondary-first contact must not permanently block real mouse clicks.
				if _reserve_touch_active:
					_reserve_touch_swiped = true
				_reserve_touch_block_until_msec = Time.get_ticks_msec() + TOUCH_MOUSE_ECHO_MS
			return
		if touch.pressed:
			_reserve_touch_active = (reserve_scroller != null and reserve_scroller.visible
				and reserve_scroller.get_global_rect().has_point(touch.position))
			_reserve_touch_origin = touch.position
			_reserve_touch_swiped = _reserve_touch_active and not _touch_secondary_indices.is_empty()
			if _reserve_touch_active:
				_reserve_touch_block_until_msec = 0
				# A new real finger-down supersedes an older pointer drag guard.
				_reserve_pointer_block_until_msec = 0
		else:
			if _reserve_touch_active and _reserve_touch_swiped:
				_reserve_touch_block_until_msec = Time.get_ticks_msec() + TOUCH_MOUSE_ECHO_MS
			_reserve_touch_active = false
			_reserve_touch_swiped = false
	elif event is InputEventScreenDrag and _reserve_touch_active:
		var drag := event as InputEventScreenDrag
		if drag.index == 0:
			var max_drift := maxf(8.0, RESERVE_SWIPE_CANCEL_DP * _native_touch_density() / _physical_pixel_scale())
			if drag.position.distance_squared_to(_reserve_touch_origin) > max_drift * max_drift:
				_reserve_touch_swiped = true
	elif event is InputEventPanGesture:
		# Some browser/trackpad backends emit pan without ScreenDrag. Only
		# invalidate a gesture already anchored in the live reserve: a free
		# trackpad scroll must not disable the next unrelated mouse click.
		if _reserve_touch_active:
			_reserve_touch_swiped = true
		if _reserve_pointer_active:
			_reserve_pointer_dragged = true
	elif event is InputEventMouseButton:
		var pointer := event as InputEventMouseButton
		if pointer.button_index == MOUSE_BUTTON_LEFT:
			if pointer.pressed:
				_reserve_pointer_active = (reserve_scroller != null and reserve_scroller.visible
					and reserve_scroller.get_global_rect().has_point(pointer.position))
				_reserve_pointer_origin = pointer.position
				_reserve_pointer_dragged = false
				if _reserve_pointer_active:
					_reserve_pointer_block_until_msec = 0
			else:
				if _reserve_pointer_active and _reserve_pointer_dragged:
					_reserve_pointer_block_until_msec = Time.get_ticks_msec() + TOUCH_MOUSE_ECHO_MS
				_reserve_pointer_active = false
				_reserve_pointer_dragged = false
	elif event is InputEventMouseMotion and _reserve_pointer_active:
		var motion := event as InputEventMouseMotion
		if (motion.button_mask & MOUSE_BUTTON_MASK_LEFT) != 0:
			var max_drift := maxf(8.0, RESERVE_SWIPE_CANCEL_DP * _native_touch_density() / _physical_pixel_scale())
			if motion.position.distance_squared_to(_reserve_pointer_origin) > max_drift * max_drift:
				_reserve_pointer_dragged = true

# Reserve Buttons alone use this guarded GUI adapter. Direct keyboard/tutorial
# calls still use _on_reserve_pressed and therefore cannot be blocked by a
# preceding touch swipe. The existing D2 legality and selection logic is reused.
func _on_reserve_gui_pressed(player: int, index: int) -> void:
	if _reserve_touch_swiped or _reserve_pointer_dragged or (
			_reserve_touch_block_until_msec > 0
			and Time.get_ticks_msec() <= _reserve_touch_block_until_msec) or (
			_reserve_pointer_block_until_msec > 0
			and Time.get_ticks_msec() <= _reserve_pointer_block_until_msec):
		return
	_on_reserve_pressed(player, index)

# ScrollContainer.value_changed cannot distinguish a real swipe from layout
# clamping or ensure_control_visible(). Observe real pointer intent instead;
# do not consume events or change any board/reserve state. This is shared
# across the seven worlds and preserves normal GUI delivery.
func _track_reserve_scroll_intent(event: InputEvent) -> void:
	_track_reserve_touch_gesture(event)
	if reserve_scroller == null or not reserve_scroller.visible:
		return
	var position := Vector2(-10000.0, -10000.0)
	var intentional := false
	if event is InputEventScreenTouch:
		var touch := event as InputEventScreenTouch
		position = touch.position
		intentional = touch.pressed
	elif event is InputEventScreenDrag:
		position = (event as InputEventScreenDrag).position
		intentional = true
	elif event is InputEventPanGesture:
		position = (event as InputEventPanGesture).position
		intentional = true
	elif event is InputEventMouseButton:
		var mouse := event as InputEventMouseButton
		position = mouse.position
		intentional = mouse.pressed and mouse.button_index in [
			MOUSE_BUTTON_LEFT, MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN,
			MOUSE_BUTTON_WHEEL_LEFT, MOUSE_BUTTON_WHEEL_RIGHT]
	elif event is InputEventMouseMotion:
		var motion := event as InputEventMouseMotion
		position = motion.position
		intentional = (motion.button_mask & MOUSE_BUTTON_MASK_LEFT) != 0
	if intentional and reserve_scroller.get_global_rect().has_point(position):
		_reserve_scroll_user_epoch += 1

func _reserve_scroll_request_current(player: int, world: int, round_id: int,
		move_count: int, rank_index: int, user_epoch: int) -> bool:
	return (turn == player and current_world == world and round_number == round_id
		and moves == move_count and selected_reserve == rank_index
		and _reserve_scroll_user_epoch == user_epoch)

func _input(event: InputEvent) -> void:
	_track_reserve_scroll_intent(event)
	# Board moves commit only after a primary touch RELEASE over the same cell.
	# Track the full path: a swipe that leaves its cell and returns must never
	# spend a piece. A secondary finger cancels the primary gesture permanently.
	if event is InputEventScreenTouch:
		var touch := event as InputEventScreenTouch
		if touch.index != 0:
			# Secondary-first and primary-first gestures are both non-taps.
			# An OS can synthesize a mouse event from ANY finger, so retain
			# the short board-local echo guard on both press and release.
			if touch.pressed:
				_touch_secondary_indices[touch.index] = true
				_cancel_pending_board_touch()
			else:
				_touch_secondary_indices.erase(touch.index)
			_touch_mouse_echo_position = touch.position
			_touch_mouse_echo_deadline_msec = Time.get_ticks_msec() + TOUCH_MOUSE_ECHO_MS
			_touch_multifinger_mouse_echo_deadline_msec = _touch_mouse_echo_deadline_msec
			return
		if not touch.pressed:
			# A focus/rotation cancellation may clear the primary gesture before
			# release. Still suppress its possible synthetic mouse echo.
			if not _touch_primary_active:
				_touch_mouse_echo_position = touch.position
				_touch_mouse_echo_deadline_msec = Time.get_ticks_msec() + TOUCH_MOUSE_ECHO_MS
				return
			var was_board := _touch_board_started
			var should_commit := _touch_board_pending
			var initial_cell := _touch_board_cell
			var origin := _touch_board_origin
			var initial_state := _touch_board_state_at_press.duplicate(true)
			# Refresh the echo guard on EVERY release, even after a canceled
			# gesture or a touch that began on UI. A long hold can outlast 350ms.
			_touch_mouse_echo_position = touch.position
			_touch_mouse_echo_deadline_msec = Time.get_ticks_msec() + TOUCH_MOUSE_ECHO_MS
			_touch_primary_active = false
			_touch_board_started = false
			_touch_board_pending = false
			_touch_board_cell = -1
			_touch_board_state_at_press.clear()
			_refresh_touch_preview()
			if was_board:
				get_viewport().set_input_as_handled()
			if not should_commit:
				return
			if initial_state.is_empty() or initial_state != _touch_board_state_token():
				return
			# A near-edge finger-up can be BOTH inside an expanded board target
			# and over the active reserve. UI always wins at release, just as it
			# already does at press; otherwise an intended reserve tap spends a
			# selected rank on the last row of the board.
			if _touch_over_live_chrome(touch.position):
				return
			if perspective_tiles.size() != 9 or game_over or _modal_blocks_board_input() or (ai_enabled and turn == 2):
				return
			var max_drift := maxf(8.0, TOUCH_TAP_DRIFT_DP * _native_touch_density() / _physical_pixel_scale())
			if touch.position.distance_squared_to(origin) > max_drift * max_drift:
				return
			var released_cell := PerspectiveGeometry.cell_at_touch(
				current_world, touch.position, perspective_rect,
				ceilf(_minimum_touch_physical_px() / _physical_pixel_scale()))
			if released_cell != initial_cell:
				return
			_last_board_press_frame = Engine.get_process_frames()
			_last_board_press_position = touch.position
			_last_board_press_kind = "touch"
			_on_cell_pressed(initial_cell)
			return
		# Track ALL primary touches for mouse-echo suppression, but only
		# consume events that actually begin on a live board cell. GUI taps
		# must remain available to the reserve and the top menu.
		_touch_primary_active = true
		_touch_board_started = false
		_touch_board_pending = false
		_touch_board_cell = -1
		_touch_board_state_at_press.clear()
		_refresh_touch_preview()
		_touch_board_origin = touch.position
		_touch_mouse_echo_origin = touch.position
		_touch_mouse_echo_position = touch.position
		_touch_mouse_echo_deadline_msec = Time.get_ticks_msec() + TOUCH_MOUSE_ECHO_MS
		# If finger 1 was already down, finger 0 must not arm a board tap.
		# A later finger-1 release does not retroactively authorize it.
		if not _touch_secondary_indices.is_empty():
			return
		if perspective_tiles.size() != 9 or game_over or _modal_blocks_board_input() or (ai_enabled and turn == 2):
			return
		var touch_topbar := get_node("SafeArea/Landscape/Center/TopBar") as Control
		var touch_dock := get_node("SafeArea/Landscape/Center/ReserveDock") as Control
		if touch_topbar.get_global_rect().has_point(touch.position) or touch_dock.get_global_rect().has_point(touch.position):
			return
		var touch_index := PerspectiveGeometry.cell_at_touch(
			current_world, touch.position, perspective_rect,
			ceilf(_minimum_touch_physical_px() / _physical_pixel_scale()))
		if touch_index < 0:
			return
		_touch_board_started = true
		_touch_board_pending = true
		_touch_board_cell = touch_index
		_touch_board_state_at_press = _touch_board_state_token()
		_refresh_touch_preview()
		get_viewport().set_input_as_handled()
		return
	if event is InputEventScreenDrag:
		var drag := event as InputEventScreenDrag
		if drag.index != 0:
			# A secondary finger can move across OTHER cells while primary touch
			# remains down. Refresh the echo location even though that finger
			# never owns a board move; some touch backends emulate mouse-down
			# at the secondary finger's NEW position.
			if _touch_secondary_indices.has(drag.index):
				_touch_mouse_echo_position = drag.position
				_touch_mouse_echo_deadline_msec = Time.get_ticks_msec() + TOUCH_MOUSE_ECHO_MS
				_touch_multifinger_mouse_echo_deadline_msec = _touch_mouse_echo_deadline_msec
			return
		if not _touch_primary_active:
			return
		_touch_mouse_echo_position = drag.position
		_touch_mouse_echo_deadline_msec = Time.get_ticks_msec() + TOUCH_MOUSE_ECHO_MS
		if not _touch_board_pending:
			return
		# Cancel the preview as soon as the finger enters a live UI control.
		# A return to the board cannot rearm this same gesture.
		if _touch_over_live_chrome(drag.position):
			_cancel_pending_board_touch()
			get_viewport().set_input_as_handled()
			return
		var max_drift := maxf(8.0, TOUCH_TAP_DRIFT_DP * _native_touch_density() / _physical_pixel_scale())
		var drifted := drag.position.distance_squared_to(_touch_board_origin) > max_drift * max_drift
		var traversed_cell := PerspectiveGeometry.cell_at_touch(
			current_world, drag.position, perspective_rect,
			ceilf(_minimum_touch_physical_px() / _physical_pixel_scale()))
		if drifted or traversed_cell != _touch_board_cell:
			_cancel_pending_board_touch()
		get_viewport().set_input_as_handled()
		return
	if not (event is InputEventMouseButton):
		return
	var mouse := event as InputEventMouseButton
	if mouse.button_index != MOUSE_BUTTON_LEFT or not mouse.pressed:
		return
	if perspective_tiles.size() != 9 or game_over or _modal_blocks_board_input() or (ai_enabled and turn == 2):
		return
	var topbar := get_node("SafeArea/Landscape/Center/TopBar") as Control
	var dock := get_node("SafeArea/Landscape/Center/ReserveDock") as Control
	if topbar.get_global_rect().has_point(mouse.position) or dock.get_global_rect().has_point(mouse.position):
		return
	var index := PerspectiveGeometry.cell_at(current_world, mouse.position, perspective_rect)
	if index < 0:
		return
	# Godot marks touchscreen-generated mouse events with DEVICE_ID_EMULATION.
	# Such an event can arrive BEFORE its ScreenTouch press; the previous
	# finger-active and 350ms guards cannot catch that ordering. Only the
	# ScreenTouch release may place a rank. Keep mouse emulation enabled for
	# GUI reserve/menu Buttons; suppress its board route alone. A real mouse
	# retains the exact polygon/click-on-press path below.
	if mouse.device == InputEvent.DEVICE_ID_EMULATION:
		get_viewport().set_input_as_handled()
		return
	# A touch held ANYWHERE on the screen (including a secondary finger)
	# owns the gesture until finger-up. Never accept an unrelated board
	# mouse-down during that hold: touch-to-mouse emulation is not required
	# to stay near the original primary or secondary contact point. This
	# guard applies ONLY to board events, not reserve/menu GUI controls.
	if _touch_primary_active or not _touch_secondary_indices.is_empty():
		get_viewport().set_input_as_handled()
		return
	# A multitouch backend can replay a mouse press at an INTERMEDIATE
	# secondary-finger position after release. A bounded 350ms board-only
	# guard is safer than matching only the final primary contact point.
	if _touch_multifinger_mouse_echo_deadline_msec > 0 and Time.get_ticks_msec() <= _touch_multifinger_mouse_echo_deadline_msec:
		get_viewport().set_input_as_handled()
		return
	# After ALL fingers are up, reject the local delayed synthetic echo.
	# A later independent desktop mouse click is not globally disabled.
	if Time.get_ticks_msec() <= _touch_mouse_echo_deadline_msec and (
			mouse.position.distance_squared_to(_touch_mouse_echo_position) <= 36.0
			or mouse.position.distance_squared_to(_touch_mouse_echo_origin) <= 36.0):
		get_viewport().set_input_as_handled()
		return
	var frame := Engine.get_process_frames()
	if _last_board_press_kind == "touch" and frame >= _last_board_press_frame and frame - _last_board_press_frame <= 2 and mouse.position.distance_squared_to(_last_board_press_position) <= 16.0:
		get_viewport().set_input_as_handled()
		return
	_last_board_press_frame = frame
	_last_board_press_position = mouse.position
	_last_board_press_kind = "mouse"
	_on_cell_pressed(index)
	get_viewport().set_input_as_handled()

func _process(_delta: float) -> void:
	_ensure_physical_touch_targets()
	_sync_live_reserve_rank_typography()
	_sync_orientation_gate()
	_sync_mobile_menu_trigger()
	_layout_reference_menu_hotspot()
	_layout_canonical_live_logo()
	# Monotonic expiry restores the normal turn indicator without another Timer,
	# modal, or per-frame HUD redraw. A terminal result always takes precedence.
	if _hud_notice_deadline_msec > 0 and Time.get_ticks_msec() >= _hud_notice_deadline_msec:
		_hud_notice_deadline_msec = 0
		_hud_notice_text = ""
		_refresh_match_hud()
	# Resume a paused AI turn on the first unblocked frame. This is a
	# bounded single-shot queue, not a per-frame opponent move loop.
	_queue_ai_turn_if_ready()
	if perspective_tiles.size() == 9 and (
			perspective_rect != _perspective_board_rect()
			or absf(_physical_pixel_scale() - _last_perspective_pixel_scale) > 0.0001
			or absf(_native_touch_density() - _last_perspective_density) > 0.0001):
		# Cancel BEFORE the newly positioned polygons become interactive.
		# Retain primary-finger tracking until release to suppress mouse echoes.
		_cancel_pending_board_touch()
		_refresh_perspective_layer()
	var size := get_viewport_rect().size
	var status := get_node("SafeArea/Landscape/Center/Status") as Label
	var base := "R%d • P%d • score %d–%d • %d×%d • moves %d" % [round_number, turn, match_score[0], match_score[1], int(size.x), int(size.y), moves]
	if match_winner != 0:
		base = "MATCH • P%d wins • %d–%d • Menu: new match" % [match_winner, match_score[0], match_score[1]]
	elif game_over and winner != 0:
		base = "ROUND %d • P%d wins • %d–%d • Menu: next round" % [round_number, winner, match_score[0], match_score[1]]
	elif game_over and round_draw:
		base = "ROUND %d • DRAW • %d–%d • Menu: next round" % [round_number, match_score[0], match_score[1]]
	elif blocked_player != 0:
		base = "R%d • P%d blocked • P%d continues • score %d–%d" % [round_number, blocked_player, turn, match_score[0], match_score[1]]
	if size.x < size.y:
		base += " • rotate device"
	if selected_reserve >= 0:
		base += " • reserve %d selected" % selected_reserve
	if selected_cell >= 0:
		base += " • cell %d selected" % selected_cell
	status.text = base

# Deferred until the new reserve has completed layout. The old row may be
# wider than the new one; clamp against the live scrollbar, never a stale size.
# A quick second turn/menu change invalidates the deferred restoration.
func _restore_active_reserve_scroll(player: int, world: int, round_id: int,
		move_count: int, rank_index: int, user_epoch: int) -> void:
	await get_tree().process_frame
	if reserve_scroller == null or game_over or not reserve_scroller.visible or turn != player:
		return
	if player < 1 or player > 2 or _last_reserve_scroll_player != player:
		return
	if not _reserve_scroll_request_current(player, world, round_id, move_count, rank_index, user_epoch):
		return
	var bar := reserve_scroller.get_h_scroll_bar()
	var max_scroll := maxi(0, int(ceilf(bar.max_value - bar.page)))
	reserve_scroller.scroll_horizontal = clampi(_reserve_scroll_by_player[player - 1], 0, max_scroll)

func _reserve_node(player: int) -> GridContainer:
	return get_node("SafeArea/Landscape/Center/ReserveDock/ReserveScroll/ReserveRow/ReserveOne" if player == 1 else "SafeArea/Landscape/Center/ReserveDock/ReserveScroll/ReserveRow/ReserveTwo") as GridContainer

func _reject_reserve_selection(reason: String) -> void:
	# A failed touch/click must not preserve a previously selected legal rank.
	# Otherwise the next board tap can place a different piece than the one
	# the player just tried to select. This guard shares keyboard semantics.
	_on_secondary()
	_play_feedback("invalid")
	_update_status(reason)

# The active reserve must distinguish an unspent rank from a rank that can
# actually be played THIS turn. The same authoritative D2 legality predicate
# drives both the dimmed visual state and the tap response; no second rules
# engine, rank hiding or smaller hit targets are introduced.
func _rank_has_legal_cell(player: int, rank: int) -> bool:
	if player != turn or game_over or rank < 1 or rank > 9:
		return false
	for cell in range(CELL_NAMES.size()):
		if _is_legal_move(player, rank, cell):
			return true
	return false

func _on_reserve_pressed(player: int, index: int) -> void:
	if game_over or _modal_blocks_board_input():
		return
	# Guard invalid programmatic/stale GUI signals before indexing reserves.
	if player < 1 or player > 2 or index < 0 or index >= 9:
		_reject_reserve_selection("invalid reserve index")
		return
	if ai_enabled and player == 2:
		_reject_reserve_selection("AI reserve is not human-controllable")
		return
	if player != turn:
		_reject_reserve_selection("wrong player reserve")
		return
	if not reserve_available[player - 1][index]:
		_reject_reserve_selection("piece already played")
		return
	if not _rank_has_legal_cell(player, index + 1):
		_reject_reserve_selection("для ранга %d нет допустимой клетки" % (index + 1))
		return
	# Touch-only players have no physical Escape key. A second tap on the
	# SAME live rank cancels its selection, clears all nine legal outlines,
	# and never spends the piece or commits a hidden board move. This uses
	# the existing shared cancellation path in all seven worlds.
	if selected_reserve == index:
		_on_secondary()
		return
	selected_reserve = index
	selected_cell = -1
	_play_feedback("select")
	_refresh_selection_feedback()
	_update_status("reserve %d" % index)

func _top_piece(cell: int) -> Dictionary:
	return {} if board_stacks[cell].is_empty() else board_stacks[cell][-1]

func _is_legal_move(player: int, rank: int, cell: int) -> bool:
	if game_over or player != turn or cell < 0 or cell > 8 or rank < 1 or rank > 9:
		return false
	if not reserve_available[player - 1][rank - 1]:
		return false
	var top := _top_piece(cell)
	if top.is_empty():
		return true
	if int(top.player) == player or rank <= int(top.rank):
		return false
	if (current_rule == "C" or current_rule == "CD") and board_stacks[cell].size() >= 2:
		return false
	return true

func _winning_line(player: int) -> Array:
	for line in LINES:
		var ranks: Array[int] = []
		var owned := true
		for cell in line:
			var top := _top_piece(cell)
			if top.is_empty() or int(top.player) != player:
				owned = false
				break
			ranks.append(int(top.rank))
		if not owned:
			continue
		var ladder := (ranks[0] < ranks[1] and ranks[1] < ranks[2]) or (ranks[0] > ranks[1] and ranks[1] > ranks[2])
		if current_rule == "C" or ladder:
			return line.duplicate()
	return []

func _has_legal_move(player: int) -> bool:
	for rank in range(1, 10):
		if not reserve_available[player - 1][rank - 1]:
			continue
		for cell in range(9):
			if _is_legal_move_for(player, rank, cell):
				return true
	return false

func _is_legal_move_for(player: int, rank: int, cell: int) -> bool:
	if game_over or cell < 0 or cell > 8 or not reserve_available[player - 1][rank - 1]:
		return false
	var top := _top_piece(cell)
	if top.is_empty():
		return true
	if int(top.player) == player or rank <= int(top.rank):
		return false
	if (current_rule == "C" or current_rule == "CD") and board_stacks[cell].size() >= 2:
		return false
	return true

func _on_cell_pressed(index: int) -> void:
	if game_over or _modal_blocks_board_input() or (ai_enabled and turn == 2) or index < 0 or index >= CELL_NAMES.size():
		return
	selected_cell = index
	if selected_reserve >= 0:
		_on_primary()
	else:
		_refresh_selection_feedback()
		_update_status("cell %d" % index)

# Website RC2.6 Undo removes a human placement and ALL AI replies as one
# transaction. When P1 has no legal move, D2 may let P2 act repeatedly; the
# previous two-entry assumption disabled Undo precisely in that live state.
# Local two-player moves still undo one at a time. An AI-only even-round
# opening has no preceding human placement and remains non-undoable.
func _undo_steps() -> int:
	if _undo_history.is_empty():
		return 0
	var last: Dictionary = _undo_history[-1]
	if not bool(last["was_ai"]):
		return 1
	var ai_tail := 0
	for index in range(_undo_history.size() - 1, -1, -1):
		var entry: Dictionary = _undo_history[index]
		if bool(entry["was_ai"]):
			# Never fold a malformed or non-P2 AI record into a human turn.
			if int(entry["player"]) != 2:
				return 0
			ai_tail += 1
			continue
		if int(entry["player"]) != 1:
			return 0
		return ai_tail + 1
	return 0

func _undo_last_move() -> void:
	var steps := _undo_steps()
	if steps == 0:
		return
	# Validate BEFORE removing history. A malformed in-memory entry must not
	# discard the user's last valid undo opportunity or partially mutate play.
	var previous: Dictionary = _undo_history[_undo_history.size() - steps]["before"]
	if not _match_snapshot_valid(previous):
		push_error("Blue Sea Undo: invalid pre-move snapshot; no state changed")
		return
	_cancel_pending_board_touch()
	_ai_turn_queued = false
	for _step in range(steps):
		_undo_history.pop_back()
	# Preserve the earlier undo entries, but restore all actual gameplay fields
	# (including terminal score and reserves) from one exact pre-move state.
	_apply_match_snapshot(previous, true)
	_refresh_surface()
	_save_match()
	_update_status("move undone")
	_queue_ai_turn_if_ready()

func _on_primary() -> void:
	# The hidden legacy ActionPrimary button and deferred GUI signals share this
	# final commit path with touch, keyboard and AI. All those entrypoints must
	# respect the SAME lifecycle/modal gate: a queued press must not spend a
	# rank behind an open phone menu, reset confirmation or paused application.
	# AI calls this only after its own readiness check; never bypass the gate.
	if _modal_blocks_board_input():
		return
	if selected_reserve < 0 or selected_cell < 0:
		_update_status("select reserve and cell")
		return
	var rank := selected_reserve + 1
	if not _is_legal_move(turn, rank, selected_cell):
		_play_feedback("invalid")
		_update_status("illegal move")
		return
	var moving_player := turn
	# Record only a legal, about-to-commit move. No history for invalid taps,
	# selection, world switches or menu actions. A round has at most 18 pieces.
	if _undo_history.size() >= 18:
		_undo_history.pop_front()
	_undo_history.append({"before": _match_snapshot(), "player": moving_player,
		"was_ai": ai_enabled and moving_player == 2})
	# A blocked opponent may have yielded the turn to this player. A winning
	# placement ends the round without entering the non-winning branch below;
	# clear the stale blocked marker BEFORE evaluating that terminal move.
	# Otherwise the legitimate win produces an invalid persisted snapshot
	# (game_over + blocked_player), and reload silently loses the winning move.
	blocked_player = 0
	board_stacks[selected_cell].append({"player": moving_player, "rank": rank})
	reserve_available[moving_player - 1][selected_reserve] = false
	moves += 1
	win_line = _winning_line(moving_player)
	if not win_line.is_empty():
		winner = moving_player
		game_over = true
		match_score[moving_player - 1] += 1
		if match_score[moving_player - 1] >= MATCH_TARGET:
			match_winner = moving_player
	else:
		blocked_player = 0
		turn = 2 if moving_player == 1 else 1
		if not _has_legal_move(turn):
			blocked_player = turn
			turn = moving_player
			if not _has_legal_move(turn):
				game_over = true
				round_draw = true
				blocked_player = 0
	selected_reserve = -1
	selected_cell = -1
	_play_feedback("win" if game_over and winner != 0 else "place", not (ai_enabled and moving_player == 2))
	_refresh_surface()
	_save_match()
	_update_status("game won" if winner != 0 else "move committed")
	_queue_ai_turn_if_ready()

func _on_secondary() -> void:
	selected_reserve = -1
	selected_cell = -1
	_refresh_selection_feedback()
	_update_status("selection cleared")

func _reset_round() -> void:
	# Undo never crosses a round or match boundary.
	_undo_history.clear()
	# Never carry a previous round's transient phone feedback into the next.
	_hud_notice_text = ""
	_hud_notice_deadline_msec = 0
	# A new round starts with all ranks available: both players return to rank 1.
	_reserve_scroll_by_player = [0, 0]
	_last_reserve_scroll_player = 0
	if reserve_scroller != null:
		reserve_scroller.scroll_horizontal = 0
	board_stacks = [[],[],[],[],[],[],[],[],[]]
	reserve_available = [[true,true,true,true,true,true,true,true,true],[true,true,true,true,true,true,true,true,true]]
	winner = 0
	win_line = []
	game_over = false
	round_draw = false
	blocked_player = 0
	selected_reserve = -1
	selected_cell = -1
	moves = 0
	turn = 1 if round_number % 2 == 1 else 2
	_refresh_surface()
	_save_match()
	_queue_ai_turn_if_ready()

func _on_menu() -> void:
	if not game_over:
		_update_status("menu action")
		return
	if match_winner != 0:
		match_score = [0, 0]
		match_winner = 0
		round_number = 1
		_reset_round()
		_update_status("new match")
	else:
		round_number += 1
		_reset_round()
		_update_status("next round")

# Translate existing gameplay feedback, not internal debug strings. The phone
# HUD is only 100 logical pixels wide, so every notice is deliberately short.
static func _hud_notice_for_event(event: String) -> String:
	match event:
		"illegal move", "invalid reserve index":
			return "НЕЛЬЗЯ"
		"piece already played":
			return "ЗАНЯТО"
		"wrong player reserve", "AI reserve is not human-controllable":
			return "ЧУЖОЙ"
		"select reserve and cell":
			return "ВЫБЕРИ"
		"selection cleared":
			return "ОТМЕНА"
		"move undone":
			return "ОТМЕНЕНО"
		"move committed":
			return "ХОД ГОТОВ"
		"match resumed":
			return "ПРОДОЛЖ."
		"save recovered":
			return "СОХРАНЕНО"
		"save retry failed":
			return "НЕ СОХР."
		"AI blocked; human continues":
			return "ИИ ПАС"
	# v139 introduced a Russian unavailable-rank rejection, but the compact
	# phone HUD ignored that event while its ordinary Status label is hidden.
	# The short visible notice uses the existing HUD, never a new overlay.
	if event.begins_with("для ранга ") and event.ends_with(" нет допустимой клетки"):
		return "НЕТ ХОДА"
	if event.begins_with("reserve "):
		var rank_index := event.trim_prefix("reserve ")
		if rank_index.is_valid_int() and int(rank_index) >= 0 and int(rank_index) < 9:
			return "РАНГ %d" % (int(rank_index) + 1)
	if event.begins_with("cell ") or event.begins_with("keyboard cell "):
		var cell_index := event.trim_prefix("keyboard cell " if event.begins_with("keyboard cell ") else "cell ")
		if cell_index.is_valid_int() and int(cell_index) >= 0 and int(cell_index) < 9:
			return "КЛЕТКА %d" % (int(cell_index) + 1)
	return ""

# A selected rank may be scrolled completely off-screen in the single
# active-player reserve on a 746x280 phone. Keep its identity visible after
# transient notices expire, using the EXISTING two-line score HUD. This is
# presentation only: no new input surface or reserve is created.
static func _hud_selected_rank_line(normal: String, rank_index: int, player: int, mobile: bool, terminal: bool, ai_turn: bool) -> String:
	if not mobile or terminal or ai_turn or player < 1 or player > 2 or rank_index < 0 or rank_index > 8:
		return normal
	return "P%d · №%d" % [player, rank_index + 1]

static func _hud_secondary_line(normal: String, notice: String, deadline: int, now: int, mobile: bool, terminal: bool) -> String:
	return notice if mobile and not terminal and notice != "" and deadline > now else normal

func _refresh_match_hud() -> void:
	if match_hud_label == null:
		return
	var score := "%d:%d" % [match_score[0], match_score[1]]
	var state := "ХОД ИИ" if ai_enabled and turn == 2 else "ХОД P%d" % turn
	if match_winner != 0:
		state = "МАТЧ P%d" % match_winner
	elif game_over and round_draw:
		state = "НИЧЬЯ"
	elif game_over and winner != 0:
		state = "РАУНД P%d" % winner
	# Persistent human rank identity remains visible after the brief selection
	# notice. It never displaces AI turn, terminal result, or an urgent notice.
	var mobile := _use_mobile_menu()
	state = _hud_selected_rank_line(state, selected_reserve, turn, mobile, game_over,
		ai_enabled and turn == 2)
	state = _hud_secondary_line(state, _hud_notice_text, _hud_notice_deadline_msec,
		Time.get_ticks_msec(), _use_mobile_menu(), game_over)
	# Storage failure is a live product state, not a console-only warning.
	# Preserve terminal winner/draw on line 2; add a compact mark to score.
	if _match_save_dirty:
		score += " !"
		if not game_over:
			state = "НЕ СОХР."
	match_hud_label.text = score + "\n" + state
	match_hud.tooltip_text = "Раунд %d · счёт %s · %s" % [round_number, score, state]
	if _match_save_dirty:
		match_hud.tooltip_text += " · Не удалось сохранить матч; повторная попытка ограничена"

func _refresh_surface() -> void:
	# Capture BEFORE hiding the previous player's row: hiding can clamp the
	# ScrollContainer's current offset to zero on the same layout pass.
	var reserve_was_visible := reserve_scroller != null and reserve_scroller.visible
	if reserve_was_visible and _last_reserve_scroll_player in [1, 2]:
		_reserve_scroll_by_player[_last_reserve_scroll_player - 1] = reserve_scroller.scroll_horizontal
	(get_node("SafeArea/Landscape/RightRail/Actions/ActionMenu") as Button).visible = game_over
	if next_round_button != null:
		next_round_button.visible = game_over
		# A hidden mobile Status must not conceal who won. Next remains
		# absent during live play and occupies the dock only after the result.
		if match_winner != 0:
			next_round_button.text = "P%d ВЫИГРАЛ МАТЧ · НОВЫЙ" % match_winner
		elif round_draw:
			next_round_button.text = "НИЧЬЯ · ДАЛЬШЕ"
		elif winner != 0:
			next_round_button.text = "P%d ПОБЕДИЛ · ДАЛЬШЕ" % winner
		else:
			next_round_button.text = "СЛЕДУЮЩИЙ РАУНД"
	for i in range(CELL_NAMES.size()):
		var cell := get_node("SafeArea/Landscape/Center/BoardAspect/Board/" + CELL_NAMES[i]) as Button
		var top := _top_piece(i)
		_set_piece_badge(cell, null if top.is_empty() else world_visuals.piece_texture(current_world, int(top.player), int(top.rank)), 0 if top.is_empty() else int(top.rank))
		cell.disabled = game_over
	for player in [1, 2]:
		var reserve := _reserve_node(player)
		reserve.visible = player == turn and not game_over and (not ai_enabled or player == 1)
		for i in range(reserve.get_child_count()):
			var piece := reserve.get_child(i) as Button
			# A hidden opponent/AI reserve is NOT a texture consumer. The old
			# path decoded nine invisible 128px ranked sprites at every cold
			# world entry, then kept them attached to hidden RankArt nodes.
			# The turn switch rebuilds the newly active reserve from the same
			# authoritative reserve_available state; no rank or rule is lost.
			var show_rank := reserve.visible and reserve_available[player - 1][i]
			_set_piece_badge(piece,
				world_visuals.piece_texture(current_world, player, i + 1) if show_rank else null,
				i + 1 if show_rank else 0)
			piece.disabled = game_over or player != turn or (ai_enabled and player == 2) or not reserve_available[player - 1][i]
			# An available but currently unplayable rank stays at the SAME safe
			# touch size. Dim it; a tap explains why rather than selecting a
			# rank with zero highlighted legal cells. Spent ranks stay hidden.
			var can_place_rank := show_rank and _rank_has_legal_cell(player, i + 1)
			# Only fade the silhouette, never its live number or the touch button.
			# Fading the parent made ranks unreadable on 746x280 phones exactly
			# when the player needed to distinguish the unavailable pieces.
			piece.modulate = Color.WHITE
			var rank_art := piece.get_node_or_null("RankArt") as TextureRect
			if rank_art != null:
				rank_art.modulate.a = 0.53 if show_rank and not can_place_rank else 1.0
			piece.tooltip_text = "" if not show_rank or can_place_rank else "Нет допустимой клетки для ранга %d" % (i + 1)
	# A hidden opponent reserve must not leave a second scrollable row.
	# The terminal Next button is outside the scroller and never beneath pieces.
	_refresh_match_hud()
	if reserve_scroller != null:
		reserve_scroller.visible = not game_over and (not ai_enabled or turn == 1)
		if game_over:
			# Terminal UI replaces the reserve with Next; no stale offset is shown.
			reserve_scroller.scroll_horizontal = 0
		if _last_reserve_scroll_player != turn or (not reserve_was_visible and reserve_scroller.visible):
			_last_reserve_scroll_player = turn
			if reserve_scroller.visible:
				call_deferred("_restore_active_reserve_scroll", turn, current_world,
					round_number, moves, selected_reserve, _reserve_scroll_user_epoch)
	_refresh_perspective_layer()
	_refresh_selection_feedback()

func _update_status(event: String) -> void:
	var status := get_node("SafeArea/Landscape/Center/Status") as Label
	status.tooltip_text = event
	# The Status label is hidden at 746x280. Surface existing game feedback
	# inside the live two-line HUD without covering board, rank or reserve.
	var notice := _hud_notice_for_event(event)
	if notice != "" and not game_over and _use_mobile_menu():
		_hud_notice_text = notice
		_hud_notice_deadline_msec = Time.get_ticks_msec() + HUD_NOTICE_DURATION_MS
		_refresh_match_hud()

func _geometry_snapshot() -> Dictionary:
	var paths := {
		"safe": "SafeArea",
		"landscape": "SafeArea/Landscape",
		"left": "SafeArea/Landscape/LeftRail",
		"center": "SafeArea/Landscape/Center",
		"board": "SafeArea/Landscape/Center/BoardAspect/Board",
		"right": "SafeArea/Landscape/RightRail",
		"reserve1": "SafeArea/Landscape/Center/ReserveDock/ReserveScroll/ReserveRow/ReserveOne",
		"reserve2": "SafeArea/Landscape/Center/ReserveDock/ReserveScroll/ReserveRow/ReserveTwo",
		"actions": "SafeArea/Landscape/RightRail/Actions"
	}
	var out := {}
	for key in paths:
		var control := get_node(paths[key]) as Control
		out[key] = {"x": control.position.x, "y": control.position.y, "w": control.size.x, "h": control.size.y}
	return out

func _assert_min_control_size(control: Control, minimum: Vector2, label: String) -> void:
	assert(control.size.x + 0.01 >= minimum.x, "%s width %.2f < %.2f" % [label, control.size.x, minimum.x])
	assert(control.size.y + 0.01 >= minimum.y, "%s height %.2f < %.2f" % [label, control.size.y, minimum.y])

func _assert_landscape_geometry() -> void:
	await get_tree().process_frame
	await get_tree().process_frame
	var viewport := get_viewport_rect().size
	assert(viewport.x >= viewport.y, "landscape contract violated")
	var board := get_node("SafeArea/Landscape/Center/BoardAspect/Board") as GridContainer
	var dock := get_node("SafeArea/Landscape/Center/ReserveDock") as HBoxContainer
	assert(dock.size.y >= 44.0, "reserve dock too small")
	var pixel_scale := _physical_pixel_scale()
	if get_window().size.x >= 746 and get_window().size.y >= 280:
		for button in [mobile_world_button if _use_mobile_menu() else world_picker, ai_toggle, mobile_menu_button if _use_mobile_menu() else top_menu]:
			assert(button.size.x * pixel_scale >= _minimum_touch_physical_px() - 0.5 and button.size.y * pixel_scale >= _minimum_touch_physical_px() - 0.5, "toolbar touch below device-independent minimum")
		for player in [1, 2]:
			for piece in _reserve_node(player).get_children():
				assert(piece.size.x * pixel_scale >= _minimum_touch_physical_px() - 0.5 and piece.size.y * pixel_scale >= _minimum_touch_physical_px() - 0.5, "reserve touch below device-independent minimum")
	for i in range(CELL_NAMES.size()):
		assert(board.get_child(i).name == CELL_NAMES[i], "board order mismatch")
		_assert_min_control_size(board.get_child(i) as Control, Vector2(44, 44), "cell")
	for player in [1, 2]:
		var reserve := _reserve_node(player)
		assert(reserve.visible == (player == turn and not game_over and (not ai_enabled or player == 1)), "inactive or AI reserve visible")
		for piece in reserve.get_children():
			_assert_min_control_size(piece as Control, Vector2(44, 44), "reserve")
	# The scroll viewport must never inherit the nine-button content width;
	# otherwise native high-density phones lose ranks 8/9 offscreen.
	assert(reserve_scroller != null and reserve_scroller.get_parent() == dock)
	assert(reserve_scroller.horizontal_scroll_mode == ScrollContainer.SCROLL_MODE_AUTO)
	assert(reserve_scroller.vertical_scroll_mode == ScrollContainer.SCROLL_MODE_DISABLED)
	assert(reserve_scroller.size.x <= dock.size.x + 0.5, "reserve scroll viewport escaped phone width")
	var visible_reserve := _reserve_node(turn)
	if visible_reserve.visible and visible_reserve.size.x > reserve_scroller.size.x + 1.0:
		var last_piece := visible_reserve.get_child(8) as Button
		assert(last_piece.position.x + last_piece.size.x > reserve_scroller.size.x,
			"Overflow fixture expected ninth rank beyond initial viewport")
		var target_scroll := ceili(last_piece.position.x + last_piece.size.x - reserve_scroller.size.x)
		reserve_scroller.scroll_horizontal = target_scroll
		await get_tree().process_frame
		assert(reserve_scroller.scroll_horizontal > 0, "ninth rank cannot be reached by scrolling")
		reserve_scroller.scroll_horizontal = 0
	print("BLUE_SEA_MOBILE_DOCK_GEOMETRY_PASS ", viewport)

func _run_headless_native_mobile_profile_smoke() -> void:
	assert(_mobile_profile("Android", 1080, 3.0, true), "High-DPI Android must use mobile UI")
	assert(_mobile_profile("iOS", 1170, 3.0, true), "High-DPI iOS must use mobile UI")
	assert(_mobile_profile("web", 840, 3.0, true), "High-DPI touch web canvas must use mobile UI")
	assert(_mobile_profile("web", 280, 1.0, false), "746x280 desktop browser must use touch-safe UI")
	assert(_mobile_profile("web", 390, 1.0, true), "844x390 touch phone must use 44dp-safe menu")
	assert(_mobile_profile("web", 430, 1.0, true), "932x430 touch phone must use 44dp-safe menu")
	assert(not _mobile_profile("web", 390, 1.0, false), "844x390 pointer-only web retains desktop menu")
	assert(not _mobile_profile("web", 720, 1.0, true), "1280x720 touch desktop retains desktop menu")
	assert(not _mobile_profile("web", 1080, 1.0, false), "Desktop web retains desktop UI")
	assert(not _mobile_profile("X11", 1080, 2.0, true), "Large desktop retains desktop UI")
	print("BLUE_SEA_NATIVE_MOBILE_PROFILE_PASS")

func _run_headless_match_snapshot_smoke() -> void:
	# Pure validation and restore test; headless never reads/writes real user://.
	var original := _match_snapshot()
	assert(_match_snapshot_valid(original), "Fresh match must be restorable")
	var played := original.duplicate(true)
	played["board"][4] = [{"player": 1, "rank": 1}]
	played["reserves"][0][0] = false
	played["moves"] = 1
	played["turn"] = 2
	assert(_match_snapshot_valid(played), "One legal human move must survive reload")
	var invalid := played.duplicate(true)
	invalid["reserves"][0][0] = true
	assert(not _match_snapshot_valid(invalid), "Used rank cannot reappear after reload")
	invalid = played.duplicate(true)
	invalid["board"][4].append({"player": 2, "rank": 1})
	invalid["reserves"][1][0] = false
	invalid["moves"] = 2
	assert(not _match_snapshot_valid(invalid), "Cover cannot use equal rank")
	invalid = played.duplicate(true)
	invalid["game_over"] = true
	invalid["winner"] = 1
	assert(not _match_snapshot_valid(invalid), "False terminal win must be rejected")
	var terminal := original.duplicate(true)
	terminal["board"][0] = [{"player": 1, "rank": 1}]
	terminal["board"][1] = [{"player": 1, "rank": 2}]
	terminal["board"][2] = [{"player": 1, "rank": 3}]
	terminal["board"][3] = [{"player": 2, "rank": 1}]
	terminal["board"][4] = [{"player": 2, "rank": 2}]
	for rank in range(3):
		terminal["reserves"][0][rank] = false
	for rank in range(2):
		terminal["reserves"][1][rank] = false
	terminal["moves"] = 5
	terminal["score"] = [1, 0]
	terminal["winner"] = 1
	terminal["win_line"] = [0, 1, 2]
	terminal["game_over"] = true
	terminal["turn"] = 1
	assert(_match_snapshot_valid(terminal), "Completed round must survive reload")
	invalid = terminal.duplicate(true)
	invalid["win_line"] = [3, 4, 5]
	assert(not _match_snapshot_valid(invalid), "Terminal win line must match the live board")
	_apply_match_snapshot(played)
	assert(moves == 1 and turn == 2 and not reserve_available[0][0], "Valid reload lost a move")
	_apply_match_snapshot(original)
	assert(_match_snapshot() == original, "Match snapshot round-trip changed game state")
	_refresh_surface()
	_run_headless_match_atomic_io_smoke()
	_run_headless_cross_rule_resume_smoke()
	_run_headless_blocked_to_win_resume_smoke()
	_run_headless_ai_empty_resume_smoke()
	_run_headless_restored_human_turn_smoke()
	print("BLUE_SEA_MATCH_RESUME_PASS valid_roundtrip stale_rank_equal_cover_false_win_rejected")

func _run_headless_cross_rule_resume_smoke() -> void:
	# Simulate lost/stale preferences without ever touching user:// files.
	# D allows a deep stack and C allows non-ladder terminal rows; validation
	# must use the rule stored WITH the saved match, not the active default.
	var previous := _match_snapshot()
	for rule in ["C", "D", "CD"]:
		current_rule = rule
		var saved := _match_snapshot()
		current_rule = "D" if rule != "D" else "C"
		assert(_match_snapshot_valid(saved), "Valid saved rule rejected after settings loss: " + rule)
		_apply_match_snapshot(saved)
		assert(current_rule == rule and _match_snapshot() == saved, "Recovered rule/state mismatch")
		var bad := saved.duplicate(true)
		bad["rule"] = "INVALID"
		assert(not _match_snapshot_valid(bad), "Unknown rule accepted from JSON")
	current_rule = "D"
	var deep := previous.duplicate(true)
	deep["rule"] = "D"
	deep["board"][4] = [
		{"player": 1, "rank": 1}, {"player": 2, "rank": 2},
		{"player": 1, "rank": 3}]
	deep["reserves"][0][0] = false
	deep["reserves"][1][1] = false
	deep["reserves"][0][2] = false
	deep["moves"] = 3
	deep["turn"] = 2
	current_rule = "CD"
	assert(_match_snapshot_valid(deep), "D deep stack rejected under stale CD preferences")
	deep["rule"] = "CD"
	assert(not _match_snapshot_valid(deep), "CD illegally accepted deep stack")
	var free_line := previous.duplicate(true)
	free_line["rule"] = "C"
	free_line["board"][0] = [{"player": 1, "rank": 3}]
	free_line["board"][1] = [{"player": 1, "rank": 1}]
	free_line["board"][2] = [{"player": 1, "rank": 2}]
	for rank in range(3):
		free_line["reserves"][0][rank] = false
	free_line["moves"] = 3
	free_line["turn"] = 1
	free_line["score"] = [1, 0]
	free_line["winner"] = 1
	free_line["win_line"] = [0, 1, 2]
	free_line["game_over"] = true
	current_rule = "CD"
	assert(_match_snapshot_valid(free_line), "C non-ladder victory rejected under stale CD preferences")
	free_line["rule"] = "CD"
	assert(not _match_snapshot_valid(free_line), "CD illegally accepted non-ladder victory")
	_apply_match_snapshot(previous)
	assert(_match_snapshot() == previous, "Cross-rule smoke changed the original match")
	print("BLUE_SEA_CROSS_RULE_RESUME_PASS C_D_CD_deep_stack_invalid_rule")

func _run_headless_blocked_to_win_resume_smoke() -> void:
	# A real D-rule position can exhaust all nine opposing ranks while the
	# active player retains a legal terminal placement. This used to leave
	# blocked_player=2 after victory, making _save_match reject a valid win.
	var previous := _match_snapshot()
	var previous_ai := ai_enabled
	current_rule = "D"
	ai_enabled = false
	board_stacks = [
		[{"player": 1, "rank": 1}], [{"player": 1, "rank": 2}], [],
		[{"player": 2, "rank": 1}, {"player": 1, "rank": 4}, {"player": 2, "rank": 7}],
		[{"player": 2, "rank": 2}, {"player": 1, "rank": 5}, {"player": 2, "rank": 9}],
		[{"player": 2, "rank": 3}, {"player": 1, "rank": 6}, {"player": 2, "rank": 8}],
		[{"player": 2, "rank": 4}], [{"player": 2, "rank": 6}], [{"player": 2, "rank": 5}]
	]
	reserve_available = [
		[false, false, true, false, false, false, true, true, true],
		[false, false, false, false, false, false, false, false, false]
	]
	turn = 1
	moves = 14
	round_number = 1
	match_score = [0, 0]
	winner = 0
	win_line = []
	game_over = false
	round_draw = false
	match_winner = 0
	blocked_player = 2
	selected_reserve = -1
	selected_cell = -1
	assert(_match_snapshot_valid(_match_snapshot()), "Pre-win blocked D snapshot invalid")
	assert(not _has_legal_move(2), "Opponent should have exhausted all ranks")
	assert(_winning_line(1).is_empty() and _winning_line(2).is_empty(), "Already terminal")
	_on_reserve_pressed(1, 2)
	_on_cell_pressed(2)
	assert(game_over and winner == 1 and win_line == [0, 1, 2], "Blocked-to-win move did not end round")
	assert(blocked_player == 0, "Terminal win retained a stale blocked marker")
	var winning_snapshot := _match_snapshot()
	assert(_match_snapshot_valid(winning_snapshot), "Winning round cannot survive reload")
	_apply_match_snapshot(winning_snapshot)
	assert(game_over and winner == 1 and blocked_player == 0, "Winning reload lost terminal state")
	_apply_match_snapshot(previous)
	ai_enabled = previous_ai
	_refresh_surface()
	print("BLUE_SEA_BLOCKED_TO_WIN_RESUME_PASS terminal_saved_round_valid")

func _run_headless_ai_empty_resume_smoke() -> void:
	# Real D-mode stacks with all P2 ranks exhausted and a remaining P1
	# rank. Simulate a stale but structurally valid interrupted snapshot
	# that resumes on the AI turn rather than the human skip transition.
	var previous := _match_snapshot()
	var previous_ai := ai_enabled
	current_rule = "D"
	ai_enabled = true
	board_stacks = [
		[{"player": 1, "rank": 1}], [{"player": 1, "rank": 2}], [],
		[{"player": 2, "rank": 1}, {"player": 1, "rank": 4}, {"player": 2, "rank": 7}],
		[{"player": 2, "rank": 2}, {"player": 1, "rank": 5}, {"player": 2, "rank": 9}],
		[{"player": 2, "rank": 3}, {"player": 1, "rank": 6}, {"player": 2, "rank": 8}],
		[{"player": 2, "rank": 4}], [{"player": 2, "rank": 6}], [{"player": 2, "rank": 5}]
	]
	reserve_available = [
		[false, false, true, false, false, false, true, true, true],
		[false, false, false, false, false, false, false, false, false]
	]
	turn = 2
	moves = 14
	round_number = 1
	match_score = [0, 0]
	winner = 0
	win_line = []
	game_over = false
	round_draw = false
	match_winner = 0
	blocked_player = 0
	selected_reserve = -1
	selected_cell = -1
	_ai_turn_queued = false
	assert(_match_snapshot_valid(_match_snapshot()), "Interrupted P2 snapshot must validate")
	assert(not _has_legal_move(2) and _has_legal_move(1), "Fixture needs a blocked AI and playable human")
	_refresh_surface()
	_play_ai_turn()
	assert(turn == 1 and blocked_player == 2 and not game_over, "AI no-op did not return turn to human")
	assert(_match_snapshot_valid(_match_snapshot()), "Recovered AI skip must be persistable")
	_queue_ai_turn_if_ready()
	assert(not _ai_turn_queued, "Blocked AI cannot be scheduled every frame")
	_on_reserve_pressed(1, 2)
	_on_cell_pressed(2)
	assert(game_over and winner == 1 and blocked_player == 0, "Human cannot finish after AI skip")
	_apply_match_snapshot(previous)
	ai_enabled = previous_ai
	_refresh_surface()
	print("BLUE_SEA_AI_EMPTY_RESUME_PASS no_spin human_recovery terminal_win")


func _run_headless_restored_human_turn_smoke() -> void:
	# Reverse the ownership of v85's valid D-mode exhausted-AI fixture:
	# P1 has spent all nine ranks, P2 has a playable rank-3 finish.
	# This is the actual saved-turn recovery path, not an AI-specific skip.
	var previous := _match_snapshot()
	var previous_ai := ai_enabled
	ai_enabled = false
	current_rule = "D"
	board_stacks = [
		[{"player": 2, "rank": 1}], [{"player": 2, "rank": 2}], [],
		[{"player": 1, "rank": 1}, {"player": 2, "rank": 4}, {"player": 1, "rank": 7}],
		[{"player": 1, "rank": 2}, {"player": 2, "rank": 5}, {"player": 1, "rank": 9}],
		[{"player": 1, "rank": 3}, {"player": 2, "rank": 6}, {"player": 1, "rank": 8}],
		[{"player": 1, "rank": 4}], [{"player": 1, "rank": 6}], [{"player": 1, "rank": 5}]
	]
	reserve_available = [
		[false, false, false, false, false, false, false, false, false],
		[false, false, true, false, false, false, true, true, true]
	]
	turn = 1
	moves = 14
	round_number = 1
	match_score = [0, 0]
	winner = 0
	win_line = []
	game_over = false
	round_draw = false
	match_winner = 0
	blocked_player = 0
	selected_reserve = -1
	selected_cell = -1
	assert(_match_snapshot_valid(_match_snapshot()), "Exhausted P1 resume fixture must validate")
	assert(not _has_legal_move(1) and _has_legal_move(2), "P1 must be blocked, P2 playable")
	assert(_reconcile_restored_turn(), "Exhausted human turn was not repaired")
	assert(turn == 2 and blocked_player == 1 and not game_over)
	assert(not _reconcile_restored_turn(), "Recovered turn must be idempotent")
	assert(_match_snapshot_valid(_match_snapshot()), "Human-turn repair invalidated persisted state")
	_refresh_surface()
	assert(_reserve_node(2).visible and not _reserve_node(1).visible, "Recovered active reserve not visible")
	_on_reserve_pressed(2, 2)
	_on_cell_pressed(2)
	assert(game_over and winner == 2 and blocked_player == 0, "Recovered P2 cannot finish")
	assert(_match_snapshot_valid(_match_snapshot()), "Recovered P2 victory cannot be saved")
	_apply_match_snapshot(previous)
	ai_enabled = previous_ai
	_refresh_surface()
	print("BLUE_SEA_RESTORED_HUMAN_TURN_PASS symmetric_skip idempotent visible_reserve victory")

func _run_headless_match_atomic_io_smoke() -> void:
	# The only headless file writes are isolated under a test-only name.
	# Production MATCH_STATE_PATH and preferences are never touched here.
	var path := "user://a5_v82_disposable_match_io_qualification.json"
	for suffix in ["", ".bak", ".tmp"]:
		var candidate := ProjectSettings.globalize_path(path + suffix)
		if FileAccess.file_exists(path + suffix):
			assert(DirAccess.remove_absolute(candidate) == OK)
	var original := _match_snapshot()
	assert(_write_match_atomically(path, original), "Initial atomic save failed")
	assert(_read_valid_match_at(path) == original, "Primary readback failed")
	var played := original.duplicate(true)
	played["board"][4] = [{"player": 1, "rank": 1}]
	played["reserves"][0][0] = false
	played["moves"] = 1
	played["turn"] = 2
	assert(_write_match_atomically(path, played), "Second atomic save failed")
	assert(_read_valid_match_at(path) == played, "New primary missing")
	assert(_read_valid_match_at(path + ".bak") == original, "Last valid backup missing")
	# Simulate an interrupted/corrupt primary without touching real user data.
	var damaged := FileAccess.open(path, FileAccess.WRITE)
	assert(damaged != null)
	damaged.store_string("{incomplete")
	damaged.close()
	assert(_read_valid_match_at(path).is_empty(), "Corruption not detected")
	assert(_read_valid_match_at(path + ".bak") == original, "Backup cannot recover")
	for suffix in ["", ".bak", ".tmp"]:
		if FileAccess.file_exists(path + suffix):
			assert(DirAccess.remove_absolute(ProjectSettings.globalize_path(path + suffix)) == OK)
	print("BLUE_SEA_MATCH_ATOMIC_IO_PASS primary_backup_corruption_recovery")

func _run_headless_reserve_scroll_resume_smoke() -> void:
	# Source-level fixture exercises the real snapshot validator and restore
	# function, not a second JSON/gameplay implementation. No user:// I/O.
	var original := _match_snapshot()
	var candidate := original.duplicate(true)
	candidate["reserve_scroll"] = [321, 654]
	assert(_match_snapshot_valid(candidate), "Valid two-player scroll offsets rejected")
	# Godot JSON may decode integral numbers as floats. Exercise the actual
	# stringify/parse boundary rather than only an in-memory typed Array.
	var decoded = JSON.parse_string(JSON.stringify(candidate))
	assert(decoded is Dictionary and _match_snapshot_valid(decoded), "Serialized scroll offsets rejected")
	_apply_match_snapshot(decoded)
	assert(_reserve_scroll_by_player == [321, 654], "Saved offsets not restored")
	assert(_last_reserve_scroll_player == 0, "Cold restore must rebind live scroller")
	var legacy := candidate.duplicate(true)
	legacy.erase("reserve_scroll")
	assert(_match_snapshot_valid(legacy), "Legacy v81-v90 match save was broken")
	_apply_match_snapshot(legacy)
	assert(_reserve_scroll_by_player == [0, 0], "Legacy scroll must start at zero")
	var integral_float := candidate.duplicate(true)
	integral_float["reserve_scroll"] = [321.0, 654.0]
	assert(_match_snapshot_valid(integral_float), "Integral JSON floats must be compatible")
	for malformed in [[-1, 0], [0, 1000001], [0], [0, 1, 2], [1.5, 2], ["5", 0]]:
		var invalid := candidate.duplicate(true)
		invalid["reserve_scroll"] = malformed
		assert(not _match_snapshot_valid(invalid), "Malformed scroll offsets accepted")
	_apply_match_snapshot(original)
	print("BLUE_SEA_RESERVE_SCROLL_COLD_RESUME_PASS legacy_compatible=true")

func _run_headless_scroll_idle_persistence_smoke() -> void:
	assert(reserve_scroll_save_timer != null and reserve_scroll_save_timer.one_shot)
	assert(reserve_scroll_save_timer.wait_time >= 0.5)
	var before := _reserve_scroll_by_player.duplicate()
	_on_reserve_scroll_changed(150.0)
	assert(reserve_scroll_save_timer.is_stopped(), "Headless scroll must not start a disk writer")
	assert(_reserve_scroll_by_player == before, "Scroll signal changed the game snapshot")
	print("BLUE_SEA_RESERVE_SCROLL_IDLE_SAVE_WIRED debounce=0.65 headless_io=disabled")

# Explicit native fixture: a new swipe/tap after a pending tutorial reveal or
# turn-scroll restore invalidates the OLD request in every world. The test
# observes the actual active ScrollContainer and real input event classes;
# it never edits the board or claims to simulate physical Android touch.
func _run_headless_deferred_scroll_intent_smoke() -> void:
	var saved_world := current_world
	var saved_ai := ai_enabled
	ai_enabled = false
	for world in range(WorldVisuals.WORLDS.size()):
		_set_world(world)
		assert(reserve_scroller.visible, "Human reserve must be visible for scroll intent")
		var old_epoch := _reserve_scroll_user_epoch
		var request_rank := selected_reserve
		assert(_reserve_scroll_request_current(turn, world, round_number, moves,
			request_rank, old_epoch), "Fresh deferred scroll context unexpectedly invalid")
		var tap := InputEventScreenTouch.new()
		tap.pressed = true
		tap.position = reserve_scroller.get_global_rect().get_center()
		_track_reserve_scroll_intent(tap)
		assert(_reserve_scroll_user_epoch == old_epoch + 1,
			"Real reserve touch did not invalidate deferred scroll")
		assert(not _reserve_scroll_request_current(turn, world, round_number, moves,
			request_rank, old_epoch), "Stale scroll request survived newer touch")
		assert(_reserve_scroll_request_current(turn, world, round_number, moves,
			request_rank, _reserve_scroll_user_epoch), "New scroll context is invalid")
	_set_world(saved_world)
	ai_enabled = saved_ai
	print("BLUE_SEA_DEFERRED_SCROLL_INTENT_PASS worlds=7 no_stale_auto_scroll")

func _run_headless_ai_fallback_smoke() -> void:
	var old_ai := ai_enabled
	var old_turn := turn
	var old_rule := current_rule
	var old_board := board_stacks.duplicate(true)
	var old_reserves := reserve_available.duplicate(true)
	var old_over := game_over
	game_over = false
	turn = 2
	current_rule = "CD"
	board_stacks = [[], [], [], [], [], [], [], [], []]
	reserve_available = [[true,true,true,true,true,true,true,true,true], [true,true,true,true,true,true,true,true,true]]
	assert(_resolve_ai_move({"rank": 9, "cell": 4}) == {"rank": 9, "cell": 4}, "Valid strategy move must be preserved")
	assert(_resolve_ai_move({}) == {"rank": 1, "cell": 0}, "Empty strategy response must not stall AI")
	assert(_resolve_ai_move({"rank": 99, "cell": 4}) == {"rank": 1, "cell": 0}, "Out-of-range rank must be safely rejected")
	assert(_resolve_ai_move({"rank": "9", "cell": 4}) == {"rank": 1, "cell": 0}, "Malformed rank must not be coerced")
	reserve_available[1] = [false,false,false,false,false,false,false,false,false]
	assert(_resolve_ai_move({}).is_empty(), "Spent AI reserve must not invent a piece")
	board_stacks = old_board
	reserve_available = old_reserves
	current_rule = old_rule
	turn = old_turn
	game_over = old_over
	ai_enabled = old_ai
	print("BLUE_SEA_AI_INVALID_PROPOSAL_RECOVERY_PASS")

# Regression: toggling AI inside the phone menu must not strand the hidden P2
# reserve. AI is suspended WHILE the modal is visible, then makes a real legal
# move through the existing deferred production turn handler after dismissal.
func _run_headless_ai_modal_resume_smoke() -> void:
	var saved := _match_snapshot()
	var saved_ai := ai_enabled
	ai_enabled = false
	_reset_round()
	turn = 2
	_refresh_surface()
	assert(moves == 0 and not game_over)
	mobile_menu_panel.show()
	_on_mobile_menu_action(106)
	assert(ai_enabled and turn == 2 and moves == 0)
	assert(not _ai_turn_queued, "AI must not queue behind an open phone menu")
	await get_tree().process_frame
	await get_tree().process_frame
	assert(moves == 0 and turn == 2, "AI moved under a visible menu")
	mobile_menu_panel.hide()
	await get_tree().process_frame
	await get_tree().process_frame
	await get_tree().process_frame
	assert(moves == 1 and turn == 1, "AI did not resume after the mobile menu closed")
	var placed := 0
	for stack in board_stacks:
		placed += stack.size()
	assert(placed == 1, "Resumed AI must commit exactly one live board move")
	# Portrait rotation is another modal exit: it must resume a previously
	# paused turn without permitting a hidden placement while portrait.
	ai_enabled = false
	_reset_round()
	turn = 2
	ai_enabled = true
	_refresh_surface()
	orientation_overlay.show()
	_queue_ai_turn_if_ready()
	assert(not _ai_turn_queued and moves == 0)
	orientation_overlay.hide()
	await get_tree().process_frame
	await get_tree().process_frame
	await get_tree().process_frame
	assert(moves == 1 and turn == 1, "AI did not resume after portrait gate cleared")
	ai_enabled = saved_ai
	_apply_match_snapshot(saved)
	_refresh_surface()
	_save_preferences()
	print("BLUE_SEA_AI_MODAL_EXIT_RESUME_PASS phone_menu=PASS portrait=PASS")

# Native-only contract: hidden reserve nodes own no textures or rank labels.
# Exercise local two-player turn switching and AI turn suppression using the
# real shared _refresh_surface(), then restore the exact pre-test match.
func _run_headless_lazy_reserve_smoke() -> void:
	var saved := _match_snapshot()
	var saved_ai := ai_enabled
	ai_enabled = false
	_reset_round()
	for active in [1, 2]:
		turn = active
		_refresh_surface()
		for player in [1, 2]:
			var reserve := _reserve_node(player)
			assert(reserve.visible == (player == active), "Wrong local-player reserve visibility")
			for piece in reserve.get_children():
				var art := (piece as Button).get_node("RankArt") as TextureRect
				var number := (piece as Button).get_node("RankNumber") as Label
				assert((art.texture != null) == reserve.visible, "Inactive reserve retained a texture")
				assert(number.visible == reserve.visible, "Inactive reserve retained a rank label")
		# An already-used rank must not retain its old image when the reserve
		# is still visible; remaining ranks stay fully tappable and numbered.
		reserve_available[active - 1][0] = false
		_refresh_surface()
		var spent := _reserve_node(active).get_child(0) as Button
		assert((spent.get_node("RankArt") as TextureRect).texture == null,
			"Spent active rank retained its image")
		assert(not (spent.get_node("RankNumber") as Label).visible,
			"Spent active rank retained its number")
		reserve_available[active - 1][0] = true
	ai_enabled = true
	turn = 2
	_refresh_surface()
	for player in [1, 2]:
		var reserve := _reserve_node(player)
		assert(not reserve.visible, "AI turn exposed a human reserve")
		for piece in reserve.get_children():
			var art := (piece as Button).get_node("RankArt") as TextureRect
			assert(art.texture == null, "AI turn retained a hidden reserve texture")
	game_over = true
	_refresh_surface()
	for player in [1, 2]:
		var reserve := _reserve_node(player)
		assert(not reserve.visible, "Terminal match exposed reserve")
		for piece in reserve.get_children():
			assert((piece as Button).get_node("RankArt") is TextureRect)
			assert(((piece as Button).get_node("RankArt") as TextureRect).texture == null,
				"Terminal match retained hidden reserve texture")
	ai_enabled = saved_ai
	_apply_match_snapshot(saved)
	_refresh_surface()
	print("BLUE_SEA_LAZY_RESERVE_PASS local_p1=9 local_p2=9 ai_hidden=18")

# A5 v122: reproduce two REAL rendered game states for each approved world.
# No flattened reference screenshot, independent game engine or fake mockup.
# The optional runner compares these captures to the seven immutable sources;
# its metrics are diagnostics, NEVER automatic VISUAL_PARITY acceptance.
const VISUAL_CAPTURE_SLUGS := [
	"01_nd_premium_void", "02_pirate_sea", "03_atlantis",
	"04_gods_of_the_deep", "05_sand_sea", "06_night_sea", "07_northern_sea"
]

func _visual_capture_dir() -> String:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--nd-capture-dir="):
			return arg.trim_prefix("--nd-capture-dir=")
	return ""

func _capture_real_frame(world: int, phase: String, output_dir: String) -> Dictionary:
	# Wait for the live Control layout, texture uploads and actual renderer.
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	var image := get_viewport().get_texture().get_image()
	if image == null or image.is_empty() or image.get_width() < 300 or image.get_height() < 200:
		push_error("A5 native visual capture: empty/undersized viewport")
		return {}
	# A headless dummy/black frame is NOT visual evidence. This small probe is
	# a guard, not a similarity test or a claim of canonical art parity.
	var unique_colors := {}
	for y in range(1, 8):
		for x in range(1, 12):
			var sample := image.get_pixel(int(x * image.get_width() / 12), int(y * image.get_height() / 8))
			unique_colors[sample.to_html()] = true
	if unique_colors.size() < 12:
		push_error("A5 native visual capture: dummy/flat renderer frame")
		return {}
	var name := "%s_%s.png" % [VISUAL_CAPTURE_SLUGS[world], phase]
	var path := output_dir.path_join(name)
	if image.save_png(path) != OK:
		push_error("A5 native visual capture: PNG write failed: " + path)
		return {}
	return {
		"world": WorldVisuals.WORLDS[world], "world_index": world,
		"live_world": current_world, "live_cell_count": perspective_tiles.size(),
		"physical_support_visible": (get_node("SafeArea/Landscape/Center/BoardAspect/PhysicalSupport") as Control).visible,
		"phase": phase, "file": name, "sha256": FileAccess.get_sha256(path),
		"width": image.get_width(), "height": image.get_height(),
		"sample_colors": unique_colors.size(), "moves": moves
	}

func _run_seven_world_visual_capture() -> void:
	if DisplayServer.get_name() == "headless":
		push_error("A5 visual capture requires a real windowed renderer, not --headless")
		get_tree().quit(2)
		return
	var output_dir := _visual_capture_dir()
	if output_dir.is_empty() or not output_dir.is_absolute_path():
		push_error("A5 visual capture requires --nd-capture-dir=ABSOLUTE_PATH")
		get_tree().quit(2)
		return
	if DirAccess.make_dir_recursive_absolute(output_dir) != OK:
		push_error("A5 visual capture directory is not writable")
		get_tree().quit(2)
		return
	# Deterministic, legal nonterminal board: six real handler-committed moves,
	# no invented reference-screenshot occupancy and no user:// persistence.
	var placements := [[1, 0], [2, 4], [3, 8], [4, 2], [5, 6], [6, 3]]
	var evidence: Array[Dictionary] = []
	ai_enabled = false
	current_rule = "CD"
	for world in range(WorldVisuals.WORLDS.size()):
		match_score = [0, 0]
		match_winner = 0
		round_number = 1
		_reset_round()
		_set_world(world)
		# A filename is not proof that the renderer actually switched worlds.
		# Verify live world-specific art and the physical-support invariant
		# BEFORE the empty/played screenshots are admitted as native evidence.
		var live_support := get_node("SafeArea/Landscape/Center/BoardAspect/PhysicalSupport") as Control
		if current_world != world or perspective_tiles.size() != 9 or live_support.visible != (world != 0) or canonical_live_logo.texture == null:
			push_error("A5 capture: live world identity/support/board mismatch")
			get_tree().quit(3)
			return
		var empty: Dictionary = await _capture_real_frame(world, "empty", output_dir)
		if empty.is_empty():
			get_tree().quit(3)
			return
		evidence.append(empty)
		for placement in placements:
			var rank: int = placement[0]
			var cell: int = placement[1]
			if not _is_legal_move(turn, rank, cell):
				push_error("A5 visual capture fixture illegal before live handler")
				get_tree().quit(3)
				return
			_on_reserve_pressed(turn, rank - 1)
			_on_cell_pressed(cell)
		if moves != 6 or game_over or winner != 0:
			push_error("A5 visual capture fixture failed real gameplay state")
			get_tree().quit(3)
			return
		var played: Dictionary = await _capture_real_frame(world, "played", output_dir)
		if played.is_empty():
			get_tree().quit(3)
			return
		evidence.append(played)
	var report := {
		"status": "NATIVE_CAPTURED_NOT_VISUAL_PARITY_ACCEPTED",
		"capture_count": evidence.size(), "world_count": WorldVisuals.WORLDS.size(),
		"real_gameplay_handlers": true, "rule": "CD", "source": "Godot live scene",
		"captures": evidence
	}
	var report_file := FileAccess.open(output_dir.path_join("capture_manifest.json"), FileAccess.WRITE)
	if report_file == null:
		push_error("A5 visual capture: manifest write failed")
		get_tree().quit(3)
		return
	report_file.store_string(JSON.stringify(report, "  "))
	report_file.flush()
	report_file.close()
	print("BLUE_SEA_NATIVE_SEVEN_WORLD_CAPTURE_PASS 14 frames; NOT visual parity")
	get_tree().quit()

# Pure native geometry smoke: no screenshots, gameplay mutation, or display
# assumptions. Explicitly validates all seven world-specific lower corners and
# their support/plinth overhang against phone and desktop reserve positions.
func _run_headless_board_reserve_clearance_smoke() -> void:
	for viewport_size in [Vector2(746, 280), Vector2(844, 390), Vector2(932, 430), Vector2(1280, 720)]:
		for reserve_fraction in [0.72, 0.78, 0.84]:
			var reserve_top: float = viewport_size.y * reserve_fraction
			for world in range(WorldVisuals.WORLDS.size()):
				var height := _safe_board_height_for_reserve(world, viewport_size, reserve_top)
				var bottom := _perspective_visual_bottom(world, Vector2(viewport_size.x, height))
				assert(bottom <= reserve_top - 5.8, "Live board/support overlaps active reserve")
				assert(height <= viewport_size.y + 0.01, "Board exceeds viewport height")
	print("BLUE_SEA_SEVEN_WORLD_RESERVE_CLEARANCE_PASS 84 profiles")

func _run_headless_reference_aspect_smoke() -> void:
	# The real runtime's backdrop/perimeter must not distort the source art.
	# This is a scene-property assertion, not a visual-parity PASS.
	var backdrop := get_node("WorldBackdrop") as TextureRect
	var scenery := get_node("SceneryPerimeter") as TextureRect
	assert(backdrop.stretch_mode == TextureRect.STRETCH_KEEP_ASPECT_COVERED)
	assert(scenery.stretch_mode == TextureRect.STRETCH_KEEP_ASPECT_COVERED)
	for viewport in [Vector2(1280, 720), Vector2(844, 390), Vector2(746, 280)]:
		var box := _canonical_logo_rect(viewport)
		assert(box.size.x > 0.0 and box.size.y > 0.0)
		assert(absf(box.size.x / box.size.y - 542.0 / 150.0) < 0.0001,
			"Canonical logo stretched at " + str(viewport))
		var canonical_left := 565.0 / 1672.0 * viewport.x
		var canonical_right := 1107.0 / 1672.0 * viewport.x
		assert(box.position.x >= canonical_left - 0.001)
		assert(box.end.x <= canonical_right + 0.001)
	print("BLUE_SEA_CANONICAL_ART_ASPECT_PASS")

# Website RC2.6 parity: exercise actual shared handlers, not a shadow model.
# All seven worlds, C/D/CD, a human-only undo, terminal score rollback and
# AI paired undo are verified without changing user:// or approved art.
func _run_headless_undo_parity_smoke() -> void:
	var original := _match_snapshot()
	var original_ai := ai_enabled
	var original_world := current_world
	var original_history := _undo_history.duplicate(true)
	var checks := 0
	for world in range(WorldVisuals.WORLDS.size()):
		_set_world(world)
		for mode in ["C", "D", "CD"]:
			current_rule = mode
			ai_enabled = false
			round_number = 1
			match_score = [0, 0]
			match_winner = 0
			_reset_round()
			assert(_undo_steps() == 0)
			_on_reserve_pressed(1, 0)
			_on_cell_pressed(0)
			assert(moves == 1 and _undo_steps() == 1)
			_undo_last_move()
			assert(moves == 0 and turn == 1 and board_stacks[0].is_empty())
			assert(reserve_available[0][0] and _undo_steps() == 0)
			checks += 1
		# In CD, 1<3<5 wins; undo must restore the previous score, terminal
		# reserve, win_line, Next visibility and the exact last rank.
		current_rule = "CD"
		_reset_round()
		for placement in [[1, 1, 0], [2, 2, 3], [1, 3, 1], [2, 4, 4], [1, 5, 2]]:
			_on_reserve_pressed(int(placement[0]), int(placement[1]) - 1)
			_on_cell_pressed(int(placement[2]))
		assert(game_over and winner == 1 and match_score[0] == 1)
		assert(next_round_button.visible and _undo_steps() == 1)
		_undo_last_move()
		assert(not game_over and winner == 0 and match_score[0] == 0)
		assert(moves == 4 and turn == 1 and reserve_available[0][4])
		assert(not next_round_button.visible and _match_snapshot_valid(_match_snapshot()))
		checks += 1
		# The AI's reply and the immediately preceding human placement are a
		# single undo unit; an AI-only even-round opening is not undoable.
		_reset_round()
		_on_reserve_pressed(1, 1)
		_on_cell_pressed(4)
		ai_enabled = true
		selected_reserve = 2
		selected_cell = 0
		_on_primary()
		assert(moves == 2 and _undo_steps() == 2)
		_undo_last_move()
		assert(moves == 0 and turn == 1 and _undo_steps() == 0)
		assert(board_stacks[0].is_empty() and board_stacks[4].is_empty())
		assert(_match_snapshot_valid(_match_snapshot()))
		ai_enabled = false
		checks += 1
	# Restore the original fixture state; later native tests must not depend
	# on this one. The test-only undo history is intentionally not persisted.
	_apply_match_snapshot(original)
	_undo_history = original_history
	ai_enabled = original_ai
	_set_world(original_world)
	_refresh_surface()
	print("BLUE_SEA_UNDO_RC26_PARITY_PASS worlds=7 modes=3 checks=", checks)

# Real D2 legality permits a blocked human to yield two consecutive turns
# to the AI. These reachable, non-shadow-rule traces exercise the production
# placement handler in all modes and seven worlds; no Godot runner is claimed
# until this opt-in fixture actually executes.
# Native-only optional Undo continuity test: no production user:// match or
# journal is read/written. Exercises actual move, JSON journal, reload and Undo.
func _run_headless_undo_reload_smoke() -> void:
	var original := _match_snapshot()
	var original_ai := ai_enabled
	var original_world := current_world
	var original_history := _undo_history.duplicate(true)
	var test_path := "user://a5_undo_reload_smoke_v153.json"
	ai_enabled = false
	round_number = 1
	match_score = [0, 0]
	match_winner = 0
	current_rule = "CD"
	_reset_round()
	_on_reserve_pressed(1, 0)
	_on_cell_pressed(0)
	assert(moves == 1 and _undo_steps() == 1)
	# The AI reply and human move are one Undo transaction across reload.
	ai_enabled = true
	selected_reserve = 1
	selected_cell = 4
	_on_primary()
	assert(moves == 2 and _undo_steps() == 2)
	var played := _match_snapshot()
	assert(_write_undo_journal(test_path, played, _undo_history))
	var restored := _read_undo_journal(test_path, played)
	assert(restored.size() == 2 and bool(restored[1]["was_ai"]))
	_undo_history.clear()
	_apply_match_snapshot(played)
	for entry in restored:
		_undo_history.append(entry)
	assert(_undo_steps() == 2)
	_undo_last_move()
	assert(moves == 0 and reserve_available[0][0] and board_stacks[0].is_empty())
	# A different legal match cannot inherit the prior move's Undo journal.
	assert(_read_undo_journal(test_path, _match_snapshot()).is_empty())
	DirAccess.remove_absolute(ProjectSettings.globalize_path(test_path))
	_apply_match_snapshot(original)
	_undo_history = original_history
	ai_enabled = original_ai
	_set_world(original_world)
	_refresh_surface()
	print("BLUE_SEA_UNDO_RELOAD_PASS")

func _run_headless_blocked_human_ai_undo_smoke() -> void:
	var original := _match_snapshot()
	var original_ai := ai_enabled
	var original_world := current_world
	var original_history := _undo_history.duplicate(true)
	var original_queued := _ai_turn_queued
	var paths := {
		"C": [[1,3,1],[2,7,6],[1,1,3],[2,6,8],[1,8,6],[2,9,2],[1,7,5],[2,8,3],[1,6,7],[2,2,0],[1,9,0],[2,5,4],[2,4,1]],
		"D": [[1,7,8],[2,5,7],[1,8,3],[2,8,6],[1,3,0],[2,3,4],[1,2,1],[2,7,0],[1,9,4],[2,6,2],[1,6,5],[2,9,5],[2,4,1]],
		"CD": [[1,4,0],[2,3,6],[1,8,4],[2,8,2],[1,6,6],[2,4,7],[1,7,7],[2,9,3],[1,5,8],[2,7,1],[1,9,5],[2,6,8],[2,5,0]]
	}
	var checks := 0
	for world in range(WorldVisuals.WORLDS.size()):
		_set_world(world)
		for mode in ["C", "D", "CD"]:
			ai_enabled = false
			_ai_turn_queued = false
			current_rule = mode
			round_number = 1
			match_score = [0, 0]
			match_winner = 0
			_reset_round()
			# Prevent an unrelated deferred AI callback; use the real shared
			# move handler for both players, with its real AI history marking.
			ai_enabled = true
			_ai_turn_queued = true
			for placement in paths[mode]:
				assert(not game_over and turn == int(placement[0]))
				selected_reserve = int(placement[1]) - 1
				selected_cell = int(placement[2])
				assert(_is_legal_move(turn, selected_reserve + 1, selected_cell))
				_on_primary()
			assert(moves == 13 and _undo_history.size() == 13)
			assert(bool(_undo_history[-1]["was_ai"]) and bool(_undo_history[-2]["was_ai"]))
			assert(not bool(_undo_history[-3]["was_ai"]) and int(_undo_history[-3]["player"]) == 1)
			assert(_undo_steps() == 3)
			_undo_last_move()
			assert(moves == 10 and turn == 1 and not game_over)
			assert(_undo_history.size() == 10 and _match_snapshot_valid(_match_snapshot()))
			checks += 1
	# AI-only opening stays non-undoable even if two AI entries are present.
	_undo_history = [{"player": 2, "was_ai": true}, {"player": 2, "was_ai": true}]
	assert(_undo_steps() == 0)
	_apply_match_snapshot(original)
	_undo_history = original_history
	ai_enabled = original_ai
	_ai_turn_queued = original_queued
	_set_world(original_world)
	_refresh_surface()
	print("BLUE_SEA_BLOCKED_HUMAN_AI_UNDO_PASS worlds=7 modes=3 checks=21")

# Native smoke uses the LIVE seven-world badge and perspective-label nodes.
# It cannot simulate real Android density changes; it verifies the shared
# current-density path and proves that font refresh does not spend a rank.
func _run_headless_live_rank_dpi_smoke() -> void:
	var before := _match_snapshot()
	var previous_world := current_world
	var expected_font := _live_rank_font_px()
	var expected_outline := _live_rank_outline_px()
	for world in range(WorldVisuals.WORLDS.size()):
		_set_world(world)
		_last_reserve_rank_font_px = -1
		_last_reserve_rank_outline_px = -1
		_sync_live_reserve_rank_typography()
		for player in [1, 2]:
			for piece in _reserve_node(player).get_children():
				var label := (piece as Button).get_node_or_null("RankNumber") as Label
				assert(label != null)
				assert(label.get_theme_font_size("font_size") == expected_font)
				assert(label.get_theme_constant("outline_size") == expected_outline)
				if not label.visible:
					continue  # Hidden/spent reserve labels do not need a visible badge.
				var piece_height := maxf(1.0, maxf((piece as Button).size.y, (piece as Button).custom_minimum_size.y))
				var readable_height := (label.anchor_bottom - label.anchor_top) * piece_height
				assert(readable_height + 0.01 >= minf(piece_height, float(expected_font) * 1.25),
					"Live reserve number too short for font at 746x280")
				assert(label.anchor_top >= -0.0001 and label.anchor_bottom <= 1.0001,
					"Live reserve number escaped its own touch target")
		for label in perspective_ranks:
			assert((label as Label).get_theme_font_size("font_size") == expected_font)
			assert((label as Label).get_theme_constant("outline_size") == expected_outline)
	_set_world(previous_world)
	assert(_match_snapshot() == before, "DPI typography test mutated the match")
	print("BLUE_SEA_LIVE_RANK_DPI_SMOKE_PASS worlds=7 labels=189")

# Opt-in native lifecycle regression. It never fabricates OS notifications:
# those still require real Android foreground/background qualification. This
# tests the SAME live AI commit gate with both independent suspension flags.
func _run_headless_lifecycle_ai_smoke() -> void:
	var previous_ai := ai_enabled
	var previous_turn := turn
	var previous_paused := _app_paused
	var previous_unfocused := _app_unfocused
	var previous_queued := _ai_turn_queued
	var previous_over := game_over
	ai_enabled = true
	turn = 2
	game_over = false
	var before := _match_snapshot()
	_app_paused = true
	_app_unfocused = false
	assert(_interaction_suspended() and _modal_blocks_board_input(), "Paused app exposed board input")
	_ai_turn_queued = true
	_play_ai_turn()
	assert(not _ai_turn_queued and _match_snapshot() == before, "Deferred AI committed while paused")
	_app_paused = false
	_app_unfocused = true
	assert(_interaction_suspended() and _modal_blocks_board_input(), "Unfocused app exposed board input")
	_ai_turn_queued = true
	_play_ai_turn()
	assert(not _ai_turn_queued and _match_snapshot() == before, "Deferred AI committed while unfocused")
	_app_paused = true
	_app_unfocused = true
	_app_paused = false
	assert(_interaction_suspended(), "Resume before focus-in prematurely released AI")
	_app_unfocused = false
	assert(not _interaction_suspended(), "Both cleared gates should restore input")
	ai_enabled = previous_ai
	turn = previous_turn
	game_over = previous_over
	_app_paused = previous_paused
	_app_unfocused = previous_unfocused
	_ai_turn_queued = previous_queued
	print("BLUE_SEA_LIFECYCLE_AI_GATE_SMOKE_PASS pause_focus_independent")

func _run_headless_atlantis_live_seam_smoke() -> void:
	var old_world := current_world
	_set_world(2)
	assert(perspective_atlantis_seam_glows.size() == 8)
	assert(perspective_atlantis_seam_cores.size() == 8)
	assert(perspective_atlantis_junctions.size() == 16)
	var quad := PerspectiveGeometry.board_quad(2, perspective_rect)
	for seam_index in range(8):
		var glow := perspective_atlantis_seam_glows[seam_index]
		var core := perspective_atlantis_seam_cores[seam_index]
		assert(glow.visible and core.visible)
		assert(glow.points.size() == 2 and core.points.size() == 2)
		assert(glow.points[0].distance_to(core.points[0]) < 0.01)
		assert(glow.points[1].distance_to(core.points[1]) < 0.01)
		var t := float(seam_index % 4) / 3.0
		var expected_start := quad[0].lerp(quad[1], t) if seam_index < 4 else quad[0].lerp(quad[3], t)
		var expected_end := quad[3].lerp(quad[2], t) if seam_index < 4 else quad[1].lerp(quad[2], t)
		assert(core.points[0].distance_to(expected_start) < 0.01)
		assert(core.points[1].distance_to(expected_end) < 0.01)
	for junction in perspective_atlantis_junctions:
		assert(junction.visible and junction.polygon.size() == 4)
	# Same physical seams must also render for Gods, with its own palette.
	_set_world(3)
	for seam in perspective_atlantis_seam_cores:
		assert(seam.visible and seam.points.size() == 2)
		assert(seam.default_color == Color(0.62, 0.92, 1.0, 0.95))
	for junction in perspective_atlantis_junctions:
		assert(junction.visible and junction.polygon.size() == 4)
	# Void and the other four worlds must have zero lingering seam geometry.
	_set_world(1)
	for seam in perspective_atlantis_seam_cores:
		assert(not seam.visible and seam.points.size() == 0)
	for junction in perspective_atlantis_junctions:
		assert(not junction.visible and junction.polygon.size() == 0)
	_set_world(old_world)

func _run_headless_void_dome_light_smoke() -> void:
	var old_world := current_world
	var old_board := board_stacks.duplicate(true)
	var pool := Sprite2D.new()
	pool.texture = _night_beacon_pool_texture
	var bloom := Line2D.new()
	var rim := Line2D.new()
	var rect := Rect2(Vector2(40.0, 30.0), Vector2(100.0, 100.0))
	_update_void_dome_light(pool, bloom, rim, 0, rect, 100.0, 1, 1)
	assert(pool.visible and bloom.visible and rim.visible)
	assert(rim.points.size() == 24 and bloom.points.size() == 24)
	var center := rect.position + Vector2(50.0, 74.0)
	var small_radius := rim.points[0].distance_to(center)
	assert(pool.modulate.r > pool.modulate.b, "Void P1 should be amber")
	_update_void_dome_light(pool, bloom, rim, 0, rect, 100.0, 9, 1)
	assert(rim.points[0].distance_to(center) > small_radius, "Void rank 9 light must grow")
	_update_void_dome_light(pool, bloom, rim, 0, rect, 100.0, 9, 2)
	assert(pool.modulate.b > pool.modulate.r, "Void P2 should be blue")
	_update_void_dome_light(pool, bloom, rim, 1, rect, 100.0, 9, 2)
	assert(not pool.visible and not bloom.visible and not rim.visible)
	assert(bloom.points.size() == 0 and rim.points.size() == 0)
	_set_world(0)
	assert(not perspective_support_surface.visible, "Void gained physical table")
	for cell in range(9):
		var occupied := not _top_piece(cell).is_empty()
		assert(perspective_void_dome_pools[cell].visible == occupied)
		assert(perspective_void_dome_rims[cell].visible == occupied)
	_set_world(5)
	for cell in range(9):
		assert(not perspective_void_dome_pools[cell].visible)
		assert(not perspective_void_dome_rims[cell].visible)
		assert(perspective_void_dome_rims[cell].points.size() == 0)
	_set_world(old_world)
	assert(board_stacks == old_board, "Visual smoke mutated live gameplay")

func _run_headless_sand_live_cartouche_smoke() -> void:
	var old_world := current_world
	_set_world(4)
	assert(perspective_sand_inlay_band != null and perspective_sand_inlay_gold != null)
	assert(perspective_sand_inlay_glyphs.size() == 12)
	assert(perspective_sand_inlay_band.visible and perspective_sand_inlay_gold.visible)
	assert(perspective_sand_inlay_band.points.size() == 4)
	assert(perspective_sand_inlay_gold.points.size() == 4)
	var quad := PerspectiveGeometry.board_quad(4, perspective_rect)
	for i in range(4):
		assert(perspective_sand_inlay_gold.points[i].distance_to(quad[i]) < 0.01)
	for glyph in perspective_sand_inlay_glyphs:
		assert(glyph.visible and glyph.polygon.size() == 4)
	# The inlay cannot become an independent floating board in any other world.
	for other_world in [0, 1, 2, 3, 5, 6]:
		_set_world(other_world)
		assert(not perspective_sand_inlay_band.visible and perspective_sand_inlay_band.points.size() == 0)
		assert(not perspective_sand_inlay_gold.visible and perspective_sand_inlay_gold.points.size() == 0)
		for glyph in perspective_sand_inlay_glyphs:
			assert(not glyph.visible and glyph.polygon.size() == 0)
	_set_world(old_world)

# Native fixture: a menu opened mid-gesture must not permit a delayed board
# placement or stale reserve click after it closes, in ANY of seven worlds.
func _run_headless_modal_open_input_transaction_smoke() -> void:
	var original := _match_snapshot()
	var original_ai := ai_enabled
	var original_world := current_world
	var original_round := round_number
	ai_enabled = false
	for world in range(WorldVisuals.WORLDS.size()):
		_set_world(world)
		round_number = 1
		_reset_round()
		_on_reserve_pressed(turn, 8)
		assert(selected_reserve == 8, "Rank9 must be selectable before menu")
		var before_board := board_stacks.duplicate(true)
		var before_reserves := reserve_available.duplicate(true)
		var before_moves := moves
		var before_score := match_score.duplicate()
		var held := InputEventScreenTouch.new()
		held.index = 0
		held.pressed = true
		held.position = PerspectiveGeometry.cell_center(world, 4, perspective_rect)
		_input(held)
		assert(_touch_board_pending, "Board touch must arm before modal")
		_open_mobile_menu()
		assert(mobile_menu_panel.visible and not _touch_board_pending,
			"Opening mobile menu must cancel held board touch")
		_on_mobile_menu_action(-2)
		held.pressed = false
		_input(held)
		assert(board_stacks == before_board and reserve_available == before_reserves
			and moves == before_moves and match_score == before_score and selected_reserve == 8,
			"Closing menu must not commit an old board touch or clear selection")
		# A new real board tap must still be usable immediately after the modal.
		var placing_player := turn
		held.pressed = true
		_input(held)
		held.pressed = false
		_input(held)
		assert(moves == before_moves + 1 and not reserve_available[placing_player - 1][8],
			"Fresh touch after menu must commit exactly one legal rank9 move")
		_reset_round()
		var reserve_down := InputEventScreenTouch.new()
		reserve_down.index = 0
		reserve_down.pressed = true
		reserve_down.position = reserve_scroller.get_global_rect().get_center()
		_track_reserve_touch_gesture(reserve_down)
		assert(_reserve_touch_active, "Reserve gesture must be active")
		_open_mobile_worlds()
		assert(mobile_menu_panel.visible and not _reserve_touch_active,
			"Opening world menu must invalidate old reserve gesture")
		_on_mobile_menu_action(-2)
		reserve_down.pressed = false
		_track_reserve_touch_gesture(reserve_down)
		_on_reserve_gui_pressed(turn, 8)
		assert(selected_reserve == -1 and moves == 0,
			"Late reserve click after modal must be ignored")
		reserve_down.pressed = true
		_track_reserve_touch_gesture(reserve_down)
		reserve_down.pressed = false
		_track_reserve_touch_gesture(reserve_down)
		_on_reserve_gui_pressed(turn, 8)
		assert(selected_reserve == 8 and moves == 0,
			"New reserve tap after modal must work immediately")
		_on_secondary()
	_set_world(original_world)
	_apply_match_snapshot(original)
	ai_enabled = original_ai
	round_number = original_round
	mobile_menu_panel.hide()
	_refresh_surface()
	print("BLUE_SEA_MODAL_OPEN_INPUT_TRANSACTION_PASS worlds=7 board=SAFE reserve=SAFE")

# Native fixture: switch all seven worlds during a held board tap and a
# reserve press. The next world must not inherit an armed move or a stale
# GUI click; no saved gameplay/AI data may be changed by the skin switch.
func _run_headless_world_switch_input_transaction_smoke() -> void:
	var old_world := current_world
	var old_ai := ai_enabled
	var old_round := round_number
	ai_enabled = false
	for world in range(WorldVisuals.WORLDS.size()):
		_set_world(world)
		round_number = 1
		_reset_round()
		_on_reserve_pressed(turn, 8)
		assert(selected_reserve == 8, "Rank9 must be selectable before switching skins")
		var board_before := board_stacks.duplicate(true)
		var reserves_before := reserve_available.duplicate(true)
		var score_before := match_score.duplicate()
		var turn_before := turn
		var moves_before := moves
		var touch := InputEventScreenTouch.new()
		touch.index = 0
		touch.pressed = true
		touch.position = PerspectiveGeometry.cell_center(world, 4, perspective_rect)
		_input(touch)
		assert(_touch_board_pending, "Held board tap must arm before world switch")
		var next_world := (world + 1) % WorldVisuals.WORLDS.size()
		_prepare_world_switch_input(next_world)
		_set_world(next_world)
		assert(not _touch_board_pending and selected_reserve == -1 and selected_cell == -1,
			"World switch must clear pending board and rank selection")
		touch.pressed = false
		_input(touch)
		assert(board_stacks == board_before and reserve_available == reserves_before
			and match_score == score_before and turn == turn_before and moves == moves_before,
			"World switch / late finger-up must not mutate a match")
		# The old reserve press may deliver a delayed GUI Button.pressed.
		var reserve_down := InputEventScreenTouch.new()
		reserve_down.index = 0
		reserve_down.pressed = true
		reserve_down.position = reserve_scroller.get_global_rect().get_center()
		_track_reserve_touch_gesture(reserve_down)
		assert(_reserve_touch_active, "Live reserve must accept primary down")
		_prepare_world_switch_input(world)
		_set_world(world)
		reserve_down.pressed = false
		_track_reserve_touch_gesture(reserve_down)
		_on_reserve_gui_pressed(turn, 8)
		assert(selected_reserve == -1 and moves == moves_before,
			"Old-world reserve click must not select rank in new world")
		# A NEW deliberate press immediately clears the bounded echo guard.
		reserve_down.pressed = true
		_track_reserve_touch_gesture(reserve_down)
		reserve_down.pressed = false
		_track_reserve_touch_gesture(reserve_down)
		_on_reserve_gui_pressed(turn, 8)
		assert(selected_reserve == 8 and moves == moves_before,
			"New-world deliberate rank tap must work without a dead zone")
		_on_secondary()
	round_number = old_round
	_reset_round()
	_set_world(old_world)
	ai_enabled = old_ai
	_refresh_surface()
	print("BLUE_SEA_WORLD_SWITCH_INPUT_TRANSACTION_PASS worlds=7 board=SAFE reserve=SAFE")

func _run_headless_geometry_and_interaction_smoke() -> void:
	assert(ai_engine.self_test(), "Shared AI tactical contract failed")
	_run_headless_modal_open_input_transaction_smoke()
	_run_headless_world_switch_input_transaction_smoke()
	_run_headless_lifecycle_ai_smoke()
	_run_headless_reference_aspect_smoke()
	_run_headless_board_reserve_clearance_smoke()
	_run_headless_ai_fallback_smoke()
	_run_headless_native_mobile_profile_smoke()
	_run_headless_match_snapshot_smoke()
	_run_headless_lazy_reserve_smoke()
	_run_headless_reserve_scroll_resume_smoke()
	_run_headless_scroll_idle_persistence_smoke()
	_run_headless_deferred_scroll_intent_smoke()
	_run_headless_match_hud_smoke()
	_run_headless_match_save_retry_smoke()
	_run_headless_hud_notice_smoke()
	await _assert_landscape_geometry()
	_run_headless_perspective_rank_density_smoke()
	_run_headless_live_rank_dpi_smoke()
	_run_headless_piece_visual_scale_smoke()
	_run_headless_pirate_ranked_art_smoke()
	_run_headless_gods_ranked_art_smoke()
	_run_headless_atlantis_ranked_art_smoke()
	_run_headless_atlantis_live_seam_smoke()
	_run_headless_sand_live_cartouche_smoke()
	_run_headless_void_dome_light_smoke()
	_run_headless_sand_ranked_art_smoke()
	_run_headless_night_ranked_art_smoke()
	_run_headless_void_ranked_art_smoke()
	_run_headless_void_canonical_cells_smoke()
	_run_headless_northern_cell_art_smoke()
	_run_headless_northern_rune_stones_smoke()
	_run_headless_northern_live_lattice_smoke()
	_run_headless_six_supported_world_cells_smoke()
	_run_headless_grounded_board_contact_smoke()
	_run_headless_piece_grounding_smoke()
	_run_headless_selection_feedback_smoke()
	_run_headless_terminal_line_smoke()
	_run_headless_reserve_invalid_guard_smoke()
	_run_headless_unplayable_rank_smoke()
	_run_headless_reserve_touch_toggle_smoke()
	_run_headless_reserve_swipe_click_smoke()
	_run_headless_keyboard_rank_guard_smoke()
	_run_headless_keyboard_navigation_smoke()
	_run_headless_interaction_smoke()
	_run_headless_undo_parity_smoke()
	_run_headless_undo_reload_smoke()
	_run_headless_blocked_human_ai_undo_smoke()
	await _run_headless_input_parity_smoke()
	await _run_headless_orientation_reload_smoke()
	_run_headless_rule_modes_smoke()
	await _run_headless_even_round_ai_smoke()
	_run_headless_preferences_smoke()
	_run_headless_modal_input_smoke()
	_run_headless_ai_modal_guard_smoke()
	_run_headless_primary_modal_commit_guard_smoke()
	_run_headless_touch_emulation_smoke()
	_run_headless_held_preview_grounding_smoke()
	_run_headless_touch_chrome_release_smoke()
	_run_headless_emulated_mouse_identity_smoke()
	_run_headless_touch_state_binding_smoke()
	_run_headless_touch_geometry_resize_smoke()
	_run_headless_modal_touch_transaction_smoke()
	_run_headless_multitouch_order_smoke()
	_run_headless_secondary_drag_mouse_echo_smoke()
	_run_headless_edge_touch_smoke()
	_run_headless_reference_menu_smoke()
	_run_headless_pirate_menu_smoke()
	_run_headless_mobile_settings_smoke()
	_run_headless_mobile_menu_touch_smoke()
	_run_headless_mobile_header_smoke()
	_run_headless_mobile_world_selector_smoke()
	_run_headless_mobile_reset_confirmation_smoke()
	await _run_headless_mobile_back_navigation_smoke()
	_run_headless_tutorial_live_practice_smoke()
	await _run_headless_tutorial_selection_continuity_smoke()
	await _run_headless_ai_modal_resume_smoke()
	print("BLUE_SEA_HEADLESS_SMOKE_SUITE_PASS")
	get_tree().quit(0)

# Explicit whole-match qualification through the PRODUCTION human and AI paths.
# Unlike the old fixture, AI stays enabled: deferred _play_ai_turn() must commit
# its own moves. This detects failures in AI scheduling, reserve visibility and
# real turn transitions which a manual choose_move() call cannot detect.
# It is CI qualification, NOT proof of physical phone-touch behavior.
func _run_headless_full_match_smoke() -> void:
	assert(_headless_run_mode() == "full_match", "Full-match fixture requires explicit CLI opt-in")
	var completed := 0
	var total_moves := 0
	var verified_ai_turns := 0
	for world in range(WorldVisuals.WORLDS.size()):
		for mode in ["C", "D", "CD"]:
			ai_enabled = true
			ai_difficulty = 3
			ai_persona = 0
			current_rule = mode
			_set_world(world)
			match_score = [0, 0]
			match_winner = 0
			round_number = 1
			_reset_round()
			assert(perspective_tiles.size() == 9)
			assert(perspective_support_surface.visible == (world != 0))
			assert(world_visuals.piece_texture(world, 1, 9) != null)
			assert(world_visuals.piece_texture(world, 2, 9) != null)
			# The two submerged worlds share live electric seams throughout
			# real matches; five other worlds must never show stale geometry.
			assert(perspective_atlantis_seam_cores.size() == 8)
			assert(perspective_atlantis_junctions.size() == 16)
			for seam in perspective_atlantis_seam_cores:
				assert(seam.visible == (world == 2 or world == 3), "Undersea seam leaked or disappeared")
				assert(seam.points.size() == (2 if world == 2 or world == 3 else 0))
			for junction in perspective_atlantis_junctions:
				assert(junction.visible == (world == 2 or world == 3), "Undersea junction leaked or disappeared")
			# Void's floating glass light is driven by actual occupied ranks;
			# no halo may leak into the six physically supported worlds.
			for halo_cell in range(9):
				var halo_expected := world == 0 and not _top_piece(halo_cell).is_empty()
				assert(perspective_void_dome_pools[halo_cell].visible == halo_expected)
				assert(perspective_void_dome_rims[halo_cell].visible == halo_expected)
				assert(perspective_void_dome_blooms[halo_cell].visible == halo_expected)
				assert(perspective_void_dome_rims[halo_cell].points.size() == (24 if halo_expected else 0))
			# Sand's cartouche must remain a live 4-sided inlay throughout
			# every rules mode, with zero leakage to the other six worlds.
			assert(perspective_sand_inlay_band.visible == (world == 4))
			assert(perspective_sand_inlay_gold.visible == (world == 4))
			assert(perspective_sand_inlay_band.points.size() == (4 if world == 4 else 0))
			for glyph in perspective_sand_inlay_glyphs:
				assert(glyph.visible == (world == 4))
				assert(glyph.polygon.size() == (4 if world == 4 else 0))
			var rounds_completed := 0
			while match_winner == 0 and rounds_completed < 12:
				var switched_this_round := false
				while not game_over and moves < 18:
					var moving_player := turn
					var before_moves := moves
					if moving_player == 1:
						var options: Array[Dictionary] = ai_engine.legal_moves(board_stacks, reserve_available, 1, mode)
						assert(not options.is_empty(), "Human turn has no legal move")
						var move: Dictionary = options[(round_number * 17 + moves * 7) % options.size()]
						_on_reserve_pressed(1, int(move["rank"]) - 1)
						_on_cell_pressed(int(move["cell"]))
						assert(moves == before_moves + 1, "Human input did not commit exactly once")
					else:
						# The AI must move from the queued production call_deferred,
						# never from manually setting selection and calling _on_primary.
						assert(ai_enabled and not _reserve_node(2).visible, "AI reserve leaked to player")
						var expected: Dictionary = ai_engine.choose_move(board_stacks, reserve_available, 2, mode, ai_difficulty, ai_persona)
						assert(not expected.is_empty(), "AI turn has no legal move")
						var expected_cell := int(expected["cell"])
						var expected_rank := int(expected["rank"])
						for frame in range(3):
							await get_tree().process_frame
							if moves > before_moves:
								break
						assert(moves > before_moves, "Deferred production AI did not move within three frames")
						assert(not reserve_available[1][expected_rank - 1], "AI failed to consume chosen rank")
						assert(board_stacks[expected_cell].has({"player": 2, "rank": expected_rank}), "AI did not commit chosen cell")
						verified_ai_turns += 1
					assert(selected_cell == -1 and selected_reserve == -1, "Selection leaked across turns")
					# The Night Sea light follows actual state: no rings on empty
					# cells, and no beacons leaking into any other world.
					for light_cell in range(9):
						var occupied := not _top_piece(light_cell).is_empty()
						var light_expected := world == 5 and occupied
						assert(perspective_night_beacon_rims[light_cell].visible == light_expected,
							"Night beacon ring not bound to live occupancy")
						assert(perspective_night_beacon_blooms[light_cell].visible == light_expected,
							"Night beacon bloom not bound to live occupancy")
						assert(perspective_night_beacon_pools[light_cell].visible == light_expected,
							"Night diffuse pool not bound to live occupancy")
						if light_expected:
							assert(perspective_night_beacon_pools[light_cell].texture == _night_beacon_pool_texture)
							assert(perspective_night_beacon_rims[light_cell].points.size() == 16)
						var void_expected := world == 0 and occupied
						assert(perspective_void_dome_pools[light_cell].visible == void_expected,
							"Void floating halo not bound to live occupancy")
						assert(perspective_void_dome_rims[light_cell].visible == void_expected,
							"Void ring not bound to live occupancy")
						if void_expected:
							assert(perspective_void_dome_rims[light_cell].points.size() == 24)
						var rune_expected := world == 6 and occupied
						assert(perspective_northern_rune_reflections[light_cell].visible == rune_expected,
							"Northern reflection not bound to live rank and occupancy")
						if rune_expected:
							assert(perspective_northern_rune_reflections[light_cell].texture == _night_beacon_pool_texture)
					if not switched_this_round and moves >= 2:
						var old_board := board_stacks.duplicate(true)
						var old_score := match_score.duplicate()
						var old_turn := turn
						_set_world((world + 1) % WorldVisuals.WORLDS.size())
						_set_world(world)
						assert(board_stacks == old_board and match_score == old_score and turn == old_turn)
						switched_this_round = true
				assert(game_over, "Round did not terminate within eighteen moves")
				# Actual AI/human full-match results must illuminate exactly their
				# three winning cells, never stale legal-target affordances.
				for cell in range(9):
					assert(perspective_legal_outlines[cell].visible == (winner != 0 and win_line.has(cell)),
						"Full-match terminal line does not reflect the live board")
				assert(next_round_button.visible, "Terminal round must expose Next")
				assert(not _reserve_node(1).visible and not _reserve_node(2).visible)
				assert(moves <= 18, "Consumed more than eighteen distinct ranks")
				total_moves += moves
				rounds_completed += 1
				if match_winner == 0:
					_on_menu()
			assert(match_winner == 2 and match_score[1] == MATCH_TARGET,
					"Hard AI failed to finish deterministic full match: world=%d rule=%s" % [world, mode])
			completed += 1
			print("BLUE_SEA_FULL_MATCH_CASE_PASS world=", world, " rule=", mode,
				" rounds=", rounds_completed, " score=", match_score)
	assert(verified_ai_turns > 0, "No production AI turns were exercised")
	print("BLUE_SEA_FULL_MATCH_SUITE_PASS matches=", completed,
		" worlds=7 modes=C,D,CD total_moves=", total_moves,
		" production_ai_turns=", verified_ai_turns)
	get_tree().quit(0)

func _run_headless_hud_notice_smoke() -> void:
	# Real UI state is bound to the current player, never the hidden AI reserve.
	assert(_hud_selected_rank_line("ХОД P1", 8, 1, true, false, false) == "P1 · №9")
	assert(_hud_selected_rank_line("ХОД P2", 0, 2, true, false, false) == "P2 · №1")
	assert(_hud_selected_rank_line("ХОД P1", -1, 1, true, false, false) == "ХОД P1")
	assert(_hud_selected_rank_line("ХОД ИИ", 8, 2, true, false, true) == "ХОД ИИ")
	assert(_hud_selected_rank_line("РАУНД P1", 8, 1, true, true, false) == "РАУНД P1")
	assert(_hud_selected_rank_line("ХОД P1", 8, 1, false, false, false) == "ХОД P1")
	assert(_hud_secondary_line(_hud_selected_rank_line("ХОД P1", 8, 1, true, false, false), "НЕЛЬЗЯ", 200, 100, true, false) == "НЕЛЬЗЯ")
	assert(_hud_secondary_line(_hud_selected_rank_line("ХОД P1", 8, 1, true, false, false), "НЕЛЬЗЯ", 200, 200, true, false) == "P1 · №9")
	assert(_hud_notice_for_event("illegal move") == "НЕЛЬЗЯ")
	assert(_hud_notice_for_event("piece already played") == "ЗАНЯТО")
	assert(_hud_notice_for_event("для ранга 1 нет допустимой клетки") == "НЕТ ХОДА")
	assert(_hud_notice_for_event("для ранга 9 нет допустимой клетки") == "НЕТ ХОДА")
	assert(_hud_notice_for_event("reserve 0") == "РАНГ 1")
	assert(_hud_notice_for_event("reserve 8") == "РАНГ 9")
	assert(_hud_notice_for_event("keyboard cell 8") == "КЛЕТКА 9")
	assert(_hud_notice_for_event("ready") == "")
	assert(_hud_secondary_line("ХОД P1", "НЕЛЬЗЯ", 200, 100, true, false) == "НЕЛЬЗЯ")
	assert(_hud_secondary_line("ХОД P1", "НЕЛЬЗЯ", 200, 200, true, false) == "ХОД P1")
	assert(_hud_secondary_line("ХОД P1", "НЕЛЬЗЯ", 200, 100, false, false) == "ХОД P1")
	assert(_hud_secondary_line("РАУНД P1", "НЕЛЬЗЯ", 200, 100, true, true) == "РАУНД P1")
	print("BLUE_SEA_MOBILE_VISIBLE_FEEDBACK_PASS 1based_rank=PASS terminal=PASS expiry=PASS")

func _run_headless_match_hud_smoke() -> void:
	var saved_board := board_stacks.duplicate(true)
	var saved_reserves := reserve_available.duplicate(true)
	var saved_score := match_score.duplicate()
	var saved_turn := turn
	var saved_moves := moves
	var saved_round := round_number
	var saved_winner := winner
	var saved_match_winner := match_winner
	var saved_over := game_over
	var saved_draw := round_draw
	var saved_ai := ai_enabled
	var saved_line := win_line.duplicate()
	var saved_blocked := blocked_player
	ai_enabled = true
	turn = 2
	match_score = [1, 0]
	game_over = false
	winner = 0
	match_winner = 0
	round_draw = false
	_refresh_surface()
	assert(match_hud_label.text == "1:0\nХОД ИИ", "Phone must show live score and AI turn")
	assert(not next_round_button.visible, "No Next during play")
	game_over = true
	winner = 2
	match_score = [1, 1]
	_refresh_surface()
	assert(match_hud_label.text == "1:1\nРАУНД P2")
	assert(next_round_button.visible and next_round_button.text.contains("P2 ПОБЕДИЛ"))
	winner = 0
	round_draw = true
	_refresh_surface()
	assert(match_hud_label.text == "1:1\nНИЧЬЯ")
	assert(next_round_button.text.contains("НИЧЬЯ"))
	round_draw = false
	winner = 2
	match_winner = 2
	match_score = [1, 3]
	_refresh_surface()
	assert(match_hud_label.text == "1:3\nМАТЧ P2")
	assert(next_round_button.text.contains("P2 ВЫИГРАЛ МАТЧ"))
	board_stacks = saved_board
	reserve_available = saved_reserves
	match_score = saved_score
	turn = saved_turn
	moves = saved_moves
	round_number = saved_round
	winner = saved_winner
	match_winner = saved_match_winner
	game_over = saved_over
	round_draw = saved_draw
	ai_enabled = saved_ai
	win_line = saved_line
	blocked_player = saved_blocked
	_refresh_surface()
	print("BLUE_SEA_LIVE_MATCH_HUD_PASS live_ai round_win draw match_win restored")

func _run_headless_match_save_retry_smoke() -> void:
	assert(_match_save_retry_delay(0) == 1.0)
	assert(_match_save_retry_delay(1) == 2.0)
	assert(_match_save_retry_delay(2) == 4.0)
	assert(_match_save_retry_delay(10) == 8.0)
	var old_dirty := _match_save_dirty
	var old_attempts := _match_save_retry_attempts
	var old_over := game_over
	var old_winner := winner
	var old_match_winner := match_winner
	var old_draw := round_draw
	_match_save_dirty = true
	_match_save_retry_attempts = MATCH_SAVE_RETRY_MAX
	game_over = false
	_refresh_match_hud()
	assert(match_hud_label.text.contains("НЕ СОХР."), "Failed save must be visible on live HUD")
	game_over = true
	winner = 0
	match_winner = 0
	round_draw = true
	_refresh_match_hud()
	assert(match_hud_label.text.contains("НИЧЬЯ") and match_hud_label.text.contains("!"),
		"Storage warning must not hide the terminal outcome")
	# The recovery action is discoverable only while storage is unsaved,
	# on BOTH the real phone menu and desktop popup. It is never offered
	# during a healthy match and never silently commits a board move.
	var old_menu_page := _mobile_menu_page
	_render_mobile_menu_page("main")
	assert(mobile_menu_list.get_node_or_null("MobileChoice_107") != null,
		"Phone lost the manual recovery action after automatic retries")
	_populate_game_menu()
	assert(top_menu.get_popup().get_item_index(107) >= 0,
		"Desktop lost the manual recovery action")
	_match_save_dirty = false
	_render_mobile_menu_page("main")
	assert(mobile_menu_list.get_node_or_null("MobileChoice_107") == null,
		"Healthy phone match still exposes retry action")
	_populate_game_menu()
	assert(top_menu.get_popup().get_item_index(107) < 0,
		"Healthy desktop match still exposes retry action")
	_render_mobile_menu_page(old_menu_page)
	_match_save_dirty = old_dirty
	_match_save_retry_attempts = old_attempts
	game_over = old_over
	winner = old_winner
	match_winner = old_match_winner
	round_draw = old_draw
	_refresh_match_hud()
	print("BLUE_SEA_SAVE_RETRY_HUD_PASS backoff=PASS terminal=PASS bounded=PASS manual_action=PASS")

func _run_headless_perspective_rank_density_smoke() -> void:
	# This is an engine-side label/layout assertion, not a real-phone test.
	var old_world := current_world
	var old_board := board_stacks.duplicate(true)
	board_stacks[4] = [{"player": 1, "rank": 9}]
	var expected_font := maxi(16, ceili(14.0 * _native_touch_density() / _physical_pixel_scale()))
	for world in range(WorldVisuals.WORLDS.size()):
		_set_world(world)
		var number := perspective_ranks[4]
		assert(number.visible and number.text == "9", "World lost live rank numeral")
		assert(number.get_theme_font_size("font_size") == expected_font, "Board rank not native-density legible")
		var quad := PerspectiveGeometry.cell_quad(world, 4, perspective_rect)
		var y_min := minf(minf(quad[0].y, quad[1].y), minf(quad[2].y, quad[3].y))
		var y_max := maxf(maxf(quad[0].y, quad[1].y), maxf(quad[2].y, quad[3].y))
		assert(number.position.y >= y_min - 0.1 and number.position.y + number.size.y <= y_max + 0.1,
			"Rank numeral escaped its own perspective cell")
	board_stacks = old_board
	_set_world(old_world)
	print("BLUE_SEA_PERSPECTIVE_RANK_DENSITY_PASS worlds=7")

func _run_headless_piece_visual_scale_smoke() -> void:
	# Regression: 44px physical touch targets must scale their 44px source
	# sprites as well. KEEP_ASPECT_CENTERED silently preserves the tiny
	# intrinsic bitmap and leaves rank-9 only ~17 physical px at 746x280.
	var scale := _physical_pixel_scale()
	for player in [1, 2]:
		for piece in _reserve_node(player).get_children():
			var button := piece as Button
			var art := button.get_node_or_null("RankArt") as TextureRect
			assert(art != null and art.stretch_mode == TextureRect.STRETCH_KEEP_ASPECT,
				"Reserve art must scale to physical touch target")
			assert(art.size.x * scale >= 43.5 and art.size.y * scale >= 43.5,
				"Reserve sprite rect smaller than physical touch target")
	for icon in perspective_icons:
		assert(icon.stretch_mode == TextureRect.STRETCH_KEEP_ASPECT,
			"Live perspective piece must scale with its projected tile rect")
	print("BLUE_SEA_PIECE_VISUAL_SCALE_PASS reserve_art_px>=44 projected_icons=9")

func _run_headless_pirate_ranked_art_smoke() -> void:
	# Runtime asset binding: all eighteen caps load through the SAME game
	# renderer and reserve. Alpha silhouettes strictly increase with rank.
	var saved_world := current_world
	_set_world(1)
	for player in [1, 2]:
		var last_width := 0
		for rank in range(1, 10):
			var texture := world_visuals.piece_texture(1, player, rank)
			assert(texture != null, "Missing Pirate ranked texture")
			var image := texture.get_image()
			assert(image != null and image.get_width() == 128 and image.get_height() == 128)
			var used := image.get_used_rect()
			assert(used.size.x > last_width, "Pirate piece rank sizes must strictly grow")
			last_width = used.size.x
			var reserve_button := _reserve_node(player).get_child(rank - 1) as Button
			var rank_label := reserve_button.get_node("RankNumber") as Label
			assert(absf(rank_label.anchor_bottom - 0.48) < 0.001, "Pirate rank must sit on top badge")
			assert(rank_label.text == str(rank), "Pirate rank must remain a live number")
	_set_world(saved_world)
	print("BLUE_SEA_PIRATE_RANKED_CANONICAL_PASS textures=18 ranks=1..9 live_badges=18")

func _run_headless_gods_ranked_art_smoke() -> void:
	# The accepted Gods world uses nine distinct creatures rather than a
	# single procedurally repeated token. Verify live board/reserve binding.
	var saved_world := current_world
	_set_world(3)
	for player in [1, 2]:
		var last_width := 0
		for rank in range(1, 10):
			var texture := world_visuals.piece_texture(3, player, rank)
			assert(texture != null, "Missing Gods ranked sea-creature texture")
			var image := texture.get_image()
			assert(image != null and image.get_width() == 128 and image.get_height() == 128)
			var used := image.get_used_rect()
			assert(used.size.x > last_width, "Gods ranked creature widths must strictly grow")
			last_width = used.size.x
			var reserve_button := _reserve_node(player).get_child(rank - 1) as Button
			var rank_label := reserve_button.get_node("RankNumber") as Label
			assert(absf(rank_label.anchor_top - 0.59) < 0.001, "Gods rank must sit on lower badge")
			assert(rank_label.text == str(rank), "Gods rank must remain a live number")
	_set_world(saved_world)
	print("BLUE_SEA_GODS_DISTINCT_CANONICAL_PASS textures=18 ranks=1..9 live_badges=18")

func _run_headless_atlantis_ranked_art_smoke() -> void:
	# Exact approved Atlantis source sprites in both materials, live ranks
	# and shared reserve/board renderer. This is engine smoke, not touch PASS.
	var saved_world := current_world
	_set_world(2)
	for player in [1, 2]:
		var last_width := 0
		for rank in range(1, 10):
			var texture := world_visuals.piece_texture(2, player, rank)
			assert(texture != null, "Missing Atlantis stepped shrine")
			var image := texture.get_image()
			assert(image != null and image.get_width() == 128 and image.get_height() == 128)
			var used := image.get_used_rect()
			assert(used.size.x > last_width, "Atlantis shrine ranks must strictly grow")
			last_width = used.size.x
			var reserve_button := _reserve_node(player).get_child(rank - 1) as Button
			var rank_label := reserve_button.get_node("RankNumber") as Label
			var band := _atlantis_rank_band(rank)
			assert(absf(rank_label.anchor_top - band.x) < 0.001)
			assert(absf(rank_label.anchor_bottom - band.y) < 0.001)
			assert(rank_label.text == str(rank), "Atlantis rank must be live")
	_set_world(saved_world)
	print("BLUE_SEA_ATLANTIS_SOURCE_SHRINES_PASS textures=18 ranks=1..9")

func _run_headless_sand_ranked_art_smoke() -> void:
	# Godot-only qualification to run when a real engine route is restored.
	# This is not a simulated PASS or a substitute for real phone input.
	var saved_world := current_world
	_set_world(4)
	for player in [1, 2]:
		var last_width := 0
		for rank in range(1, 10):
			var texture := world_visuals.piece_texture(4, player, rank)
			assert(texture != null, "Missing Sand ranked pyramid")
			var image := texture.get_image()
			assert(image != null and image.get_width() == 128 and image.get_height() == 128)
			var used := image.get_used_rect()
			assert(used.size.x > last_width, "Sand pyramid rank sizes must strictly grow")
			last_width = used.size.x
			var reserve_button := _reserve_node(player).get_child(rank - 1) as Button
			var rank_label := reserve_button.get_node("RankNumber") as Label
			var band := _sand_rank_band(rank)
			assert(absf(rank_label.anchor_top - band.x) < 0.001)
			assert(absf(rank_label.anchor_bottom - band.y) < 0.001)
			assert(rank_label.text == str(rank), "Sand rank must be a live number")
	_set_world(saved_world)
	print("BLUE_SEA_SAND_CANONICAL_PYRAMIDS_PASS textures=18 ranks=1..9")

func _run_headless_night_ranked_art_smoke() -> void:
	# Runtime binding for both live reserve and perspective board textures.
	var saved_world := current_world
	_set_world(5)
	for player in [1, 2]:
		var last_width := 0
		for rank in range(1, 10):
			var texture := world_visuals.piece_texture(5, player, rank)
			assert(texture != null, "Missing Night Gothic beacon")
			var image := texture.get_image()
			assert(image != null and image.get_width() == 128 and image.get_height() == 128)
			var used := image.get_used_rect()
			assert(used.size.x > last_width, "Night beacon ranks must strictly grow")
			last_width = used.size.x
			var reserve_button := _reserve_node(player).get_child(rank - 1) as Button
			var rank_label := reserve_button.get_node("RankNumber") as Label
			var band := _night_rank_band(rank)
			assert(absf(rank_label.anchor_top - band.x) < 0.001)
			assert(absf(rank_label.anchor_bottom - band.y) < 0.001)
			assert(rank_label.text == str(rank), "Night rank must be a live number")
	_set_world(saved_world)
	print("BLUE_SEA_NIGHT_SOURCE_GOTHIC_BEACONS_PASS textures=18 ranks=1..9")

func _run_headless_void_ranked_art_smoke() -> void:
	# Both canonical glass materials are real rank-scaled sprites, not a
	# screenshot overlay. The central game state and reserve stay interactive.
	var saved_world := current_world
	_set_world(0)
	for player in [1, 2]:
		var last_width := 0
		for rank in range(1, 10):
			var texture := world_visuals.piece_texture(0, player, rank)
			assert(texture != null, "Missing ND Void source glass dome")
			var image := texture.get_image()
			assert(image != null and image.get_width() == 128 and image.get_height() == 128)
			var used := image.get_used_rect()
			assert(used.size.x > last_width, "Void glass dome ranks must strictly grow")
			last_width = used.size.x
			var reserve_button := _reserve_node(player).get_child(rank - 1) as Button
			var rank_label := reserve_button.get_node("RankNumber") as Label
			assert(rank_label.text == str(rank), "Void rank must be live, not baked")
	assert(not perspective_support_surface.visible, "Void is the ONLY floating world")
	_set_world(saved_world)
	print("BLUE_SEA_VOID_SOURCE_GLASS_DOMES_PASS textures=18 ranks=1..9")

func _run_headless_void_canonical_cells_smoke() -> void:
	# Source-derived EMPTY luminous board cells now belong to Void too.
	# Test the real live Polygon2D layer, not an offline board screenshot.
	var saved_world := current_world
	var saved_stacks := board_stacks.duplicate(true)
	var saved_reserves := reserve_available.duplicate(true)
	var saved_turn := turn
	var saved_moves := moves
	_set_world(0)
	assert(not perspective_support_surface.visible and perspective_support_surface.texture == null,
		"Void must float without inheriting any physical support")
	for i in range(9):
		var source := get_node("SafeArea/Landscape/Center/BoardAspect/Board/" + CELL_NAMES[i]) as Button
		var art := source.get_node("WorldCellArt") as TextureRect
		assert(art.visible and art.texture != null, "Void source-derived empty cell missing")
		assert(art.texture.get_size() == Vector2(192, 192), "Void canonical tile size changed")
		assert(perspective_tiles[i].texture == art.texture,
			"Void live perspective tile must show its source-derived texture")
	assert(board_stacks == saved_stacks and reserve_available == saved_reserves,
		"Void art must not change actual board occupancy")
	assert(turn == saved_turn and moves == saved_moves,
		"Void art must not change match state")
	_set_world(saved_world)
	print("BLUE_SEA_VOID_EMPTY_CANONICAL_CELLS_PASS 9 live tiles state=preserved")

func _run_headless_northern_cell_art_smoke() -> void:
	# Nine actual empty rune-circle textures, taken only from two unoccupied
	# cells in the immutable accepted Northern screenshot. Occupancy remains live.
	var saved_world := current_world
	_set_world(6)
	for i in range(9):
		var source := get_node("SafeArea/Landscape/Center/BoardAspect/Board/" + CELL_NAMES[i]) as Button
		var art := source.get_node("WorldCellArt") as TextureRect
		assert(art.visible and art.texture != null, "Northern canonical cell art missing")
		assert(art.texture.get_size() == Vector2(192, 192), "Northern tile size changed")
		assert(perspective_tiles[i].texture == art.texture, "Northern live perspective tile not bound")
	assert(perspective_tiles.size() == 9 and perspective_support_surface.visible,
		"Northern board must remain physically supported")
	_set_world(saved_world)
	print("BLUE_SEA_NORTHERN_EMPTY_CANONICAL_CELLS_PASS 9 live tiles")

func _run_headless_northern_rune_stones_smoke() -> void:
	# The runes must be actual live textures on BOTH reserves and the board,
	# not an inert screenshot. A world switch cannot alter the D2 match.
	var previous_world := current_world
	var previous_board := board_stacks.duplicate(true)
	var previous_reserves := reserve_available.duplicate(true)
	var previous_turn := turn
	_set_world(6)
	var signatures: Dictionary = {}
	for player in [1, 2]:
		for value in range(1, 10):
			var tex := world_visuals.piece_texture(6, player, value)
			assert(tex != null and tex.get_size() == Vector2(128, 128), "Northern runic piece missing")
			assert(not signatures.has(tex.resource_path), "Northern rune ranks must be distinct")
			signatures[tex.resource_path] = true
	assert(signatures.size() == 18, "Expected 18 distinct Northern rune textures")
	# One occupied live cell must use the same ranked texture as the reserve.
	var saved_cell := board_stacks[0].duplicate(true)
	board_stacks[0] = [{"player": 1, "rank": 9}]
	_refresh_surface()
	assert(perspective_icons[0].texture == world_visuals.piece_texture(6, 1, 9))
	assert(perspective_ranks[0].text == "9", "Rune cannot replace live numeric rank")
	board_stacks[0] = saved_cell
	_set_world(previous_world)
	assert(board_stacks == previous_board and reserve_available == previous_reserves and turn == previous_turn,
		"Northern art switch changed live match state")
	print("BLUE_SEA_NORTHERN_RUNE_ENGRAVING_PASS 18 live ranked textures")

func _run_headless_northern_live_lattice_smoke() -> void:
	# Native-only: all 8 live lines/16 knots align with actual cell geometry.
	# Switch to each other world and verify complete teardown, then restore
	# the unchanged match. This is not physical-touch or visual-parity evidence.
	var previous_world := current_world
	var previous_board := board_stacks.duplicate(true)
	var previous_reserves := reserve_available.duplicate(true)
	var previous_turn := turn
	var previous_moves := moves
	_set_world(6)
	assert(perspective_northern_grid_glows.size() == 8)
	assert(perspective_northern_grid_cores.size() == 8)
	assert(perspective_northern_grid_junctions.size() == 16)
	var quad := PerspectiveGeometry.board_quad(6, perspective_rect)
	for index in range(8):
		var glow := perspective_northern_grid_glows[index]
		var core := perspective_northern_grid_cores[index]
		assert(glow.visible and core.visible and core.points.size() == 2)
		var t := float(index % 4) / 3.0
		var expected_start := quad[0].lerp(quad[1], t) if index < 4 else quad[0].lerp(quad[3], t)
		var expected_end := quad[3].lerp(quad[2], t) if index < 4 else quad[1].lerp(quad[2], t)
		assert(core.points[0].distance_to(expected_start) < 0.01)
		assert(core.points[1].distance_to(expected_end) < 0.01)
		assert(glow.default_color == Color(1.0, 0.52, 0.12, 0.34))
	for star in perspective_northern_grid_junctions:
		assert(star.visible and star.polygon.size() == 4)
	for other_world in [0, 1, 2, 3, 4, 5]:
		_set_world(other_world)
		for line in perspective_northern_grid_glows:
			assert(not line.visible and line.points.size() == 0)
		for line in perspective_northern_grid_cores:
			assert(not line.visible and line.points.size() == 0)
		for star in perspective_northern_grid_junctions:
			assert(not star.visible and star.polygon.size() == 0)
	_set_world(previous_world)
	assert(board_stacks == previous_board and reserve_available == previous_reserves)
	assert(turn == previous_turn and moves == previous_moves)
	print("BLUE_SEA_NORTHERN_LIVE_LATTICE_PASS 8 seams 16 junctions")

func _run_headless_six_supported_world_cells_smoke() -> void:
	# v41: Pirate/Atlantis/Gods now use source-derived EMPTY board tiles,
	# matching already-qualified Sand/Night/North. All share one live board.
	var saved_world := current_world
	var saved_stacks := board_stacks.duplicate(true)
	var saved_reserves := reserve_available.duplicate(true)
	var saved_turn := turn
	var saved_moves := moves
	for world in range(1, 7):
		_set_world(world)
		assert(perspective_support_surface.visible and perspective_support_shadow.visible,
			"Every non-Void board needs a physical supporting surface")
		var foundation := get_node("SafeArea/Landscape/Center/BoardAspect/PhysicalSupport/NorthernStonePlinth") as TextureRect
		assert(foundation.visible and foundation.texture != null,
			"Every supported world must supply a material, including Sand")
		assert(perspective_support_surface.texture == foundation.texture,
			"Live perspective support must show the same world-specific material")
		assert(perspective_support_surface.uv.size() == 4,
			"Perspective support material requires four correctly mapped UV corners")
		for i in range(9):
			var source := get_node("SafeArea/Landscape/Center/BoardAspect/Board/" + CELL_NAMES[i]) as Button
			var art := source.get_node("WorldCellArt") as TextureRect
			assert(art.visible and art.texture != null, "Missing supported-world canonical tile")
			assert(art.texture.get_size() == Vector2(192, 192), "Incorrect approved-source cell atlas size")
			assert(perspective_tiles[i].texture == art.texture,
				"Perspective gameplay tile must use the same live empty source art")
		assert(board_stacks == saved_stacks and reserve_available == saved_reserves,
			"Changing supported-world artwork must not change game state")
		assert(turn == saved_turn and moves == saved_moves,
			"World art change must not alter turn or move count")
	_set_world(0)
	assert(not perspective_support_surface.visible and perspective_support_surface.texture == null,
		"Void alone floats, without inherited tabletop texture")
	_set_world(saved_world)
	print("BLUE_SEA_SIX_SUPPORTED_CANONICAL_EMPTY_CELLS_PASS worlds=6 tiles=54 state=preserved")

# Verify the actual production layer and all seven world transitions, not a
# disconnected render mockup. This is headless engine smoke, not real-phone QA.
func _run_headless_grounded_board_contact_smoke() -> void:
	var saved_world := current_world
	for world in range(WorldVisuals.WORLDS.size()):
		_set_world(world)
		var grounded := world != 0
		assert(perspective_board_front_fascia.visible == grounded)
		assert(perspective_board_right_fascia.visible == grounded)
		assert(perspective_support_surface.visible == grounded)
		if grounded:
			var base := PerspectiveGeometry.board_quad(world, perspective_rect)
			var front := perspective_board_front_fascia.polygon
			var right := perspective_board_right_fascia.polygon
			assert(front.size() == 4 and right.size() == 4)
			assert(front[0].distance_to(base[3]) < 0.01)
			assert(front[1].distance_to(base[2]) < 0.01)
			assert(right[0].distance_to(base[1]) < 0.01)
			assert(right[1].distance_to(base[2]) < 0.01)
			assert(front[2].y > front[1].y and right[2].y > right[1].y)
			assert(perspective_support_surface.texture != null)
		else:
			assert(perspective_board_front_fascia.polygon.is_empty())
			assert(perspective_board_right_fascia.polygon.is_empty())
	_set_world(saved_world)
	print("BLUE_SEA_SIX_GROUNDED_BOARD_CONTACT_PASS")

# Source-derived baseline alignment is applied to LIVE occupancy across all
# seven worlds. This engine smoke is registered, but not passed until Godot runs.
func _run_headless_piece_grounding_smoke() -> void:
	var saved_world := current_world
	var saved_board := board_stacks.duplicate(true)
	var saved_reserves := reserve_available.duplicate(true)
	var saved_moves := moves
	var saved_turn := turn
	var saved_game_over := game_over
	var saved_winner := winner
	game_over = false
	winner = 0
	turn = 2
	for world in range(WorldVisuals.WORLDS.size()):
		for rank in [1, 5, 9]:
			board_stacks = [[],[],[],[],[],[],[],[],[]]
			board_stacks[4] = [{"player": 1, "rank": rank}]
			reserve_available = [[true,true,true,true,true,true,true,true,true], [true,true,true,true,true,true,true,true,true]]
			reserve_available[0][rank - 1] = false
			moves = 1
			_set_world(world)
			var contact := perspective_piece_contacts[4]
			assert(contact.visible and contact.polygon.size() == 16)
			var quad := PerspectiveGeometry.cell_quad(world, 4, perspective_rect)
			var cell_center := PerspectiveGeometry.cell_center(world, 4, perspective_rect)
			var cell_width := (quad[1] - quad[0]).length()
			var cell_height := (quad[3] - quad[0]).length()
			var extent := minf(ceilf(_minimum_touch_physical_px() / _physical_pixel_scale()), minf(cell_width * 0.56, cell_height * 0.88))
			var expected_top := cell_center.y - extent * 0.5 + PieceGrounding.baseline_shift(world, rank, extent)
			assert(absf(perspective_icons[4].position.y - expected_top) < 0.1)
			assert(perspective_ranks[4].text == str(rank))
			if world == 6 and rank == 1:
				assert(PieceGrounding.baseline_shift(world, rank, extent) > 10.0)
			if world == 0:
				assert(PieceGrounding.baseline_shift(world, rank, extent) == 0.0)
		board_stacks = [[],[],[],[],[],[],[],[],[]]
		_refresh_surface()
		assert(not perspective_piece_contacts[4].visible and perspective_piece_contacts[4].polygon.is_empty())
	board_stacks = saved_board
	reserve_available = saved_reserves
	moves = saved_moves
	turn = saved_turn
	game_over = saved_game_over
	winner = saved_winner
	_set_world(saved_world)
	assert(board_stacks == saved_board and reserve_available == saved_reserves)
	print("BLUE_SEA_PIECE_BASELINE_CONTACT_PASS worlds=7 ranks=1,5,9")

func _run_headless_selection_feedback_smoke() -> void:
	var saved_ai := ai_enabled
	var saved_world := current_world
	ai_enabled = false
	_set_world(6)
	_reset_round()
	assert(perspective_legal_outlines.size() == 9, "Nine independent live board affordances required")
	_on_reserve_pressed(1, 2)
	assert((_reserve_node(1).get_child(2) as Button).get_node("SelectionRing").visible,
		"Selected reserve must have a visible touch-safe outline")
	for i in range(9):
		assert(perspective_legal_outlines[i].visible, "Every empty board cell must show legal target")
	board_stacks[0] = [{"player": 1, "rank": 1}]
	board_stacks[1] = [{"player": 2, "rank": 3}]
	_refresh_selection_feedback()
	assert(not perspective_legal_outlines[0].visible and not perspective_legal_outlines[1].visible,
		"Own-piece and stronger enemy cover must not be suggested as legal")
	assert(perspective_legal_outlines[2].visible, "Empty legal target must remain highlighted")
	board_stacks[0] = []
	board_stacks[1] = []
	_on_cell_pressed(4)
	assert(moves == 1 and selected_reserve == -1, "Touch move must commit and clear selection")
	for outline in perspective_legal_outlines:
		assert(not outline.visible, "Legal highlights must disappear after move")
	_reset_round()
	_on_cell_pressed(5)
	assert(perspective_legal_outlines[5].visible, "Cell-first tap needs visible feedback")
	_on_secondary()
	for outline in perspective_legal_outlines:
		assert(not outline.visible, "Cancel must clear every affordance")
	_reset_round()
	_set_world(saved_world)
	ai_enabled = saved_ai
	_refresh_surface()
	print("BLUE_SEA_TOUCH_SELECTION_FEEDBACK_PASS worlds=7 outlines=9 legal=filtered")

func _run_headless_terminal_line_smoke() -> void:
	# No alternate game engine: exercise the shared live perspective renderer
	# with actual rank/ownership/round state across all seven worlds.
	var old_world := current_world
	var old_ai := ai_enabled
	ai_enabled = false
	_reset_round()
	for world in range(WorldVisuals.WORLDS.size()):
		_set_world(world)
		board_stacks = [[],[],[],[],[],[],[],[],[]]
		board_stacks[3] = [{"player": 1, "rank": 3}]
		board_stacks[4] = [{"player": 1, "rank": 4}]
		board_stacks[5] = [{"player": 1, "rank": 5}]
		winner = 1
		win_line = _winning_line(1)
		game_over = true
		_refresh_surface()
		assert(win_line == [3,4,5], "Terminal fixture must be a real D/CD rank ladder")
		for cell in range(9):
			var outline := perspective_legal_outlines[cell]
			assert(outline.visible == win_line.has(cell), "Terminal highlights must match winning cells exactly")
			if outline.visible:
				assert(outline.default_color == Color("#ffda73") and outline.width >= 3.5)
		# Switching art after a win must not change or erase the result.
		_set_world((world + 1) % WorldVisuals.WORLDS.size())
		assert(win_line == [3,4,5] and game_over and winner == 1)
		for cell in range(9):
			assert(perspective_legal_outlines[cell].visible == win_line.has(cell))
		_set_world(world)
		# A draw has no phantom victory affordance.
		winner = 0
		win_line = []
		round_draw = true
		_refresh_surface()
		for outline in perspective_legal_outlines:
			assert(not outline.visible, "Draw cannot display a winning line")
		_reset_round()
		for outline in perspective_legal_outlines:
			assert(not outline.visible, "New round must clear terminal outlines")
	_set_world(old_world)
	ai_enabled = old_ai
	_refresh_surface()
	print("BLUE_SEA_TERMINAL_LINE_SEVEN_WORLDS_PASS winners=7 draws=7 resets=7")

# Exercise the REAL shared GUI reserve handler, not a Python-only surrogate.
# This catches stale selections after consumed, opponent and malformed taps.
func _run_headless_reserve_invalid_guard_smoke() -> void:
	var saved_ai := ai_enabled
	var saved_round := round_number
	ai_enabled = false
	round_number = 1
	_reset_round()
	_on_reserve_pressed(1, 4)
	assert(selected_reserve == 4, "Valid reserve tap must select rank 5")
	reserve_available[0][0] = false
	_on_reserve_pressed(1, 0)
	assert(selected_reserve == -1 and selected_cell == -1, "Consumed touch rank left a stale selection")
	assert(moves == 0 and board_stacks[0].is_empty(), "Rejected touch changed gameplay")
	reserve_available[0][0] = true
	_on_reserve_pressed(1, 2)
	_on_reserve_pressed(2, 1)
	assert(selected_reserve == -1 and selected_cell == -1, "Opponent tap left a stale selection")
	_on_reserve_pressed(1, 3)
	_on_reserve_pressed(1, 9)
	assert(selected_reserve == -1 and selected_cell == -1, "Out-of-range rank left a stale selection")
	_on_reserve_pressed(0, 0)
	assert(selected_reserve == -1 and moves == 0, "Invalid player modified game state")
	round_number = saved_round
	_reset_round()
	ai_enabled = saved_ai
	_refresh_surface()
	print("BLUE_SEA_RESERVE_INVALID_GUARD_PASS touch=used,opponent,out_of_range no_ghost_move")

# Native regression: an unspent rank can be temporarily unusable while
# another unspent rank remains legal. Exercise the real reserve handler and
# actual UI controls, not an independent rules model. No durable save occurs.
func _run_headless_unplayable_rank_smoke() -> void:
	var saved_world := current_world
	var saved_ai := ai_enabled
	var saved_round := round_number
	ai_enabled = false
	# The same live rank UI is used in every world, but each world's texture
	# can alter readability. Inspect real art and number nodes for all seven.
	for world in range(WorldVisuals.WORLDS.size()):
		_set_world(world)
		round_number = 1
		_reset_round()
		# A filled, non-winning board: rank 1 cannot cover any top piece;
		# rank 9 can cover the opponent's rank-2..6 pieces. Both are unspent.
		var owners := [2, 1, 2, 2, 1, 1, 1, 2, 2]
		var ranks := [2, 2, 3, 4, 3, 4, 5, 5, 6]
		for cell in range(9):
			board_stacks[cell] = [{"player": owners[cell], "rank": ranks[cell]}]
		turn = 1
		assert(not _rank_has_legal_cell(1, 1), "Rank 1 must be unavailable on filled board")
		assert(_rank_has_legal_cell(1, 9), "Rank 9 must be able to cover P2")
		_refresh_surface()
		var low := _reserve_node(1).get_child(0) as Button
		var high := _reserve_node(1).get_child(8) as Button
		assert(low.size == high.size or low.custom_minimum_size == high.custom_minimum_size,
			"Unplayable rank changed touch target geometry")
		var low_art := low.get_node("RankArt") as TextureRect
		var high_art := high.get_node("RankArt") as TextureRect
		var low_number := low.get_node("RankNumber") as Label
		assert(low_art.modulate.a < high_art.modulate.a, "Unplayable rank silhouette must be dimmed")
		assert(is_equal_approx(low.modulate.a, 1.0) and is_equal_approx(low_number.modulate.a, 1.0),
			"Unplayable rank number must retain full contrast")
		assert(low_number.text == "1" and low_number.visible, "Unplayable rank number disappeared")
		assert(not low.disabled and not high.disabled, "Available ranks must remain tappable")
		_on_reserve_pressed(1, 0)
		assert(selected_reserve == -1 and moves == 0, "Unplayable rank armed a move")
		_on_reserve_pressed(1, 8)
		assert(selected_reserve == 8, "Playable rank 9 must still select")
	# Restore the same fresh match; no simulated move or stale selection leaks.
	_set_world(saved_world)
	round_number = saved_round
	_reset_round()
	ai_enabled = saved_ai
	_refresh_surface()
	print("BLUE_SEA_UNPLAYABLE_RANK_SMOKE_PASS worlds=7 dim_art=7 readable_number=7 touch=equal")

# Real shared UI fixture, not a separate game simulation. Must be run by
# Godot 4.7.2 to qualify; Python source checks alone cannot prove touch input.
func _run_headless_reserve_touch_toggle_smoke() -> void:
	var saved_ai := ai_enabled
	var saved_world := current_world
	var saved_round := round_number
	ai_enabled = false
	for world in range(WorldVisuals.WORLDS.size()):
		_set_world(world)
		for player in [1, 2]:
			round_number = 1
			_reset_round()
			turn = player
			_refresh_surface()
			for index in [0, 8]:
				_on_reserve_pressed(player, index)
				assert(selected_reserve == index and selected_cell == -1,
					"First live reserve tap must select its exact rank")
				assert((_reserve_node(player).get_child(index) as Button).get_node("SelectionRing").visible,
					"Selected reserve needs a visible ring")
				_on_reserve_pressed(player, index)
				assert(selected_reserve == -1 and selected_cell == -1 and moves == 0,
					"Second live reserve tap must cancel without a move")
				assert(reserve_available[player - 1][index] and board_stacks[4].is_empty(),
					"Cancel must not spend a rank or occupy a cell")
				for outline in perspective_legal_outlines:
					assert(not outline.visible, "Cancel must clear every legal target")
	round_number = saved_round
	_reset_round()
	_set_world(saved_world)
	ai_enabled = saved_ai
	_refresh_surface()
	print("BLUE_SEA_RESERVE_TOUCH_TOGGLE_PASS worlds=7 players=2 ranks=1,9 no_move=PASS")

# Real shared GUI adapter fixture. A swipe across the live reserve must not
# select or spend rank 9, but the NEXT deliberate tap must work immediately.
# All seven worlds are exercised against their actual live reserve nodes.
func _run_headless_reserve_swipe_click_smoke() -> void:
	var saved_world := current_world
	var saved_round := round_number
	var saved_ai := ai_enabled
	ai_enabled = false
	for world in range(WorldVisuals.WORLDS.size()):
		_set_world(world)
		round_number = 1
		_reset_round()
		var center := reserve_scroller.get_global_rect().get_center()
		var down := InputEventScreenTouch.new()
		down.index = 0
		down.pressed = true
		down.position = center
		_track_reserve_touch_gesture(down)
		assert(_reserve_touch_active, "Reserve gesture must start inside live scroller")
		var swipe := InputEventScreenDrag.new()
		swipe.index = 0
		swipe.position = center + Vector2(48.0, 0.0)
		_track_reserve_touch_gesture(swipe)
		assert(_reserve_touch_swiped, "Horizontal reserve swipe must invalidate GUI click")
		var up := InputEventScreenTouch.new()
		up.index = 0
		up.pressed = false
		up.position = swipe.position
		_track_reserve_touch_gesture(up)
		_on_reserve_gui_pressed(1, 8)
		assert(selected_reserve == -1 and moves == 0 and reserve_available[0][8],
			"Swipe echo must not select or spend the largest rank")
		# A NEW primary press clears the echo guard; no 350ms dead zone.
		_track_reserve_touch_gesture(down)
		up.position = center
		_track_reserve_touch_gesture(up)
		_on_reserve_gui_pressed(1, 8)
		assert(selected_reserve == 8 and moves == 0,
			"Fresh rank9 tap must work immediately after a swipe")
		_on_secondary()
		# A second finger while the reserve is held is never a rank tap.
		_track_reserve_touch_gesture(down)
		var second := InputEventScreenTouch.new()
		second.index = 1
		second.pressed = true
		second.position = center
		_track_reserve_touch_gesture(second)
		_track_reserve_touch_gesture(up)
		_on_reserve_gui_pressed(1, 0)
		assert(selected_reserve == -1 and moves == 0,
			"Multitouch reserve echo must not select a rank")
		_reserve_touch_block_until_msec = 0
		# A real mouse drag must not select rank 9 on delayed GUI release.
		var mouse_down := InputEventMouseButton.new()
		mouse_down.button_index = MOUSE_BUTTON_LEFT
		mouse_down.pressed = true
		mouse_down.position = center
		_track_reserve_touch_gesture(mouse_down)
		var mouse_drag := InputEventMouseMotion.new()
		mouse_drag.button_mask = MOUSE_BUTTON_MASK_LEFT
		mouse_drag.position = center + Vector2(45.0, 0.0)
		_track_reserve_touch_gesture(mouse_drag)
		assert(_reserve_pointer_dragged, "Reserve mouse drag must invalidate GUI click")
		var mouse_up := InputEventMouseButton.new()
		mouse_up.button_index = MOUSE_BUTTON_LEFT
		mouse_up.pressed = false
		mouse_up.position = mouse_drag.position
		_track_reserve_touch_gesture(mouse_up)
		_on_reserve_gui_pressed(1, 8)
		assert(selected_reserve == -1 and moves == 0,
			"Mouse drag echo must not select a reserve rank")
		# A new intentional pointer press clears the prior drag guard.
		_track_reserve_touch_gesture(mouse_down)
		mouse_up.position = center
		_track_reserve_touch_gesture(mouse_up)
		_on_reserve_gui_pressed(1, 8)
		assert(selected_reserve == 8 and moves == 0,
			"Fresh pointer click must work immediately after drag")
		_on_secondary()
		# Pan delivered during an active touch is a swipe even when the
		# backend omits ScreenDrag. A free pan without contact is not.
		_track_reserve_touch_gesture(down)
		var pan := InputEventPanGesture.new()
		pan.position = center
		pan.delta = Vector2(40.0, 0.0)
		_track_reserve_touch_gesture(pan)
		assert(_reserve_touch_swiped, "Reserve pan must cancel pending GUI tap")
		_track_reserve_touch_gesture(up)
		_on_reserve_gui_pressed(1, 8)
		assert(selected_reserve == -1 and moves == 0,
			"Pan gesture echo must not select a reserve rank")
		_reserve_touch_block_until_msec = 0
		_reserve_touch_swiped = false
		_reserve_pointer_block_until_msec = 0
		_reserve_pointer_dragged = false
	round_number = saved_round
	_reset_round()
	_set_world(saved_world)
	ai_enabled = saved_ai
	_refresh_surface()
	print("BLUE_SEA_RESERVE_SWIPE_CLICK_SAFETY_PASS worlds=7 swipe=blocked next_tap=allowed multitouch=blocked")

# Actual in-project qualification fixture (requires Godot 4.7.2 execution).
# Keyboard selection and commit must use the same board/reserve and rules.
func _run_headless_keyboard_rank_guard_smoke() -> void:
	var saved_ai := ai_enabled
	var saved_round := round_number
	var saved_rule := current_rule
	ai_enabled = false
	round_number = 1
	_reset_round()
	_select_keyboard_rank(1)
	assert(selected_reserve == 1, "Valid keyboard rank must select its own piece")
	reserve_available[0][0] = false
	_select_keyboard_rank(0)
	assert(selected_reserve == -1 and selected_cell == -1,
		"Used keyboard rank must clear stale selection to prevent accidental move")
	reserve_available[0][0] = true
	_select_keyboard_rank(8)
	assert(selected_reserve == 8, "Last rank must remain keyboard-selectable")
	# Deferred visibility correction is guarded against subsequent turn changes.
	_on_secondary()
	_reveal_keyboard_rank(1, 8, current_world, round_number, moves,
		_reserve_scroll_user_epoch)
	assert(selected_reserve == -1, "Stale reveal must not reselect a piece")
	# All seven world skins share this scroll path. A fresh keyboard request
	# must be invalidated by a later human reserve touch even if the same
	# rank remains selected and the game board never changes.
	var saved_world := current_world
	for world in range(WorldVisuals.WORLDS.size()):
		_set_world(world)
		_select_keyboard_rank(8)
		assert(selected_reserve == 8 and reserve_scroller.visible)
		var epoch_at_request := _reserve_scroll_user_epoch
		assert(_reserve_scroll_request_current(1, world, round_number, moves,
			8, epoch_at_request), "Fresh keyboard reveal context must be valid")
		var new_swipe := InputEventScreenTouch.new()
		new_swipe.pressed = true
		new_swipe.position = reserve_scroller.get_global_rect().get_center()
		_track_reserve_scroll_intent(new_swipe)
		assert(not _reserve_scroll_request_current(1, world, round_number, moves,
			8, epoch_at_request), "New touch must invalidate keyboard reveal")
		_reveal_keyboard_rank(1, 8, world, round_number, moves, epoch_at_request)
		assert(selected_reserve == 8, "Stale keyboard reveal changed selection")
		_on_secondary()
	_set_world(saved_world)
	current_rule = saved_rule
	round_number = saved_round
	_reset_round()
	ai_enabled = saved_ai
	_refresh_surface()
	print("BLUE_SEA_KEYBOARD_RANK_GUARD_PASS stale_selection rank9 deferred_reveal")

func _run_headless_keyboard_navigation_smoke() -> void:
	var saved_ai := ai_enabled
	var saved_rule := current_rule
	var saved_round := round_number
	var saved_world := current_world
	ai_enabled = false
	round_number = 1
	for world in range(WorldVisuals.WORLDS.size()):
		_set_world(world)
		for mode in ["C", "D", "CD"]:
			current_rule = mode
			_reset_round()
			_select_keyboard_rank(0)
			assert(selected_reserve == 0 and selected_cell == -1, "Keyboard rank selection failed")
			_move_keyboard_cell(0, -1)
			assert(selected_cell == 4, "Keyboard cursor must start in the center")
			_move_keyboard_cell(-1, 0)
			assert(selected_cell == 3, "Keyboard left must select row 1 col 0")
			_move_keyboard_cell(0, -1)
			assert(selected_cell == 0, "Keyboard up must select row 0 col 0")
			_move_keyboard_cell(-1, 0)
			assert(selected_cell == 0, "Keyboard cursor must clamp at edge")
			assert(perspective_legal_outlines[0].visible and perspective_legal_outlines[0].default_color == Color("#6be7e6"), "Keyboard focus must be visible")
			_on_primary()
			assert(moves == 1 and int(board_stacks[0][-1].rank) == 1, "Keyboard move must commit through production gameplay")
			assert(not reserve_available[0][0] and turn == 2, "Keyboard move must consume reserve and advance turn")
			ai_enabled = true
			_select_keyboard_rank(0)
			assert(selected_reserve == -1, "AI reserve must not be selected by human keyboard")
			ai_enabled = false
			_reset_round()
			assert(moves == 0 and selected_reserve == -1 and selected_cell == -1)
	current_rule = saved_rule
	round_number = saved_round
	_set_world(saved_world)
	_reset_round()
	ai_enabled = saved_ai
	_refresh_surface()
	print("BLUE_SEA_KEYBOARD_PARITY_PASS worlds=7 modes=C,D,CD shared_moves=21")

# Actual shared production scene fixture: a high-rank held piece covering a
# low-rank one must preview at the EXACT final grounded position in each world.
# Synthetic Godot input, not a physical-phone touch or visual-parity PASS.
func _run_headless_held_preview_grounding_smoke() -> void:
	var saved_world := current_world
	var saved_rule := current_rule
	var saved_ai := ai_enabled
	var saved_round := round_number
	ai_enabled = false
	current_rule = "CD"
	round_number = 1
	for world in range(WorldVisuals.WORLDS.size()):
		_set_world(world)
		_reset_round()
		_on_reserve_pressed(1, 0)
		_on_cell_pressed(4)
		assert(turn == 2 and int(_top_piece(4).rank) == 1,
			"Rank-1 setup must leave P2 ready to cover center")
		_on_reserve_pressed(2, 8)
		_refresh_perspective_layer()
		var old_rect := perspective_icons[4].position
		var point := PerspectiveGeometry.cell_center(world, 4, perspective_rect)
		var touch := InputEventScreenTouch.new()
		touch.index = 0
		touch.position = point
		touch.pressed = true
		_input(touch)
		assert(_touch_board_pending and perspective_touch_preview_icon.visible and
			perspective_touch_preview_contact.visible,
			"Legal covering touch must show held rank-9 sprite and contact")
		var preview_contact_polygon := perspective_touch_preview_contact.polygon.duplicate()
		var preview_contact_color := perspective_touch_preview_contact.color
		var preview_position := perspective_touch_preview_icon.position
		var preview_size := perspective_touch_preview_icon.size
		var preview_label_position := perspective_touch_preview_rank.position
		var preview_label_size := perspective_touch_preview_rank.size
		assert(preview_position.is_equal_approx(_perspective_piece_rect(world, 4, 9, preview_size.x).position),
			"Preview must use the selected rank's baseline, not the covered rank")
		if world == 6:
			assert(absf(preview_position.y - old_rect.y) > 0.1,
				"Northern rank-9 preview must not inherit rank-1 rune baseline")
			assert(perspective_touch_preview_northern_reflection.visible,
				"Held Nordic rune must reflect light on frozen support")
		else:
			assert(not perspective_touch_preview_northern_reflection.visible,
				"Nordic light must not leak into other worlds")
		touch.pressed = false
		_input(touch)
		assert(moves == 2 and int(_top_piece(4).rank) == 9,
			"Released rank-9 touch must commit legal cover")
		assert(perspective_icons[4].position.is_equal_approx(preview_position) and
			perspective_icons[4].size.is_equal_approx(preview_size),
			"Committed piece must exactly replace the preview, without a vertical jump")
		assert(perspective_ranks[4].position.is_equal_approx(preview_label_position) and
			perspective_ranks[4].size.is_equal_approx(preview_label_size),
			"Committed numeral must exactly replace preview numeral")
		assert(perspective_piece_contacts[4].polygon == preview_contact_polygon and
			perspective_piece_contacts[4].color == preview_contact_color,
			"Committed physical contact/void halo must exactly replace held preview")
		assert(not perspective_touch_preview_icon.visible and
			not perspective_touch_preview_contact.visible and
			not perspective_touch_preview_northern_reflection.visible,
			"Preview sprite, contact and rune reflection must disappear on release")
		if world == 6:
			assert(perspective_northern_rune_reflections[4].visible,
				"Committed Nordic rank must inherit live reflection")
	current_rule = saved_rule
	round_number = saved_round
	_set_world(saved_world)
	_reset_round()
	ai_enabled = saved_ai
	_refresh_surface()
	print("BLUE_SEA_HELD_PREVIEW_GROUNDING_PASS worlds=7 cover=rank1_to_rank9 rect_and_label_exact")

# Engine-level boundary test for all seven worlds. This is not a physical
# phone test; it verifies that release/drag over live UI cannot spend a rank,
# and that a nearby touch outside UI is not globally disabled.
func _run_headless_touch_chrome_release_smoke() -> void:
	var topbar := get_node("SafeArea/Landscape/Center/TopBar") as Control
	var dock := get_node("SafeArea/Landscape/Center/ReserveDock") as Control
	var top_rect := topbar.get_global_rect()
	var dock_rect := dock.get_global_rect()
	assert(_touch_over_chrome_rects(top_rect.get_center(), top_rect, dock_rect))
	assert(_touch_over_chrome_rects(dock_rect.get_center(), top_rect, dock_rect))
	var above_dock := Vector2(dock_rect.get_center().x, dock_rect.position.y - 0.25)
	assert(not _touch_over_chrome_rects(above_dock, top_rect, dock_rect),
		"Board side of reserve boundary must remain tappable")
	var old_world := current_world
	var old_ai := ai_enabled
	ai_enabled = false
	for world in range(WorldVisuals.WORLDS.size()):
		# At 3x native DPI, a 44dp target occupies 132 physical pixels.
		# At 746x280 the expanded bottom-center cell reaches across the
		# visible 6px board/reserve clearance: the old release path would
		# commit rank 9 even though finger-up is INSIDE the reserve.
		var simulated_size := Vector2(746.0, 280.0)
		var simulated_dock_top := 218.0
		var simulated_height := _safe_board_height_for_reserve(world, simulated_size, simulated_dock_top)
		var simulated_board := Rect2(Vector2.ZERO, Vector2(simulated_size.x, simulated_height))
		var simulated_down := Vector2(373.0, 216.0)
		var simulated_up := Vector2(373.0, 219.0)
		assert(PerspectiveGeometry.cell_at_touch(world, simulated_down, simulated_board, 132.0) == 7 and
			PerspectiveGeometry.cell_at_touch(world, simulated_up, simulated_board, 132.0) == 7,
			"Expanded high-DPI board target must reproduce the near-reserve overlap")
		assert(_touch_over_chrome_rects(simulated_up, Rect2(Vector2.ZERO, Vector2(746.0, 44.0)),
			Rect2(Vector2(0.0, simulated_dock_top), Vector2(746.0, 62.0))),
			"Release inside active reserve must take priority over expanded board hit")
		_set_world(world)
		_reset_round()
		_on_reserve_pressed(1, 8)
		var center := PerspectiveGeometry.cell_center(world, 7, perspective_rect)
		var touch := InputEventScreenTouch.new()
		touch.index = 0
		touch.position = center
		touch.pressed = true
		_input(touch)
		assert(_touch_board_pending, "Center-cell touch must arm before crossing UI")
		# A real finger may cross from the board into reserve. A release over
		# the reserve cannot commit, even if target expansion includes it.
		touch.position = dock.get_global_rect().get_center()
		assert(_touch_over_live_chrome(touch.position), "Live reserve release zone missing")
		touch.pressed = false
		_input(touch)
		assert(moves == 0 and turn == 1 and selected_reserve == 8 and
			reserve_available[0][8] and not _touch_board_pending,
			"Release on reserve must never spend a selected rank")
		# The drag route must also cancel the translucent held preview.
		touch.position = center
		touch.pressed = true
		_input(touch)
		assert(_touch_board_pending)
		var drag := InputEventScreenDrag.new()
		drag.index = 0
		drag.position = dock.get_global_rect().get_center()
		_input(drag)
		assert(not _touch_board_pending and not perspective_touch_preview_icon.visible,
			"Drag into reserve must cancel preview")
		touch.position = center
		touch.pressed = false
		_input(touch)
		assert(moves == 0 and selected_reserve == 8,
			"Canceled gesture must never rearm after returning to board")
	_set_world(old_world)
	_reset_round()
	ai_enabled = old_ai
	_refresh_surface()
	print("BLUE_SEA_TOUCH_CHROME_RELEASE_PASS worlds=7 reserve_release_drag_no_move")

# Engine-level geometry assertion (runs only under explicit --nd-run-smoke).
# The previous center-only fallback missed off-center touches immediately
# outside narrow top-row cells in all seven playable worlds.
func _run_headless_edge_touch_smoke() -> void:
	var phone_rect := Rect2(Vector2.ZERO, Vector2(746.0, 210.0))
	for world in range(WorldVisuals.WORLDS.size()):
		var quad := PerspectiveGeometry.cell_quad(world, 0, phone_rect)
		var top_edge := quad[1] - quad[0]
		var outward := Vector2(top_edge.y, -top_edge.x).normalized()
		var off_center := quad[0].lerp(quad[1], 0.18) + outward * 0.75
		assert(PerspectiveGeometry.cell_at(world, off_center, phone_rect) == -1,
			"Edge smoke must test a genuinely OUTSIDE touch")
		assert(PerspectiveGeometry.cell_at_touch(world, off_center, phone_rect, 44.0) == 0,
			"Off-center top-border touch missed live perspective cell")
		assert(PerspectiveGeometry.cell_at_touch(world, off_center, phone_rect, 0.0) == -1,
			"Mouse/exact route must not use touch expansion")
		assert(PerspectiveGeometry.cell_at_touch(world, Vector2(0.0, 0.0), phone_rect, 44.0) == -1,
			"Edge expansion must not invent distant board hits")
	print("BLUE_SEA_EDGE_TOUCH_PASS worlds=7 off_center=7 exact_pointer_unchanged")

func _run_headless_touch_emulation_smoke() -> void:
	# One primary tap commits only on release. Mouse echo, drag, and secondary
	# finger never spend a rank. This is synthetic engine input, NOT phone QA.
	var saved_ai := ai_enabled
	var saved_round := round_number
	_last_board_press_frame = -100
	_last_board_press_kind = "none"
	_touch_mouse_echo_deadline_msec = 0
	_touch_board_pending = false
	_touch_primary_active = false
	_touch_board_started = false
	ai_enabled = false
	round_number = 1
	_reset_round()
	_on_reserve_pressed(1, 0)
	_refresh_perspective_layer()
	var point := PerspectiveGeometry.cell_center(current_world, 4, perspective_rect)
	var touch := InputEventScreenTouch.new()
	touch.index = 0
	touch.position = point
	touch.pressed = true
	_input(touch)
	assert(moves == 0 and _touch_board_pending and selected_reserve == 0,
		"Touch-down must not spend the selected rank")
	assert(perspective_touch_preview_icon.visible and perspective_touch_preview_rank.visible,
		"Held legal touch must preview the selected rank without spending it")
	assert(perspective_touch_preview_rank.text == "1" and
		perspective_touch_preview_icon.texture == world_visuals.piece_texture(current_world, 1, 1),
		"Held preview must use the actual active rank and world sprite")
	var emulated_mouse := InputEventMouseButton.new()
	emulated_mouse.button_index = MOUSE_BUTTON_LEFT
	emulated_mouse.position = point
	emulated_mouse.pressed = true
	_input(emulated_mouse)
	assert(moves == 0, "Synthetic mouse-down must not bypass release gate")
	touch.pressed = false
	_input(touch)
	assert(moves == 1 and turn == 2 and selected_cell == -1,
		"Release over same cell must commit exactly one move")
	assert(not perspective_touch_preview_icon.visible and not perspective_touch_preview_rank.visible,
		"Released touch must remove the preview before rendering committed occupancy")
	_input(emulated_mouse)
	assert(moves == 1 and selected_cell == -1,
		"Post-release mouse echo must not ghost-select P2 cell")
	# A deliberate mouse click in a different cell remains available.
	emulated_mouse.position = PerspectiveGeometry.cell_center(current_world, 5, perspective_rect)
	_input(emulated_mouse)
	assert(selected_cell == 5 and moves == 1,
		"Independent different-cell mouse click must remain valid")
	_on_secondary()
	# A swipe across the board must NOT place a rank.
	_reset_round()
	_on_reserve_pressed(1, 0)
	touch.position = point
	touch.pressed = true
	_input(touch)
	touch.position = PerspectiveGeometry.cell_center(current_world, 5, perspective_rect)
	touch.pressed = false
	_input(touch)
	assert(moves == 0 and selected_reserve == 0,
		"Board swipe must not spend a rank")
	# Even an echo at the original press position cannot commit a canceled swipe.
	emulated_mouse.position = point
	_input(emulated_mouse)
	assert(moves == 0, "Canceled swipe mouse echo must not place a piece")
	# A returning swipe must not commit just because the final finger-up
	# position equals the original cell center. The full trajectory matters.
	_reset_round()
	_on_reserve_pressed(1, 0)
	touch.position = point
	touch.pressed = true
	_input(touch)
	var drag := InputEventScreenDrag.new()
	drag.index = 0
	drag.position = PerspectiveGeometry.cell_center(current_world, 5, perspective_rect)
	_input(drag)
	drag.position = point
	_input(drag)
	touch.pressed = false
	_input(touch)
	assert(moves == 0 and not _touch_board_pending,
		"Return swipe must not commit after traversing another cell")
	assert(not perspective_touch_preview_icon.visible,
		"Canceled returning swipe must not leave a ghost piece")
	# A second finger cancels an armed first-finger tap.
	touch.position = point
	touch.pressed = true
	_input(touch)
	var second_finger := InputEventScreenTouch.new()
	second_finger.index = 1
	second_finger.position = point
	second_finger.pressed = true
	_input(second_finger)
	touch.pressed = false
	_input(touch)
	assert(moves == 0 and not _touch_board_pending,
		"Secondary finger must cancel the primary board tap")
	# Simulate a long press whose initial 350ms echo deadline expired.
	# Release must rearm it even when a secondary finger canceled the tap.
	_touch_mouse_echo_deadline_msec = 0
	_input(emulated_mouse)
	assert(moves == 0, "Multitouch release mouse echo must not spend a rank")
	# A touch beginning on the reserve/topbar and ending on the board
	# cannot become a board move through an emulated mouse press.
	var ui_point := (get_node("SafeArea/Landscape/Center/ReserveDock") as Control).get_global_rect().get_center()
	touch.position = ui_point
	touch.pressed = true
	_input(touch)
	assert(not _touch_board_started and not _touch_board_pending)
	touch.position = point
	touch.pressed = false
	_input(touch)
	emulated_mouse.position = point
	_input(emulated_mouse)
	assert(moves == 0, "UI-to-board synthetic mouse must not place a piece")
	# Same-kind mouse clicks are still independent (no blanket mouse lock).
	_touch_mouse_echo_deadline_msec = 0
	_touch_primary_active = false
	_touch_board_started = false
	_last_board_press_frame = -100
	_last_board_press_kind = "none"
	_on_reserve_pressed(1, 0) # Toggle selected rank off.
	_on_reserve_pressed(1, 0)
	emulated_mouse.position = point
	_input(emulated_mouse)
	assert(moves == 1 and selected_cell == -1 and turn == 2,
		"Mouse click must still commit selected P1 rank")
	_input(emulated_mouse)
	assert(moves == 1 and selected_cell == 4 and turn == 2,
		"Second same-kind mouse click must remain independent")
	_on_secondary()
	round_number = saved_round
	_reset_round()
	ai_enabled = saved_ai
	_refresh_surface()
	print("BLUE_SEA_TOUCH_RELEASE_GATE_PASS tap=1 return_drag=0 multitouch=0 ui_to_board=0 echo=0 mouse=2")

# Godot InputEvent.DEVICE_ID_EMULATION is -1 for touchscreen mouse echo.
# A synthetic mouse press may precede ScreenTouch down, so time/distance
# guards alone cannot prevent an early, unintended move. This test exercises
# the actual production _input path across all seven live world treatments.
# Native engine smoke only; NOT evidence of real-phone touch qualification.
func _run_headless_emulated_mouse_identity_smoke() -> void:
	var old_world := current_world
	var old_ai := ai_enabled
	var old_round := round_number
	var old_rule := current_rule
	ai_enabled = false
	current_rule = "CD"
	round_number = 1
	for world in range(WorldVisuals.WORLDS.size()):
		_set_world(world)
		_reset_round()
		_on_reserve_pressed(1, 0)
		var point := PerspectiveGeometry.cell_center(current_world, 4, perspective_rect)
		var ghost := InputEventMouseButton.new()
		ghost.device = InputEvent.DEVICE_ID_EMULATION
		ghost.button_index = MOUSE_BUTTON_LEFT
		ghost.position = point
		ghost.pressed = true
		# Previously this FIRST mouse press could place the rank before any
		# ScreenTouch had armed _touch_primary_active.
		_input(ghost)
		assert(moves == 0 and selected_reserve == 0,
			"Pre-touch emulated mouse must not place a piece")
		var touch := InputEventScreenTouch.new()
		touch.index = 0
		touch.position = point
		touch.pressed = true
		_input(touch)
		_input(ghost)
		assert(moves == 0 and _touch_board_pending,
			"Touch-down and mid-hold emulated mouse must not commit")
		touch.pressed = false
		_input(touch)
		assert(moves == 1 and turn == 2 and not reserve_available[0][0],
			"Only primary finger-up may commit the selected rank")
		_input(ghost)
		assert(moves == 1, "Post-release emulated mouse must not double-place")
		# A real mouse on the same board remains usable on its own click.
		_reset_round()
		_on_reserve_pressed(1, 0)
		_touch_mouse_echo_deadline_msec = 0
		_touch_multifinger_mouse_echo_deadline_msec = 0
		_last_board_press_frame = -100
		_last_board_press_kind = "none"
		var physical := InputEventMouseButton.new()
		physical.device = InputEvent.DEVICE_ID_MOUSE
		physical.button_index = MOUSE_BUTTON_LEFT
		physical.position = point
		physical.pressed = true
		_input(physical)
		assert(moves == 1 and turn == 2,
			"Physical mouse must retain independent exact board click")
	current_rule = old_rule
	round_number = old_round
	_set_world(old_world)
	_reset_round()
	ai_enabled = old_ai
	_refresh_surface()
	print("BLUE_SEA_EMULATED_MOUSE_PRE_TOUCH_PASS worlds=7 pre=0 release=1 echo=0 physical=1")

# Synthetic Godot gesture transaction regression. Not physical-phone QA.
# Exercise actual _input + reserve handler, all seven shared world surfaces.
func _run_headless_touch_state_binding_smoke() -> void:
	var old_world := current_world
	var old_ai := ai_enabled
	var old_round := round_number
	ai_enabled = false
	for world in range(WorldVisuals.WORLDS.size()):
		_set_world(world)
		_reset_round()
		_on_reserve_pressed(1, 0)
		_refresh_perspective_layer()
		var point := PerspectiveGeometry.cell_center(current_world, 4, perspective_rect)
		var touch := InputEventScreenTouch.new()
		touch.index = 0
		touch.position = point
		touch.pressed = true
		_input(touch)
		assert(_touch_board_pending and not _touch_board_state_at_press.is_empty())
		# A keyboard or other input can change rank during a long hold.
		_on_reserve_pressed(1, 1)
		touch.pressed = false
		_input(touch)
		assert(moves == 0 and selected_reserve == 1 and board_stacks[4].is_empty(),
			"Finger release must not place a newly selected rank")
		# A world switch must also invalidate the original gesture, even if
		# the new board happens to map the same screen point to cell 4.
		_reset_round()
		_on_reserve_pressed(1, 0)
		touch.pressed = true
		_input(touch)
		_set_world((world + 1) % WorldVisuals.WORLDS.size())
		touch.pressed = false
		_input(touch)
		assert(moves == 0 and reserve_available[0][0],
			"World switch during touch must not place a rank")
		# Unchanged same-cell tap still commits in every world.
		_set_world(world)
		_reset_round()
		_on_reserve_pressed(1, 0)
		touch.pressed = true
		_input(touch)
		touch.pressed = false
		_input(touch)
		assert(moves == 1 and not reserve_available[0][0],
			"Ordinary touch release must remain playable in all seven worlds")
	_set_world(old_world)
	round_number = old_round
	_reset_round()
	ai_enabled = old_ai
	_refresh_surface()
	print("BLUE_SEA_TOUCH_STATE_BINDING_PASS worlds=7 stale_rank=0 world_switch=0 normal_taps=7")

# Opt-in Godot regression for the SAME live touch transaction in all worlds.
# Synthetic geometry-token variations are not physical device resize evidence.
# A menu opened and closed while a finger remains down must not convert
# that original finger-up into a legal placement. Exercises the real shared
# input and modal visibility signals in every world; not real-phone QA.
func _run_headless_modal_touch_transaction_smoke() -> void:
	var saved_world := current_world
	var saved_ai := ai_enabled
	var saved_round := round_number
	ai_enabled = false
	for world in range(WorldVisuals.WORLDS.size()):
		_set_world(world)
		_reset_round()
		_on_reserve_pressed(1, 0)
		_refresh_perspective_layer()
		var point := PerspectiveGeometry.cell_center(world, 4, perspective_rect)
		var touch := InputEventScreenTouch.new()
		touch.index = 0
		touch.position = point
		touch.pressed = true
		_input(touch)
		assert(_touch_board_pending, "Touch must arm before menu opens")
		mobile_menu_panel.show()
		assert(not _touch_board_pending, "Opening menu must cancel armed touch")
		mobile_menu_panel.hide()
		touch.pressed = false
		_input(touch)
		assert(moves == 0 and reserve_available[0][0] and board_stacks[4].is_empty(),
			"Closing menu must not rearm old finger-up")
		# Desktop popups have a separate opening signal; they also invalidate.
		touch.pressed = true
		_input(touch)
		assert(_touch_board_pending)
		top_menu.get_popup().about_to_popup.emit()
		assert(not _touch_board_pending, "Desktop popup must cancel held touch")
		touch.pressed = false
		_input(touch)
		assert(moves == 0 and reserve_available[0][0])
		# A fresh independent tap must still place exactly one real rank.
		touch.pressed = true
		_input(touch)
		touch.pressed = false
		_input(touch)
		assert(moves == 1 and not reserve_available[0][0] and turn == 2,
			"Fresh tap after modal dismissal must remain playable")
	_set_world(saved_world)
	round_number = saved_round
	_reset_round()
	ai_enabled = saved_ai
	_refresh_surface()
	print("BLUE_SEA_MODAL_TOUCH_TRANSACTION_PASS worlds=7 canceled=14 fresh=7")

func _run_headless_touch_geometry_resize_smoke() -> void:
	var old_world := current_world
	var old_ai := ai_enabled
	var old_round := round_number
	ai_enabled = false
	var sample_rect := Rect2(Vector2.ZERO, Vector2(746, 190))
	var initial := _touch_geometry_token(Vector2(746, 280), Vector2i(746, 280), sample_rect, 1.0)
	for changed in [
		_touch_geometry_token(Vector2(844, 390), Vector2i(844, 390), sample_rect, 1.0),
		_touch_geometry_token(Vector2(746, 280), Vector2i(1492, 560), sample_rect, 1.0),
		_touch_geometry_token(Vector2(746, 280), Vector2i(746, 280), Rect2(Vector2.ZERO, Vector2(746, 170)), 1.0),
		_touch_geometry_token(Vector2(746, 280), Vector2i(746, 280), sample_rect, 2.0)
	]:
		assert(changed != initial, "Resize/DPI/dock change must invalidate held touch")
	for world in range(WorldVisuals.WORLDS.size()):
		_set_world(world)
		_reset_round()
		_on_reserve_pressed(1, 0)
		_refresh_perspective_layer()
		var point := PerspectiveGeometry.cell_center(current_world, 4, perspective_rect)
		var touch := InputEventScreenTouch.new()
		touch.index = 0
		touch.position = point
		touch.pressed = true
		_input(touch)
		assert(_touch_board_pending and _touch_board_state_at_press.size() == 11)
		var at_press := _touch_board_state_at_press.duplicate(true)
		var mutated := at_press.duplicate(true)
		mutated[10] = _touch_geometry_token(Vector2(844, 390), Vector2i(844, 390), sample_rect, 1.0)
		assert(mutated != at_press, "Touch token must include actual geometry")
		# The real _process resize branch performs this cancellation BEFORE
		# refreshing the live board; release cannot place a stale rank.
		_cancel_pending_board_touch()
		touch.pressed = false
		_input(touch)
		assert(moves == 0 and reserve_available[0][0] and board_stacks[4].is_empty(),
			"Resized held touch spent a piece")
		# Normal stationary taps must remain playable after cancellation.
		touch.pressed = true
		_input(touch)
		touch.pressed = false
		_input(touch)
		assert(moves == 1 and not reserve_available[0][0],
			"Resize guard blocked ordinary same-cell tap")
	_set_world(old_world)
	round_number = old_round
	_reset_round()
	ai_enabled = old_ai
	_refresh_surface()
	print("BLUE_SEA_TOUCH_RESIZE_TRANSACTION_PASS worlds=7 profiles=4 stale=0 ordinary=7")

# Opt-in native Godot regression: a secondary finger can touch first, not
# just after index 0. Both orders must leave the shared live match unchanged.
func _run_headless_multitouch_order_smoke() -> void:
	var old_world := current_world
	var old_ai := ai_enabled
	var old_round := round_number
	ai_enabled = false
	for world in range(WorldVisuals.WORLDS.size()):
		_set_world(world)
		for secondary_first in [true, false]:
			_reset_round()
			_on_reserve_pressed(1, 0)
			_refresh_perspective_layer()
			var point := PerspectiveGeometry.cell_center(current_world, 4, perspective_rect)
			var primary := InputEventScreenTouch.new()
			primary.index = 0
			primary.position = point
			primary.pressed = true
			var secondary := InputEventScreenTouch.new()
			secondary.index = 1
			secondary.position = point
			secondary.pressed = true
			if secondary_first:
				_input(secondary)
				_input(primary)
			else:
				_input(primary)
				_input(secondary)
			assert(not _touch_board_pending, "Two fingers must never arm a board move")
			secondary.pressed = false
			_input(secondary)
			primary.pressed = false
			_input(primary)
			assert(moves == 0 and reserve_available[0][0] and board_stacks[4].is_empty(),
				"Secondary-first/primary-first must not spend a rank")
			assert(_touch_secondary_indices.is_empty(), "Released secondary finger leaked")
		# After the second finger leaves, a fresh single-finger tap works.
		_reset_round()
		_on_reserve_pressed(1, 0)
		var single := InputEventScreenTouch.new()
		single.index = 0
		single.position = PerspectiveGeometry.cell_center(current_world, 4, perspective_rect)
		single.pressed = true
		_input(single)
		single.pressed = false
		_input(single)
		assert(moves == 1 and not reserve_available[0][0],
			"A fresh one-finger tap must remain playable")
	# A missing finger-up after app suspension must not permanently block input.
	var held := InputEventScreenTouch.new()
	held.index = 2
	held.position = Vector2(10.0, 10.0)
	held.pressed = true
	_input(held)
	assert(_touch_secondary_indices.has(2))
	_notification(NOTIFICATION_APPLICATION_FOCUS_OUT)
	assert(_touch_secondary_indices.is_empty(), "Focus loss must clear stale fingers")
	_set_world(old_world)
	round_number = old_round
	_reset_round()
	ai_enabled = old_ai
	_refresh_surface()
	print("BLUE_SEA_MULTITOUCH_ORDER_PASS worlds=7 orders=14 fresh_taps=7 focus_reset=1")

# v125: regression for synthetic mouse-down at a SECONDARY finger's new
# location, not merely at the primary finger's original touch point.
# Exercises all seven shared worlds through actual _input and game handlers.
# This is a Godot opt-in smoke, NOT physical touchscreen evidence.
func _run_headless_secondary_drag_mouse_echo_smoke() -> void:
	var saved_world := current_world
	var saved_ai := ai_enabled
	var saved_round := round_number
	ai_enabled = false
	for world in range(WorldVisuals.WORLDS.size()):
		_set_world(world)
		_reset_round()
		_on_reserve_pressed(1, 0)
		_refresh_perspective_layer()
		var primary_point := PerspectiveGeometry.cell_center(world, 4, perspective_rect)
		var secondary_start := PerspectiveGeometry.cell_center(world, 0, perspective_rect)
		var secondary_end := PerspectiveGeometry.cell_center(world, 8, perspective_rect)
		assert(primary_point.distance_to(secondary_end) > 6.0)
		var primary := InputEventScreenTouch.new()
		primary.index = 0
		primary.position = primary_point
		primary.pressed = true
		_input(primary)
		var secondary := InputEventScreenTouch.new()
		secondary.index = 1
		secondary.position = secondary_start
		secondary.pressed = true
		_input(secondary)
		var secondary_drag := InputEventScreenDrag.new()
		secondary_drag.index = 1
		secondary_drag.position = secondary_end
		_input(secondary_drag)
		assert(_touch_mouse_echo_position == secondary_end,
			"Secondary drag must update synthetic mouse echo location")
		var mouse := InputEventMouseButton.new()
		mouse.button_index = MOUSE_BUTTON_LEFT
		mouse.pressed = true
		mouse.position = secondary_end
		_input(mouse)
		assert(moves == 0 and reserve_available[0][0] and board_stacks[8].is_empty(),
			"Mouse echo from moving secondary finger committed a rank")
		secondary.pressed = false
		secondary.position = secondary_end
		_input(secondary)
		primary.pressed = false
		_input(primary)
		_input(mouse)
		assert(moves == 0 and board_stacks[8].is_empty(),
			"Delayed secondary finger-up mouse echo committed a rank")
		# After the echo window expires, a genuine mouse remains playable.
		_touch_mouse_echo_deadline_msec = 0
		_touch_multifinger_mouse_echo_deadline_msec = 0
		_last_board_press_kind = "none"
		_last_board_press_frame = -100
		_input(mouse)
		assert(moves == 1 and int(board_stacks[8][-1].rank) == 1,
			"Real mouse board play was blocked after multitouch")
	_set_world(saved_world)
	round_number = saved_round
	_reset_round()
	ai_enabled = saved_ai
	_refresh_surface()
	print("BLUE_SEA_SECONDARY_DRAG_ECHO_PASS worlds=7 echo_held=0 echo_release=0 real_mouse=7")

func _run_headless_reference_menu_smoke() -> void:
	# The visible legacy reference glyph must have an actual mobile action.
	assert(reference_menu_hotspot != null and reference_menu_hotspot.flat)
	assert(reference_menu_hotspot.size.x * _physical_pixel_scale() >= 43.5)
	assert(reference_menu_hotspot.size.y * _physical_pixel_scale() >= 43.5)
	assert(reference_menu_clearance.custom_minimum_size.x >= reference_menu_hotspot.position.x + reference_menu_hotspot.size.x)
	var saved_moves := moves
	var saved_world := current_world
	for world in range(WorldVisuals.WORLDS.size()):
		_set_world(world)
		assert(reference_menu_hotspot.visible, "Menu hotspot must exist in every approved world")
		assert(reference_menu_art != null and reference_menu_art.visible and reference_menu_art.texture != null,
			"Approved menu glyph must be visibly rendered in every world")
		var plate_image := reference_menu_art.texture.get_image()
		assert(plate_image != null and plate_image.get_width() > 40 and plate_image.get_height() > 40,
			"Missing source-derived menu plate pixels")
		assert(plate_image.get_pixel(int(plate_image.get_width() / 2), int(plate_image.get_height() / 2)).a > 0.99,
			"Menu plate must have a visible center")
		if world == 0:
			assert(not (get_node("SceneryPerimeter") as TextureRect).visible,
				"Void must retain its minimal background while showing the menu")
		reference_menu_hotspot.pressed.emit()
		if _use_mobile_menu():
			assert(mobile_menu_panel.visible, "Reference hamburger must open the touch-safe mobile menu")
		else:
			assert(top_menu.get_popup().visible, "Reference hamburger must open the live game menu")
		assert(_modal_blocks_board_input(), "Open menu must block hidden board moves")
		mobile_menu_panel.hide()
		top_menu.get_popup().hide()
		assert(moves == saved_moves, "Menu hotspot must not alter the current match")
	_set_world(saved_world)
	print("BLUE_SEA_REFERENCE_MENU_TOUCH_PASS worlds=7 target_px=", reference_menu_hotspot.size * _physical_pixel_scale())

func _run_headless_tutorial_live_practice_smoke() -> void:
	# Execute the real phone menu navigation and selection handler without
	# inventing a parallel board or altering the persisted match state.
	var preserved := _match_snapshot()
	var preserved_ai := ai_enabled
	ai_enabled = false
	match_score = [0, 0]
	match_winner = 0
	round_number = 1
	_reset_round()
	var practice_snapshot := _match_snapshot()
	assert(_has_legal_move(turn), "Fresh tutorial practice needs a legal move")
	mobile_menu_panel.show()
	_on_mobile_menu_action(3)
	assert(_mobile_menu_page == "tutorial_1" and mobile_menu_panel.visible)
	for page_id in [701, 702, 703]:
		_on_mobile_menu_action(page_id)
	assert(_mobile_menu_page == "tutorial_4")
	var practice_button := mobile_menu_list.get_node("MobileChoice_704") as Button
	assert(not practice_button.disabled, "Fresh tutorial must allow a practice selection")
	_on_mobile_menu_action(704)
	assert(not mobile_menu_panel.visible and selected_reserve >= 0)
	var found := false
	for cell in range(9):
		if _is_legal_move(turn, selected_reserve + 1, cell):
			assert(perspective_legal_outlines[cell].visible, "Tutorial did not highlight a legal live cell")
			found = true
	assert(found, "Tutorial practice selected a dead rank")
	assert(_match_snapshot() == practice_snapshot, "Tutorial must not play or reset a match")
	_on_secondary()
	_apply_match_snapshot(preserved)
	ai_enabled = preserved_ai
	_refresh_surface()
	assert(_match_snapshot() == preserved, "Tutorial fixture must restore the original match")
	print("BLUE_SEA_LIVE_PHONE_TUTORIAL_PASS pages=4 no_automatic_move legal_highlights")

# Real shared mobile tutorial flow: preserving a previously selected high
# rank is essential when that rank is scrolled off-screen on a dense phone.
# The native fixture never places a piece or changes the match score.
func _run_headless_tutorial_selection_continuity_smoke() -> void:
	var original := _match_snapshot()
	var original_ai := ai_enabled
	var original_world := current_world
	var original_selection := selected_reserve
	var original_cell := selected_cell
	ai_enabled = false
	match_score = [0, 0]
	match_winner = 0
	round_number = 1
	_reset_round()
	_on_reserve_pressed(1, 8)
	assert(selected_reserve == 8, "Rank 9 must be selectable before tutorial")
	var before := _match_snapshot()
	before.erase("reserve_scroll")
	for world in range(WorldVisuals.WORLDS.size()):
		_set_world(world)
		selected_cell = 4  # Stale keyboard target must not survive tutorial.
		_render_mobile_menu_page("tutorial_4")
		mobile_menu_panel.show()
		_on_mobile_menu_action(704)
		assert(not mobile_menu_panel.visible and selected_reserve == 8 and selected_cell == -1,
			"Tutorial toggled off/replaced a preselected legal rank")
		var current := _match_snapshot()
		current.erase("reserve_scroll")
		assert(current == before, "Tutorial changed the actual match")
		await get_tree().process_frame
		await get_tree().process_frame
		var rank_button := _reserve_node(1).get_child(8) as Button
		assert(rank_button != null and rank_button.visible and reserve_scroller.visible,
			"Tutorial did not retain the active reserve")
		var view := reserve_scroller.get_global_rect()
		var piece := rank_button.get_global_rect()
		assert(piece.position.x >= view.position.x - 1.0 and piece.end.x <= view.end.x + 1.0,
			"Tutorial-selected rank 9 is outside the scroller")
	_set_world(original_world)
	_apply_match_snapshot(original)
	selected_reserve = original_selection
	selected_cell = original_cell
	ai_enabled = original_ai
	mobile_menu_panel.hide()
	_refresh_surface()
	print("BLUE_SEA_TUTORIAL_SELECTION_CONTINUITY_PASS worlds=7 rank9 scroll_visible no_move")

func _run_headless_mobile_settings_smoke() -> void:
	# Regression for the 746x280 phone menu: settings are reachable in three
	# small submenus, rather than an unbounded fifteen-item vertical list.
	var saved_world := current_world
	var saved_moves := moves
	var saved_round := round_number
	var saved_score := match_score.duplicate()
	var saved_game_over := game_over
	var saved_rule := current_rule
	var saved_difficulty := ai_difficulty
	var saved_persona := ai_persona
	_set_world(0)
	moves = 0
	round_number = 1
	match_score = [0, 0]
	game_over = false
	_populate_game_menu()
	var popup := top_menu.get_popup()
	assert(popup.item_count <= 6, "Phone top menu must remain compact")
	assert(rule_submenu.item_count == 3 and difficulty_submenu.item_count == 3 and persona_submenu.item_count == 3)
	assert(popup.get_item_submenu_node(popup.get_item_index(100)) == rule_submenu)
	assert(popup.get_item_submenu_node(popup.get_item_index(101)) == difficulty_submenu)
	assert(popup.get_item_submenu_node(popup.get_item_index(102)) == persona_submenu)
	assert(popup.max_size.y <= maxi(180, get_window().size.y - 12))
	assert(rule_submenu.get_item_index(300) >= 0 and difficulty_submenu.get_item_index(402) >= 0 and persona_submenu.get_item_index(412) >= 0)
	moves = 1
	_populate_game_menu()
	assert(popup.is_item_disabled(popup.get_item_index(100)), "Rules must lock after first move")
	assert(not popup.is_item_disabled(popup.get_item_index(101)), "Difficulty remains configurable")
	assert(not popup.is_item_disabled(popup.get_item_index(102)), "Persona remains configurable")
	moves = saved_moves
	round_number = saved_round
	match_score = saved_score
	game_over = saved_game_over
	current_rule = saved_rule
	ai_difficulty = saved_difficulty
	ai_persona = saved_persona
	_set_world(saved_world)
	_populate_game_menu()
	print("BLUE_SEA_MOBILE_SETTINGS_MENU_PASS compact=6 nested=3x3 rule_lock=PASS")

func _run_headless_mobile_menu_touch_smoke() -> void:
	if not _use_mobile_menu():
		return
	var original_rule := current_rule
	var original_difficulty := ai_difficulty
	var original_persona := ai_persona
	var original_ai := ai_enabled
	var original_world := current_world
	var original_moves := moves
	var original_round := round_number
	var original_score := match_score.duplicate()
	var original_game_over := game_over
	_set_world(0)
	moves = 0
	round_number = 1
	match_score = [0, 0]
	game_over = false
	_open_mobile_menu()
	assert(mobile_menu_panel.visible and _modal_blocks_board_input())
	assert(not mobile_menu_button.visible and not top_menu.visible)
	assert(not mobile_world_button.visible and not ai_toggle.visible)
	assert(reference_menu_hotspot.visible, "Canonical menu glyph must remain accessible")
	assert(mobile_menu_list.get_node_or_null("MobileChoice_105") != null)
	assert(mobile_menu_list.get_node_or_null("MobileChoice_106") != null)
	var physical_scale := _physical_pixel_scale()
	for choice in mobile_menu_list.get_children():
		assert(choice.size.y * physical_scale >= 43.5 or choice.custom_minimum_size.y * physical_scale >= 43.5,
			"Mobile settings must have >=44 physical-pixel touch targets")
	_on_mobile_menu_action(106)
	assert(ai_enabled != original_ai and mobile_menu_panel.visible)
	_on_mobile_menu_action(106)
	assert(ai_enabled == original_ai and mobile_menu_panel.visible)
	_on_mobile_menu_action(100)
	assert(_mobile_menu_page == "rules" and mobile_menu_list.get_child_count() == 4)
	_on_mobile_menu_action(301)
	assert(current_rule == "D" and not mobile_menu_panel.visible)
	_open_mobile_menu()
	_on_mobile_menu_action(101)
	_on_mobile_menu_action(402)
	assert(ai_difficulty == 3)
	_open_mobile_menu()
	_on_mobile_menu_action(102)
	_on_mobile_menu_action(412)
	assert(ai_persona == 2)
	moves = 1
	_open_mobile_menu()
	assert((mobile_menu_list.get_node("MobileChoice_100") as Button).disabled,
		"Rules must lock once the match has started")
	var before := current_rule
	_on_mobile_menu_action(300)
	assert(current_rule == before, "Mobile menu must not bypass the rule lock")
	current_rule = original_rule
	ai_difficulty = original_difficulty
	ai_persona = original_persona
	moves = original_moves
	round_number = original_round
	match_score = original_score
	game_over = original_game_over
	mobile_menu_panel.hide()
	_set_world(original_world)
	print("BLUE_SEA_MOBILE_TOUCH_MENU_PASS touch_px>=44 rules_difficulty_persona modal_lock")

# Android/system Back regression: one shared game, no accidental reset/quit,
# no ghost moves behind a menu, and a two-frame OS/key duplicate guard.
func _run_headless_mobile_back_navigation_smoke() -> void:
	if not _use_mobile_menu():
		return
	var original := _match_snapshot()
	var original_ai := ai_enabled
	var original_dirty := _match_save_dirty
	var original_attempts := _match_save_retry_attempts
	ai_enabled = false
	mobile_menu_panel.hide()
	_last_mobile_back_frame = -100
	var before := _match_snapshot()
	_handle_mobile_back()
	assert(mobile_menu_panel.visible and _mobile_menu_page == "main", "Back must open canonical phone menu")
	_handle_mobile_back()
	assert(mobile_menu_panel.visible, "OS/key echo must not close menu immediately")
	await get_tree().process_frame
	await get_tree().process_frame
	await get_tree().process_frame
	_handle_mobile_back()
	assert(not mobile_menu_panel.visible, "Second independent Back must close menu")
	await get_tree().process_frame
	await get_tree().process_frame
	await get_tree().process_frame
	_handle_mobile_back()
	_on_mobile_menu_action(1)
	assert(mobile_menu_panel.visible and _mobile_menu_page == "confirm_reset")
	await get_tree().process_frame
	await get_tree().process_frame
	await get_tree().process_frame
	_handle_mobile_back()
	assert(mobile_menu_panel.visible and _mobile_menu_page == "main", "Back must CANCEL reset")
	_on_mobile_menu_action(3)
	assert(_mobile_menu_page == "tutorial_1")
	_on_mobile_menu_action(701)
	assert(_mobile_menu_page == "tutorial_2")
	await get_tree().process_frame
	await get_tree().process_frame
	await get_tree().process_frame
	_handle_mobile_back()
	assert(_mobile_menu_page == "tutorial_1", "Back must return to previous tutorial page")
	assert(_match_snapshot() == before, "Back navigation changed the live match")
	mobile_menu_panel.hide()
	_apply_match_snapshot(original)
	ai_enabled = original_ai
	_match_save_dirty = original_dirty
	_match_save_retry_attempts = original_attempts
	_last_mobile_back_frame = -100
	_refresh_surface()
	print("BLUE_SEA_MOBILE_BACK_NAVIGATION_PASS menu=toggle duplicate=suppressed reset=cancel tutorial=back game=unchanged")

func _run_headless_mobile_header_smoke() -> void:
	if not _use_mobile_menu():
		return
	_layout_reference_menu_hotspot()
	assert(reference_menu_hotspot.visible, "Approved menu hotspot missing")
	assert(not mobile_menu_button.visible and not mobile_world_button.visible)
	assert(not world_picker.visible and not ai_toggle.visible and not top_menu.visible)
	assert(match_hud.visible and match_hud_label.text != "", "Live score must remain visible")
	var logo_right := 1107.0 / 1672.0 * get_viewport_rect().size.x
	var hud_left := reference_menu_clearance.custom_minimum_size.x
	assert(hud_left >= logo_right, "Mobile score overlaps the approved red logo")
	_open_mobile_menu()
	assert(mobile_menu_panel.visible and _mobile_menu_page == "main")
	assert(mobile_menu_list.get_node_or_null("MobileChoice_105") != null)
	assert(mobile_menu_list.get_node_or_null("MobileChoice_106") != null)
	mobile_menu_panel.hide()
	print("BLUE_SEA_MOBILE_HEADER_NO_LOGO_OVERLAP_PASS")

func _run_headless_mobile_world_selector_smoke() -> void:
	if not _use_mobile_menu():
		return
	var saved_world := current_world
	var saved_board := board_stacks.duplicate(true)
	var saved_reserve := reserve_available.duplicate(true)
	var saved_turn := turn
	var saved_moves := moves
	var saved_score := match_score.duplicate()
	var saved_ai := ai_enabled
	assert(not mobile_world_button.visible and not world_picker.visible,
		"Phone world selector must live in the reference-glyph menu")
	_open_mobile_menu()
	_on_mobile_menu_action(105)
	assert(mobile_menu_panel.visible and _mobile_menu_page == "worlds")
	assert(_modal_blocks_board_input(), "World chooser must block gameplay taps")
	assert(mobile_menu_list.get_child_count() == 8, "Seven canonical worlds + back")
	var scale := _physical_pixel_scale()
	for choice in mobile_menu_list.get_children():
		assert((choice as Button).custom_minimum_size.y * scale >= 43.5,
			"Every world must have a >=44 physical pixel tap target")
	for world_id in range(WorldVisuals.WORLDS.size()):
		if not mobile_menu_panel.visible:
			_open_mobile_worlds()
		_on_mobile_menu_action(500 + world_id)
		assert(current_world == world_id and not mobile_menu_panel.visible)
		assert(board_stacks == saved_board and reserve_available == saved_reserve,
			"World switching must preserve live game stacks and reserve")
		assert(turn == saved_turn and moves == saved_moves and match_score == saved_score)
		assert(ai_enabled == saved_ai, "World switching must not reset AI mode")
	_set_world(saved_world)
	print("BLUE_SEA_MOBILE_SEVEN_WORLD_SELECTOR_PASS touch>=44 modal seven_live_worlds game_state_preserved")

func _run_headless_mobile_reset_confirmation_smoke() -> void:
	if not _use_mobile_menu():
		return
	# Preserve the actual game across this opt-in headless fixture.
	var old_board := board_stacks.duplicate(true)
	var old_reserve := reserve_available.duplicate(true)
	var old_moves := moves
	var old_score := match_score.duplicate()
	var old_round := round_number
	var old_turn := turn
	var old_winner := winner
	var old_match_winner := match_winner
	var old_game_over := game_over
	var old_draw := round_draw
	var old_blocked := blocked_player
	var old_win_line := win_line.duplicate()
	var old_selected_cell := selected_cell
	var old_selected_reserve := selected_reserve
	board_stacks[4] = [{"player": 1, "rank": 1}]
	reserve_available[0][0] = false
	moves = 1
	match_score = [1, 2]
	round_number = 4
	_refresh_surface()
	var board_before := board_stacks.duplicate(true)
	var reserve_before := reserve_available.duplicate(true)
	var score_before := match_score.duplicate()
	_open_mobile_menu()
	_on_mobile_menu_action(1)
	assert(mobile_menu_panel.visible and _mobile_menu_page == "confirm_reset")
	assert(_modal_blocks_board_input(), "Reset confirmation must block live board input")
	assert(mobile_menu_list.get_child_count() == 2, "Reset needs Cancel and Confirm")
	var scale := _physical_pixel_scale()
	for choice in mobile_menu_list.get_children():
		assert((choice as Button).custom_minimum_size.y * scale >= 43.5,
			"Reset confirmation actions must be touch-safe")
	_on_mobile_menu_action(-2)
	assert(not mobile_menu_panel.visible, "Cancel must close reset confirmation")
	assert(board_stacks == board_before and reserve_available == reserve_before and match_score == score_before,
		"Cancel must preserve game state")
	# Stale/misrouted confirm action must never bypass the visible confirmation.
	_on_mobile_menu_action(600)
	assert(board_stacks == board_before and match_score == score_before,
		"Hidden confirmation must not reset match")
	_open_mobile_menu()
	_on_mobile_menu_action(1)
	_on_mobile_menu_action(600)
	assert(not mobile_menu_panel.visible and moves == 0 and round_number == 1)
	assert(match_score == [0, 0] and board_stacks == [[], [], [], [], [], [], [], [], []],
		"Confirmed reset must start a clean match")
	assert(reserve_available == [[true,true,true,true,true,true,true,true,true],[true,true,true,true,true,true,true,true,true]],
		"Confirmed reset must restore all pieces")
	# Do not leak test mutations into subsequent tests or user data.
	board_stacks = old_board
	reserve_available = old_reserve
	moves = old_moves
	match_score = old_score
	round_number = old_round
	turn = old_turn
	winner = old_winner
	match_winner = old_match_winner
	game_over = old_game_over
	round_draw = old_draw
	blocked_player = old_blocked
	win_line = old_win_line
	selected_cell = old_selected_cell
	selected_reserve = old_selected_reserve
	_refresh_surface()
	print("BLUE_SEA_MOBILE_RESET_CONFIRM_PASS touch>=44 cancel_preserves guarded_confirm clean_match")

func _run_headless_pirate_menu_smoke() -> void:
	# Regression: seven-world selector must not orphan the accepted Pirate story.
	var saved_world := current_world
	var saved_moves := moves
	var saved_score := match_score.duplicate()
	_set_world(0)
	_populate_game_menu()
	assert(top_menu.get_popup().get_item_index(4) == -1, "Pirate opening is world-specific")
	_set_world(1)
	# The scenery is strictly a non-interactive perimeter; live tiles remain.
	var scenery := get_node_or_null("SceneryPerimeter") as TextureRect
	assert(scenery != null and scenery.texture != null and scenery.mouse_filter == Control.MOUSE_FILTER_IGNORE,
		"Approved-reference scenery must load without intercepting touches")
	assert(perspective_tiles.size() == 9, "Scenery cannot replace nine live board cells")
	_populate_game_menu()
	assert(top_menu.get_popup().get_item_index(4) >= 0, "Pirate opening must be reachable from menu")
	var pirate_choice := get_node("PirateOpeningChoiceSurface/PirateOpeningChoice") as Control
	pirate_choice.hide()
	_on_game_menu_item(4)
	assert(pirate_choice.visible, "Pirate opening controller was not invoked")
	assert(_modal_blocks_board_input(), "Pirate opening must own input while visible")
	assert(moves == saved_moves and match_score == saved_score, "Opening must not change live gameplay")
	# A phone has no ESC key: verify the dedicated close control after a story choice.
	var close := pirate_choice.get_node_or_null("Shell/Header/CloseButton") as Button
	assert(close != null, "Pirate opening must have an always-visible header close control")
	assert(pirate_choice.get_node_or_null("Shell/StoryScroll/Column") != null, "Narrative must scroll independently from close")
	assert(close.custom_minimum_size.y * _physical_pixel_scale() >= 43.5, "Pirate close touch target below 44px")
	close.pressed.emit()
	assert(not pirate_choice.visible, "Pirate close must dismiss the modal")
	_set_world(saved_world)
	assert(not _modal_blocks_board_input(), "Closing Pirate opening must restore board input")
	print("BLUE_SEA_PIRATE_OPENING_MENU_PASS visible_reachable_state_preserved")

func _run_headless_modal_input_smoke() -> void:
	# Regression: pointer and keyboard events must not place pieces through overlays.
	var saved_ai := ai_enabled
	ai_enabled = false
	round_number = 1
	_reset_round()
	_on_reserve_pressed(1, 0)
	assert(selected_reserve == 0)
	_refresh_perspective_layer()
	var point := PerspectiveGeometry.cell_center(current_world, 4, perspective_rect)
	var pointer := InputEventMouseButton.new()
	pointer.button_index = MOUSE_BUTTON_LEFT
	pointer.pressed = true
	pointer.position = point
	var key := InputEventKey.new()
	key.keycode = KEY_ENTER
	key.pressed = true
	rules_dialog.visible = true
	assert(_modal_blocks_board_input(), "rules overlay must block board input")
	_input(pointer)
	_unhandled_key_input(key)
	assert(moves == 0 and _top_piece(4).is_empty(), "rules overlay leaked a game move")
	rules_dialog.hide()
	reset_dialog.visible = true
	assert(_modal_blocks_board_input(), "reset confirmation must block board input")
	_input(pointer)
	assert(moves == 0, "reset confirmation leaked a game move")
	reset_dialog.hide()
	var pirate_choice := get_node_or_null("PirateOpeningChoiceSurface/PirateOpeningChoice") as Control
	assert(pirate_choice != null, "existing Pirate opening surface must be preserved")
	pirate_choice.show()
	assert(_modal_blocks_board_input(), "Pirate campaign overlay must block board input")
	_input(pointer)
	assert(moves == 0, "Pirate campaign overlay leaked a game move")
	pirate_choice.hide()
	assert(not _modal_blocks_board_input(), "closed overlays must restore game input")
	_input(pointer)
	assert(moves == 1 and _top_piece(4) == {"player": 1, "rank": 1}, "normal board touch must work after closing overlays")
	_reset_round()
	ai_enabled = saved_ai
	_refresh_surface()
	print("BLUE_SEA_MODAL_INPUT_ISOLATION_PASS rules_reset_pirate_keyboard_pointer")

# The final placement handler is a public UI signal target. Earlier board
# handlers blocked modal input, but a stale ActionPrimary signal could bypass
# them and commit a preselected rank behind the overlay or during app pause.
# This native fixture exercises the REAL handler, not a duplicate rule model.
func _run_headless_primary_modal_commit_guard_smoke() -> void:
	var original := _match_snapshot()
	var original_history := _undo_history.duplicate(true)
	var original_ai := ai_enabled
	var original_paused := _app_paused
	var original_unfocused := _app_unfocused
	var original_queued := _ai_turn_queued
	mobile_menu_panel.hide()
	ai_enabled = false
	_app_paused = false
	_app_unfocused = false
	board_stacks = [[],[],[],[],[],[],[],[],[]]
	reserve_available = [[true,true,true,true,true,true,true,true,true],[true,true,true,true,true,true,true,true,true]]
	turn = 1
	moves = 0
	winner = 0
	game_over = false
	round_draw = false
	blocked_player = 0
	match_winner = 0
	selected_reserve = 0
	selected_cell = 0
	var before := _match_snapshot()
	mobile_menu_panel.show()
	assert(_modal_blocks_board_input(), "Primary commit fixture requires a visible modal")
	_on_primary()
	assert(_match_snapshot() == before and selected_reserve == 0 and selected_cell == 0,
		"ActionPrimary spent a piece behind the mobile menu")
	mobile_menu_panel.hide()
	_app_paused = true
	_on_primary()
	assert(_match_snapshot() == before, "ActionPrimary spent a piece while suspended")
	_app_paused = false
	_app_unfocused = true
	_on_primary()
	assert(_match_snapshot() == before, "ActionPrimary spent a piece while unfocused")
	_app_unfocused = false
	assert(not _modal_blocks_board_input(), "Fixture did not restore live input")
	_on_primary()
	assert(moves == 1 and board_stacks[0].size() == 1 and not reserve_available[0][0],
		"Final placement handler did not resume normal gameplay after modal close")
	_apply_match_snapshot(original)
	_undo_history = original_history
	ai_enabled = original_ai
	_app_paused = original_paused
	_app_unfocused = original_unfocused
	_ai_turn_queued = original_queued
	_refresh_surface()
	print("BLUE_SEA_PRIMARY_MODAL_COMMIT_GUARD_PASS menu pause focus normal_resume")

func _run_headless_ai_modal_guard_smoke() -> void:
	# Test the actual AI entrypoint with an in-scene modal, then resume.
	# This remains an engine fixture; offline Python checks cannot certify it.
	var saved_board := board_stacks.duplicate(true)
	var saved_reserves := reserve_available.duplicate(true)
	var saved_ai := ai_enabled
	var saved_turn := turn
	var saved_moves := moves
	var saved_game_over := game_over
	var saved_winner := winner
	var saved_draw := round_draw
	var saved_blocked := blocked_player
	var saved_selection := selected_reserve
	var saved_cell := selected_cell
	var saved_queued := _ai_turn_queued
	var saved_score := match_score.duplicate()
	var saved_match_winner := match_winner
	var saved_line := win_line.duplicate()
	board_stacks = [[],[],[],[],[],[],[],[],[]]
	reserve_available = [[true,true,true,true,true,true,true,true,true],[true,true,true,true,true,true,true,true,true]]
	turn = 2
	moves = 0
	game_over = false
	winner = 0
	round_draw = false
	blocked_player = 0
	selected_reserve = -1
	selected_cell = -1
	_ai_turn_queued = false
	ai_enabled = true
	match_winner = 0
	_refresh_surface()
	mobile_menu_panel.show()
	assert(_modal_blocks_board_input(), "AI modal test needs an active overlay")
	_queue_ai_turn_if_ready()
	assert(not _ai_turn_queued, "AI must not queue behind a modal")
	_play_ai_turn()
	assert(moves == 0 and turn == 2, "AI moved while a menu was open")
	mobile_menu_panel.hide()
	assert(not _modal_blocks_board_input(), "Closing the menu must unblock AI")
	_play_ai_turn()
	assert(moves == 1 and turn == 1, "AI did not resume its real move after menu closure")
	board_stacks = saved_board
	reserve_available = saved_reserves
	ai_enabled = saved_ai
	turn = saved_turn
	moves = saved_moves
	game_over = saved_game_over
	winner = saved_winner
	round_draw = saved_draw
	blocked_player = saved_blocked
	selected_reserve = saved_selection
	selected_cell = saved_cell
	_ai_turn_queued = saved_queued
	match_score = saved_score
	match_winner = saved_match_winner
	win_line = saved_line
	_refresh_surface()
	print("BLUE_SEA_AI_MODAL_PAUSE_RESUME_PASS")

func _run_headless_rule_modes_smoke() -> void:
	var saved_mode := current_rule
	var saved_score := match_score.duplicate()
	var saved_round := round_number
	round_number = 1
	match_score = [0, 0]
	_reset_round()
	for mode_id in range(3):
		_on_game_menu_item(300 + mode_id)
		assert(current_rule == ["C", "D", "CD"][mode_id], "mode menu must select requested rules")
	board_stacks[0] = [{"player": 1, "rank": 2}]
	board_stacks[1] = [{"player": 1, "rank": 2}]
	board_stacks[2] = [{"player": 1, "rank": 2}]
	current_rule = "C"
	assert(_winning_line(1) == [0, 1, 2], "C permits ordinary three-in-row")
	current_rule = "D"
	assert(_winning_line(1).is_empty(), "D requires a rank ladder")
	current_rule = "CD"
	assert(_winning_line(1).is_empty(), "CD requires a rank ladder")
	board_stacks[0] = [{"player": 1, "rank": 1}]
	board_stacks[1] = [{"player": 1, "rank": 2}]
	board_stacks[2] = [{"player": 1, "rank": 3}]
	assert(_winning_line(1) == [0, 1, 2], "CD accepts an ascending ladder")
	board_stacks[3] = [{"player": 1, "rank": 1}, {"player": 2, "rank": 2}]
	turn = 1
	assert(not _is_legal_move(1, 9, 3), "CD forbids third layer")
	current_rule = "D"
	assert(_is_legal_move(1, 9, 3), "D allows third layer")
	moves = 1
	_on_game_menu_item(300)
	assert(current_rule == "D", "mode must not change during a match")
	current_rule = saved_mode
	match_score = saved_score
	round_number = saved_round
	_reset_round()
	for level in range(1, 4):
		_on_game_menu_item(399 + level)
		assert(ai_difficulty == level)
	for persona_id in range(3):
		_on_game_menu_item(410 + persona_id)
		assert(ai_persona == persona_id)
	ai_difficulty = 2
	ai_persona = 0
	print("BLUE_SEA_RULE_MODES_PASS C_D_CD ladder_stack2_mode_menu ai_config")

func _run_headless_preferences_smoke() -> void:
	var old := [current_world, ai_enabled, ai_difficulty, ai_persona, current_rule]
	current_world = 5
	ai_enabled = true
	ai_difficulty = 3
	ai_persona = 2
	current_rule = "D"
	_save_preferences()
	var settings := ConfigFile.new()
	assert(settings.load(_preferences_path()) == OK, "Free Play settings file must be readable")
	assert(int(settings.get_value("free_play", "world", -1)) == 5)
	assert(bool(settings.get_value("free_play", "ai_enabled", false)))
	assert(int(settings.get_value("free_play", "ai_difficulty", -1)) == 3)
	assert(int(settings.get_value("free_play", "ai_persona", -1)) == 2)
	assert(str(settings.get_value("free_play", "rule", "")) == "D")
	current_world = old[0]
	ai_enabled = old[1]
	ai_difficulty = old[2]
	ai_persona = old[3]
	current_rule = old[4]
	_save_preferences()
	print("BLUE_SEA_FREEPLAY_PREFERENCES_PASS world_ai_difficulty_persona_rule")

func _run_headless_even_round_ai_smoke() -> void:
	ai_enabled = true
	ai_toggle.text = "ИИ: ВКЛ"
	round_number = 2
	_reset_round()
	await get_tree().process_frame
	await get_tree().process_frame
	assert(moves == 1 and turn == 1, "AI must make opening move in even round")
	assert(not _reserve_node(2).visible, "AI reserve must remain hidden")
	ai_enabled = false
	ai_toggle.text = "ИИ: ВЫКЛ"
	round_number = 1
	_reset_round()
	print("BLUE_SEA_AI_EVEN_ROUND_START_PASS")

func _run_headless_input_parity_smoke() -> void:
	_reset_round()
	var pointer_reserve := 2
	var pointer_cell := 4
	_on_cell_pressed(pointer_cell)
	assert(moves == 0 and _top_piece(pointer_cell).is_empty())
	_on_reserve_pressed(1, pointer_reserve)
	_on_cell_pressed(pointer_cell)
	assert(_top_piece(pointer_cell) == {"player": 1, "rank": pointer_reserve + 1})
	assert(turn == 2 and moves == 1)
	_reset_round()
	_on_reserve_pressed(1, pointer_reserve)
	selected_cell = pointer_cell
	var primary_key := InputEventKey.new()
	primary_key.keycode = KEY_ENTER
	primary_key.pressed = true
	_unhandled_key_input(primary_key)
	assert(_top_piece(pointer_cell) == {"player": 1, "rank": pointer_reserve + 1})
	assert(turn == 2 and moves == 1)
	var clear_key := InputEventKey.new()
	clear_key.keycode = KEY_ESCAPE
	clear_key.pressed = true
	selected_reserve = 3
	selected_cell = 3
	_unhandled_key_input(clear_key)
	assert(selected_reserve == -1 and selected_cell == -1)
	var menu_key := InputEventKey.new()
	menu_key.keycode = KEY_M
	menu_key.pressed = true
	game_over = true
	round_draw = true
	var before_round := round_number
	_unhandled_key_input(menu_key)
	assert(round_number == before_round and game_over, "M must open menu, not advance round")
	if _use_mobile_menu():
		assert(mobile_menu_panel.visible, "M must open physical-touch-safe mobile menu")
		mobile_menu_panel.hide()
	else:
		assert(top_menu.get_popup().visible, "M must open desktop menu")
		top_menu.get_popup().hide()
	game_over = false
	round_draw = false
	_refresh_surface()
	print("BLUE_SEA_INPUT_PARITY_PASS touch_pointer_buttons=PRIMARY/CLEAR/MENU keyboard=ENTER_ESCAPE_M")

func _run_headless_orientation_reload_smoke() -> void:
	# Rotation changes UI only; never alter the live board, reserves or score.
	var preserved_board := board_stacks.duplicate(true)
	var preserved_reserves := reserve_available.duplicate(true)
	var preserved_score := match_score.duplicate()
	var preserved_turn := turn
	var preserved_moves := moves
	var window := get_window()
	var original := Vector2i(window.content_scale_size)
	if original.x <= 0 or original.y <= 0:
		original = Vector2i(int(get_viewport_rect().size.x), int(get_viewport_rect().size.y))
	# Force a real phone portrait viewport even when CI started on desktop.
	var portrait := Vector2i(280, 746)
	window.content_scale_size = portrait
	window.size = portrait
	await get_tree().process_frame
	await get_tree().process_frame
	_process(0.0)
	var status := get_node("SafeArea/Landscape/Center/Status") as Label
	assert(status.text.contains("rotate device"))
	assert(orientation_overlay.visible, "Portrait must display a real rotate overlay")
	assert(_modal_blocks_board_input(), "Portrait must block hidden board touches")
	assert(_use_mobile_menu(), "Phone portrait must not switch to desktop popups")
	assert(not status.visible, "Phone status must not consume board space")
	window.content_scale_size = original
	window.size = original
	await get_tree().process_frame
	await get_tree().process_frame
	_process(0.0)
	assert(not status.text.contains("rotate device"))
	assert(not orientation_overlay.visible, "Landscape must restore interactive board")
	assert(status.visible == (not _use_mobile_menu()), "Status visibility follows physical size")
	assert(board_stacks == preserved_board and reserve_available == preserved_reserves)
	assert(match_score == preserved_score and turn == preserved_turn and moves == preserved_moves)
	await _assert_landscape_geometry()
	print("BLUE_SEA_ORIENTATION_RELOAD_PASS portrait=", portrait, " restored=", original)

func _run_headless_interaction_smoke() -> void:
	# D2 rules parity smoke: rank stacking, Stack-2 cap, ladder win and illegal preservation.
	_on_reserve_pressed(1, 0)
	_on_cell_pressed(0)
	assert(_top_piece(0) == {"player": 1, "rank": 1})
	assert(turn == 2 and moves == 1)

	# Opponent may cover with a strictly larger rank.
	_on_reserve_pressed(2, 1)
	_on_cell_pressed(0)
	assert(_top_piece(0) == {"player": 2, "rank": 2})
	assert(board_stacks[0].size() == 2)
	assert(turn == 1 and moves == 2)

	# CD uses Stack 2: a third piece cannot cover this cell.
	_on_reserve_pressed(1, 2)
	_on_cell_pressed(0)
	assert(board_stacks[0].size() == 2)
	assert(reserve_available[0][2] == true)
	assert(turn == 1 and moves == 2)

	# Build an increasing P1 ladder 1-2-3 across cells 3,4,5.
	_on_secondary()
	_on_reserve_pressed(1, 0)
	# rank 1 was already spent, so use 3/4/5 instead.
	_on_reserve_pressed(1, 2)
	_on_cell_pressed(3)
	_on_reserve_pressed(2, 0)
	_on_cell_pressed(6)
	_on_reserve_pressed(1, 3)
	_on_cell_pressed(4)
	_on_reserve_pressed(2, 2)
	_on_cell_pressed(7)
	_on_reserve_pressed(1, 4)
	_on_cell_pressed(5)
	assert(game_over and winner == 1)
	assert(win_line == [3,4,5])
	assert(_top_piece(3).rank == 3 and _top_piece(4).rank == 4 and _top_piece(5).rank == 5)
	assert(match_score == [1, 0])
	_on_menu()
	assert(round_number == 2 and turn == 2 and not game_over and winner == 0 and moves == 0)
	assert(match_score == [1, 0])
	for stack in board_stacks:
		assert(stack.is_empty())
	print("BLUE_SEA_D2_RULES_SMOKE_PASS round=", round_number, " starter=", turn, " score=", match_score)

	# Draw/stalemate must advance the round without changing match score.
	var score_before_draw := match_score.duplicate()
	round_draw = true
	game_over = true
	winner = 0
	_on_menu()
	assert(round_number == 3 and turn == 1 and not game_over and not round_draw and winner == 0 and moves == 0)
	assert(match_score == score_before_draw)
	for stack in board_stacks:
		assert(stack.is_empty())
	print("BLUE_SEA_DRAW_FLOW_SMOKE_PASS round=", round_number, " starter=", turn, " score=", match_score)

	# A player with no legal move is explicitly surfaced and skipped while the opponent continues.
	_reset_round()
	turn = 2
	reserve_available[1] = [false,false,false,false,false,false,false,false,false]
	assert(not _has_legal_move(2) and _has_legal_move(1))
	blocked_player = 2
	turn = 1
	assert(blocked_player == 2 and turn == 1 and not game_over)
	_reset_round()
	assert(blocked_player == 0)
	assert((_reserve_node(1).get_child(0) as Button).disabled == false)
	assert((_reserve_node(2).get_child(0) as Button).disabled == true)
	print("BLUE_SEA_BLOCKED_PLAYER_SMOKE_PASS blocked=P2 continuing=P1 reset=PASS")
	print("BLUE_SEA_TURN_AWARE_RESERVES_SMOKE_PASS active=P1 inactive=P2")