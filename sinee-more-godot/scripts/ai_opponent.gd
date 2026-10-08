extends RefCounted

# Deterministic shared D2 opponent. No world-dependent rules or hidden UI.
const LINES: Array[Array] = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]]
const CELL_WEIGHTS := [2, 3, 2, 3, 5, 3, 2, 3, 2]

func legal_moves(board: Array, reserves: Array, player: int, rule: String) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for rank in range(1, 10):
		if not reserves[player - 1][rank - 1]:
			continue
		for cell in range(9):
			var stack: Array = board[cell]
			if not stack.is_empty():
				var top: Dictionary = stack[-1]
				if int(top["player"]) == player or rank <= int(top["rank"]):
					continue
				if (rule == "C" or rule == "CD") and stack.size() >= 2:
					continue
			result.append({"rank": rank, "cell": cell})
	return result

func is_win(board: Array, player: int, rule: String) -> bool:
	for line in LINES:
		var ranks: Array[int] = []
		var owned := true
		for cell in line:
			var stack: Array = board[cell]
			if stack.is_empty() or int(stack[-1]["player"]) != player:
				owned = false
				break
			ranks.append(int(stack[-1]["rank"]))
		if owned and (rule == "C" or (ranks[0] < ranks[1] and ranks[1] < ranks[2]) or (ranks[0] > ranks[1] and ranks[1] > ranks[2])):
			return true
	return false

func _after_move(board: Array, reserves: Array, player: int, move: Dictionary) -> Dictionary:
	var next_board: Array = board.duplicate(true)
	var next_reserves: Array = reserves.duplicate(true)
	next_board[int(move["cell"])].append({"player": player, "rank": int(move["rank"])})
	next_reserves[player - 1][int(move["rank"]) - 1] = false
	return {"board": next_board, "reserves": next_reserves}

func _winning_replies(board: Array, reserves: Array, player: int, rule: String) -> int:
	var count := 0
	for move in legal_moves(board, reserves, player, rule):
		var next_board: Array = board.duplicate(true)
		next_board[int(move["cell"])].append({"player": player, "rank": int(move["rank"])})
		if is_win(next_board, player, rule):
			count += 1
	return count

func choose_move(board: Array, reserves: Array, player: int, rule: String, difficulty: int, persona: int) -> Dictionary:
	# difficulty 1=easy, 2=normal, 3=hard; persona 0=balanced, 1=aggressive, 2=defensive.
	var candidates := legal_moves(board, reserves, player, rule)
	if candidates.is_empty():
		return {}
	var enemy := 2 if player == 1 else 1
	var best: Dictionary = {}
	var best_score := -INF
	for move in candidates:
		var rank: int = move["rank"]
		var cell: int = move["cell"]
		var covered: bool = not board[cell].is_empty()
		var next: Dictionary = _after_move(board, reserves, player, move)
		var next_board: Array = next["board"]
		var next_reserves: Array = next["reserves"]
		var win := is_win(next_board, player, rule)
		var score := float(CELL_WEIGHTS[cell] * 3) + float(10 - rank) * 0.65
		if covered:
			score += 9.0
		if persona == 1:
			score += 3.0 if covered else 0.0
		if persona == 2:
			score += 2.0 * CELL_WEIGHTS[cell]
		if difficulty == 1:
			# Deliberately simple but always legal and reproducible.
			score += float((cell * 7 + rank * 3) % 11) * 0.4
		else:
			var enemy_wins := _winning_replies(next_board, next_reserves, enemy, rule)
			score -= float(enemy_wins) * (22000.0 if difficulty == 3 else 12000.0)
			if difficulty == 3:
				var own_threats := _winning_replies(next_board, next_reserves, player, rule)
				score += float(own_threats) * (90.0 if persona == 2 else 200.0)
				if persona == 2:
					score -= float(enemy_wins) * 6000.0
		if win and difficulty >= 2:
			score += 1000000.0
		if score > best_score:
			best_score = score
			best = move
	return best

func self_test() -> bool:
	var board: Array = [[],[],[],[],[],[],[],[],[]]
	var reserves: Array = [[true,true,true,true,true,true,true,true,true],[true,true,true,true,true,true,true,true,true]]
	for difficulty in [1,2,3]:
		for persona in [0,1,2]:
			var move := choose_move(board, reserves, 2, "CD", difficulty, persona)
			assert(not move.is_empty() and move in legal_moves(board, reserves, 2, "CD"))
	# Forced immediate win must be taken on normal/hard.
	board[0] = [{"player": 2, "rank": 1}]
	board[1] = [{"player": 2, "rank": 2}]
	reserves[1][0] = false
	reserves[1][1] = false
	for difficulty in [2,3]:
		var move := choose_move(board, reserves, 2, "CD", difficulty, 0)
		assert(int(move["cell"]) == 2 and int(move["rank"]) > 2)
		var next := _after_move(board, reserves, 2, move)
		assert(is_win(next["board"], 2, "CD"))
	# A rank-9 cover is forbidden if the cell already has two pieces.
	board[2] = [{"player": 1, "rank": 2}, {"player": 2, "rank": 4}]
	assert(not {"rank": 9, "cell": 2} in legal_moves(board, reserves, 1, "CD"))
	return true
