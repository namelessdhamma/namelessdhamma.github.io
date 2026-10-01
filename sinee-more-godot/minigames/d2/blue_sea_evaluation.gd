class_name BlueSeaEvaluation
extends RefCounted

const LINES := [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]]
const BASE_PROFILE := {
	"terminal": 100000.0, "board_control": 5.0, "center_control": 3.0,
	"closed_cell": 18.0, "cover_mobility": 1.2, "resource": 0.08,
	"ladder_resource": 0.35, "line_pressure": 7.0, "fork_pressure": 10.0
}

static func _top(position: Dictionary, cell: int) -> Dictionary:
	var stack: Array = position.board[cell]
	return {} if stack.is_empty() else stack[-1]

static func _other(player: int) -> int:
	return 2 if player == 1 else 1

static func _uses_stack2(rule: String) -> bool:
	return rule == "C" or rule == "CD"

static func _uses_ladder(rule: String) -> bool:
	return rule == "D" or rule == "CD"

static func _resource_value(position: Dictionary, player: int) -> float:
	var total := 0.0
	for rank in position.remaining[player]:
		total += float(rank * rank)
	return total

static func _board_control(position: Dictionary, player: int, profile: Dictionary) -> float:
	var score := 0.0
	for cell in range(9):
		var top := _top(position, cell)
		if top.is_empty(): continue
		var sign := 1.0 if int(top.player) == player else -1.0
		score += sign * float(profile.board_control)
		if cell == 4: score += sign * float(profile.center_control)
	return score

static func _closed_cell_value(position: Dictionary, player: int, rule: String, profile: Dictionary) -> float:
	if not _uses_stack2(rule): return 0.0
	var score := 0.0
	for cell in range(9):
		if position.board[cell].size() < 2: continue
		var top := _top(position, cell)
		var sign := 1.0 if int(top.player) == player else -1.0
		var factor := 1.35 if cell == 4 else (1.1 if cell % 2 == 0 else 1.0)
		score += sign * float(profile.closed_cell) * factor
	return score

static func _cover_mobility(position: Dictionary, player: int, rule: String) -> int:
	var count := 0
	for cell in range(9):
		var stack: Array = position.board[cell]
		var top := _top(position, cell)
		if top.is_empty() or int(top.player) == player: continue
		if _uses_stack2(rule) and stack.size() >= 2: continue
		for rank in position.remaining[player]:
			if int(rank) > int(top.rank): count += 1
	return count

static func _classic_line_features(position: Dictionary, player: int) -> Dictionary:
	var pressure := 0
	var near_wins := 0
	for line in LINES:
		var own := 0
		var opponent := 0
		var empty := 0
		for cell in line:
			var top := _top(position, cell)
			if top.is_empty(): empty += 1
			elif int(top.player) == player: own += 1
			else: opponent += 1
		if opponent == 0:
			pressure += own * own
			if own == 2 and empty == 1: near_wins += 1
	return {"pressure": pressure, "near_wins": near_wins}

static func _terminal_score(position: Dictionary, root_player: int, profile: Dictionary):
	if position.status == "draw": return 0.0
	if position.status != "win": return null
	var tempo := max(0, 20 - int(position.moves))
	return float(profile.terminal) + tempo if int(position.winner) == root_player else -float(profile.terminal) - tempo

static func evaluate_position(position: Dictionary, root_player: int, rule: String, profile: Dictionary = BASE_PROFILE) -> float:
	var terminal = _terminal_score(position, root_player, profile)
	if terminal != null: return float(terminal)
	var opponent := _other(root_player)
	var score := _board_control(position, root_player, profile)
	score += _closed_cell_value(position, root_player, rule, profile)
	score += float(_cover_mobility(position, root_player, rule) - _cover_mobility(position, opponent, rule)) * float(profile.cover_mobility)
	var resource_delta := _resource_value(position, root_player) - _resource_value(position, opponent)
	score += resource_delta * float(profile.resource)
	if _uses_ladder(rule):
		score += resource_delta * float(profile.ladder_resource)
	else:
		var root_lines := _classic_line_features(position, root_player)
		var opp_lines := _classic_line_features(position, opponent)
		score += float(root_lines.pressure - opp_lines.pressure) * float(profile.line_pressure)
		score += float(root_lines.near_wins - opp_lines.near_wins) * float(profile.fork_pressure)
	return score
