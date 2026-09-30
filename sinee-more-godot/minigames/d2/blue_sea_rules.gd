class_name BlueSeaRules
extends RefCounted

const LIGHT := 1
const DARK := 2
const RULE_C := "C"
const RULE_D := "D"
const RULE_CD := "CD"
const RANKS := [1,2,3,4,5,6,7,8,9]
const LINES := [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]]

static func other_player(player: int) -> int:
	return DARK if player == LIGHT else LIGHT

static func uses_stack2(rule: String) -> bool:
	return rule == RULE_C or rule == RULE_CD

static func uses_ladder(rule: String) -> bool:
	return rule == RULE_D or rule == RULE_CD

static func create_initial_position(first_player: int = LIGHT) -> Dictionary:
	return {
		"board": [[],[],[],[],[],[],[],[],[]],
		"remaining": {LIGHT: RANKS.duplicate(), DARK: RANKS.duplicate()},
		"turn": first_player, "status": "playing", "winner": null,
		"win_line": null, "moves": 0, "passes": 0
	}

static func clone_position(position: Dictionary) -> Dictionary:
	return position.duplicate(true)

static func top_piece(position: Dictionary, cell: int):
	var stack: Array = position.board[cell]
	return stack[-1] if not stack.is_empty() else null

static func is_legal_move(position: Dictionary, move: Dictionary, rule: String = RULE_C) -> bool:
	if position.is_empty() or position.status != "playing": return false
	if not move.has("player") or move.player != position.turn: return false
	if not move.has("cell") or not move.has("rank"): return false
	var cell := int(move.cell)
	var rank := int(move.rank)
	if cell < 0 or cell > 8: return false
	if not position.remaining.has(move.player) or not position.remaining[move.player].has(rank): return false
	var stack: Array = position.board[cell]
	var top = top_piece(position, cell)
	if top == null: return true
	if top.player == move.player or rank <= int(top.rank): return false
	if uses_stack2(rule) and stack.size() >= 2: return false
	return true

static func get_legal_moves(position: Dictionary, player: int = -1, rule: String = RULE_C) -> Array:
	if position.is_empty() or position.status != "playing": return []
	if player == -1: player = int(position.turn)
	if player != position.turn: return []
	var out: Array = []
	for rank in position.remaining[player]:
		for cell in range(9):
			var move := {"player": player, "rank": rank, "cell": cell}
			if is_legal_move(position, move, rule): out.append(move)
	return out

static func _winning_line(position: Dictionary, player: int, rule: String):
	for line in LINES:
		var ranks: Array = []
		var owned := true
		for cell in line:
			var top = top_piece(position, cell)
			if top == null or top.player != player:
				owned = false
				break
			ranks.append(int(top.rank))
		if not owned: continue
		var ladder := (ranks[0] < ranks[1] and ranks[1] < ranks[2]) or (ranks[0] > ranks[1] and ranks[1] > ranks[2])
		if not uses_ladder(rule) or ladder: return line.duplicate()
	return null

static func get_winner(position: Dictionary, rule: String = RULE_C):
	for player in [LIGHT, DARK]:
		var line = _winning_line(position, player, rule)
		if line != null: return {"player": player, "line": line}
	return null

static func is_terminal(position: Dictionary) -> bool:
	return position.status != "playing"

static func apply_move(position: Dictionary, move: Dictionary, rule: String = RULE_C):
	if not is_legal_move(position, move, rule): return null
	var next := clone_position(position)
	next.remaining[move.player].erase(move.rank)
	next.board[move.cell].append({"player": move.player, "rank": move.rank})
	next.moves += 1
	var win = get_winner(next, rule)
	if win != null:
		next.status = "win"; next.winner = win.player; next.win_line = win.line; next.turn = win.player
		return next
	next.turn = other_player(move.player)
	if not get_legal_moves(next, next.turn, rule).is_empty(): return next
	next.turn = move.player
	if not get_legal_moves(next, next.turn, rule).is_empty():
		next.passes += 1
		return next
	next.status = "draw"; next.winner = null; next.win_line = null
	return next
