class_name BlueSeaGuardian
extends RefCounted

static func same_move(a, b) -> bool:
	return a != null and b != null and int(a.player) == int(b.player) and int(a.rank) == int(b.rank) and int(a.cell) == int(b.cell)

static func _probe_for(position: Dictionary, player: int) -> Dictionary:
	if int(position.turn) == player: return position
	var probe := BlueSeaRules.clone_position(position)
	probe.turn = player
	return probe

static func _visible_top_count(position: Dictionary, player: int) -> int:
	var count := 0
	for cell in range(9):
		var top = BlueSeaRules.top_piece(position, cell)
		if top != null and int(top.player) == player: count += 1
	return count

static func _immediate_threat_lines(position: Dictionary, player: int) -> Array:
	if position.is_empty() or position.status != "playing": return []
	var out: Array = []
	for line in BlueSeaRules.LINES:
		var owned := 0
		var target := -1
		for cell in line:
			var top = BlueSeaRules.top_piece(position, cell)
			if top != null and int(top.player) == player: owned += 1
			else: target = int(cell)
		if owned == 2 and target >= 0:
			out.append({"line": line.duplicate(), "target": target})
	return out

static func get_immediate_threat_cells(position: Dictionary, player: int, _rule: String) -> Array:
	var seen := {}
	for item in _immediate_threat_lines(position, player): seen[int(item.target)] = true
	var cells: Array = seen.keys()
	cells.sort()
	return cells

static func _is_winning_visible_line(position: Dictionary, player: int, rule: String, move: Dictionary) -> bool:
	for line in BlueSeaRules.LINES:
		if not line.has(int(move.cell)): continue
		var ranks: Array = []
		var owned := true
		for cell in line:
			if int(cell) == int(move.cell):
				ranks.append(int(move.rank))
				continue
			var top = BlueSeaRules.top_piece(position, int(cell))
			if top == null or int(top.player) != player:
				owned = false
				break
			ranks.append(int(top.rank))
		if not owned: continue
		if not BlueSeaRules.uses_ladder(rule): return true
		if (ranks[0] < ranks[1] and ranks[1] < ranks[2]) or (ranks[0] > ranks[1] and ranks[1] > ranks[2]):
			return true
	return false

static func get_immediate_wins(position: Dictionary, player: int, rule: String) -> Array:
	if position.is_empty() or position.status != "playing": return []
	var probe := _probe_for(position, player)
	var cells := get_immediate_threat_cells(probe, player, rule)
	var wins: Array = []
	for rank in probe.remaining[player]:
		for cell in cells:
			var move := {"player": player, "rank": int(rank), "cell": int(cell)}
			if BlueSeaRules.is_legal_move(probe, move, rule) and _is_winning_visible_line(probe, player, rule, move):
				wins.append(move)
	return wins

static func get_safe_moves(position: Dictionary, player: int, rule: String, legal_moves = null, known_own_wins = null) -> Array:
	if position.is_empty() or position.status != "playing": return []
	var probe := _probe_for(position, player)
	var legal: Array = BlueSeaRules.get_legal_moves(probe, player, rule) if legal_moves == null else legal_moves
	var opponent := BlueSeaRules.other_player(player)
	if _visible_top_count(probe, opponent) < 2: return legal
	var opponent_wins := get_immediate_wins(probe, opponent, rule)
	if opponent_wins.is_empty(): return legal
	var own_wins: Array = get_immediate_wins(probe, player, rule) if known_own_wins == null else known_own_wins
	var safe: Array = []
	for move in legal:
		var is_own_win := false
		for win in own_wins:
			if same_move(move, win):
				is_own_win = true
				break
		if is_own_win:
			safe.append(move)
			continue
		var next = BlueSeaRules.apply_move(probe, move, rule)
		if next == null: continue
		if next.status != "playing" or int(next.turn) != opponent or get_immediate_wins(next, opponent, rule).is_empty():
			safe.append(move)
	return safe

static func get_tactical_candidates(position: Dictionary, player: int = -1, rule: String = BlueSeaRules.RULE_C) -> Dictionary:
	if player == -1: player = int(position.turn)
	var probe := _probe_for(position, player)
	var legal := BlueSeaRules.get_legal_moves(probe, player, rule)
	if legal.is_empty(): return {"tier": "ALL_LEGAL", "moves": [], "forcing_skipped": true}
	var wins := get_immediate_wins(probe, player, rule)
	if not wins.is_empty(): return {"tier": "WIN_NOW", "moves": wins, "forcing_skipped": true}
	var safe := get_safe_moves(probe, player, rule, legal, wins)
	if not safe.is_empty() and safe.size() < legal.size():
		return {"tier": "MUST_DEFEND", "moves": safe, "forcing_skipped": true}
	if not safe.is_empty(): return {"tier": "SAFE", "moves": safe, "forcing_skipped": true}
	return {"tier": "ALL_LEGAL", "moves": legal, "forcing_skipped": true}
