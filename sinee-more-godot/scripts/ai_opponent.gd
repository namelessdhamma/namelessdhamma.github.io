extends RefCounted

# Deterministic shared D2 opponent. No world-dependent rules or hidden UI.
const LINES: Array[Array] = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]]
const CELL_WEIGHTS := [2, 3, 2, 3, 5, 3, 2, 3, 2]

# One cover predicate for move enumeration and tactical threat counting.
# Both paths must agree about the C/CD two-piece stack ceiling.
func _legal_destination(board: Array, player: int, rank: int, cell: int, rule: String) -> bool:
	var stack: Array = board[cell]
	if stack.is_empty():
		return true
	var top: Dictionary = stack[-1]
	return int(top["player"]) != player and rank > int(top["rank"]) and not (
		(rule == "C" or rule == "CD") and stack.size() >= 2)

func legal_moves(board: Array, reserves: Array, player: int, rule: String) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for rank in range(1, 10):
		if not reserves[player - 1][rank - 1]:
			continue
		for cell in range(9):
			if _legal_destination(board, player, rank, cell, rule):
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

# AI lookahead can examine up to 81 legal candidates in a single phone frame.
# Clone only the two rows that this hypothetical placement mutates. The
# remaining board stacks and the other player's reserve are READ-ONLY during
# evaluation, so copying all 11 nested arrays per candidate wastes allocations
# and may stall touch feedback on low-end Android hardware. This is copy-on-write,
# never an in-place mutation of the live match.
func _after_move(board: Array, reserves: Array, player: int, move: Dictionary) -> Dictionary:
	var cell: int = int(move["cell"])
	var rank: int = int(move["rank"])
	var next_board: Array = board.duplicate()
	var next_reserves: Array = reserves.duplicate()
	next_board[cell] = board[cell].duplicate()
	next_reserves[player - 1] = reserves[player - 1].duplicate()
	next_board[cell].append({"player": player, "rank": rank})
	next_reserves[player - 1][rank - 1] = false
	return {"board": next_board, "reserves": next_reserves}

# A winning reply can only create a new line through its destination cell.
# Inspect that hypothetical top piece without deep-copying all nine stacks.
# If a line was already complete before this hypothetical move, every
# legal reply still counts as winning; _winning_replies handles that case.
func _wins_after_placement(board: Array, player: int, rule: String, destination: int, placed_rank: int) -> bool:
	for line in LINES:
		if not line.has(destination):
			continue
		var ranks: Array[int] = []
		var owned := true
		for cell in line:
			if cell == destination:
				ranks.append(placed_rank)
				continue
			var stack: Array = board[cell]
			if stack.is_empty() or int(stack[-1]["player"]) != player:
				owned = false
				break
			ranks.append(int(stack[-1]["rank"]))
		if owned and (rule == "C" or
				(ranks[0] < ranks[1] and ranks[1] < ranks[2]) or
				(ranks[0] > ranks[1] and ranks[1] > ranks[2])):
			return true
	return false

func _wins_after_legal_move(board: Array, player: int, rule: String, move: Dictionary) -> bool:
	return _wins_after_placement(board, player, rule, int(move["cell"]), int(move["rank"]))

# The AI evaluates this for each candidate position. Do not allocate up to 81
# move dictionaries on EVERY lookahead, or clone 9 stacks per reply. Count
# legal winning destinations directly; preserve pre-existing-win semantics.
func _winning_replies(board: Array, reserves: Array, player: int, rule: String) -> int:
	var already_won := is_win(board, player, rule)
	var count := 0
	for rank in range(1, 10):
		if not reserves[player - 1][rank - 1]:
			continue
		for cell in range(9):
			if not _legal_destination(board, player, rank, cell, rule):
				continue
			if already_won or _wins_after_placement(board, player, rule, cell, rank):
				count += 1
	return count

# Deliberately slower independent oracle, used ONLY in headless self_test.
# It recomputes each hypothetical board via the original deep-copy route.
func _reference_winning_replies(board: Array, reserves: Array, player: int, rule: String) -> int:
	var count := 0
	for move in legal_moves(board, reserves, player, rule):
		var after: Dictionary = _after_move(board, reserves, player, move)
		if is_win(after["board"], player, rule):
			count += 1
	return count

func choose_move(board: Array, reserves: Array, player: int, rule: String, difficulty: int, persona: int) -> Dictionary:
	# difficulty 1=easy, 2=normal, 3=hard; persona 0=balanced, 1=aggressive, 2=defensive.
	var candidates := legal_moves(board, reserves, player, rule)
	if candidates.is_empty():
		return {}
	# A completed line ends the round immediately. Never rank an actual win
	# below a speculative opponent reply (the opponent never gets that turn).
	# Inspect only destination-dependent lines before expensive lookahead.
	# Easy retains its deliberately simpler scoring policy.
	if difficulty >= 2:
		for move in candidates:
			if _wins_after_legal_move(board, player, rule, move):
				return move
	var enemy := 2 if player == 1 else 1
	var best: Dictionary = {}
	var best_score := -INF
	# The original easy mode used almost the same center/cover policy as the
	# tactical levels and defeated a seeded novice in 70/72 matches. Vary its
	# choices deterministically with the LIVE move count, without RNG or a
	# second rules engine. Normal/hard scoring remains byte-for-byte intact.
	var spent_count := 0
	if difficulty == 1:
		for reserve_row in reserves:
			for available in reserve_row:
				if not available:
					spent_count += 1
	# A synthetic already-won board is not a playable turn, but retain the
	# old is_win(next_board) behavior without recomputing it per candidate.
	var easy_already_won := is_win(board, player, rule) if difficulty == 1 else false
	# Normal/Hard returned above for ANY newly completed line. Their
	# remaining candidates cannot create a new win; only a pre-existing
	# (synthetic) winning line could make is_win(next_board) true. A legal
	# placement never covers its OWN top piece, so it cannot erase that line.
	# Compute this invariant once instead of scanning all 8 lines for every
	# candidate on the real-time mobile AI path. Scoring/tie order is unchanged.
	var tactical_already_won := is_win(board, player, rule) if difficulty >= 2 else false
	for move in candidates:
		var rank: int = move["rank"]
		var cell: int = move["cell"]
		var covered: bool = not board[cell].is_empty()
		var score := 0.0
		var win := false
		if difficulty == 1:
			# Easy has no opponent lookahead. The former shared preamble
			# cloned board+reserves for EVERY candidate just to test a win.
			# Use the same destination-aware win predicate instead: no
			# hypothetical arrays, no live-state mutation, same scoring.
			# Preserve the previous evaluator's already-won semantics for
			# synthetic fixtures (normal matches stop on the winning move).
			win = easy_already_won or _wins_after_legal_move(board, player, rule, move)
			# Easy should be genuinely approachable, not a nearly-hard AI with
			# a cosmetic label. Favor variety and lower-cost pieces over optimal
			# center/cover pressure; sometimes notice an immediate win, but do
			# not calculate opponent replies. Board state alone seeds variation.
			score = float(CELL_WEIGHTS[cell]) * 0.4 + float(10 - rank) * 0.5
			score -= 3.0 if covered else 0.0
			score += float((cell * 7 + rank * 3 + spent_count * 5) % 17) * 2.0
			if persona == 1 and covered:
				score += 2.0 + float(rank) * 0.2
			elif persona == 2:
				score += float(CELL_WEIGHTS[cell] * (rank - 1)) * 0.04
			if win:
				score += 2.0
		else:
			# Only Normal/Hard need the copy-on-write hypothetical state.
			# Keep their v141 tactical/persona logic byte-for-byte intact.
			var next: Dictionary = _after_move(board, reserves, player, move)
			var next_board: Array = next["board"]
			var next_reserves: Array = next["reserves"]
			win = tactical_already_won
			score = float(CELL_WEIGHTS[cell] * 3) + float(10 - rank) * 0.65
			if covered:
				score += 9.0
			# The established v141 normal/hard persona contract is unchanged.
			if persona == 1 and covered:
				score += 18.0 + float(rank) * 0.9
			elif persona == 2:
				score += float(CELL_WEIGHTS[cell] * (rank - 1)) * 0.15
			var enemy_wins := _winning_replies(next_board, next_reserves, enemy, rule)
			score -= float(enemy_wins) * (22000.0 if difficulty == 3 else 12000.0)
			if difficulty == 3:
				var own_threats := _winning_replies(next_board, next_reserves, player, rule)
				score += float(own_threats) * (90.0 if persona == 2 else 200.0)
				if persona == 2:
					score -= float(enemy_wins) * 6000.0
			if win:
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
	for rule in ["C", "D", "CD"]:
		for difficulty in [2,3]:
			for persona in [0,1,2]:
				var move := choose_move(board, reserves, 2, rule, difficulty, persona)
				assert(int(move["cell"]) == 2 and int(move["rank"]) > 2)
				var next := _after_move(board, reserves, 2, move)
				assert(is_win(next["board"], 2, rule))
	# One real mid-game C position distinguishes all three personas.
	# This is a bounded native behavior check, not a visual parity claim.
	var persona_board: Array = [
		[{"player": 2, "rank": 6}], [{"player": 1, "rank": 6}], [],
		[{"player": 1, "rank": 7}], [], [], [], [], []]
	var persona_reserves: Array = [
		[true, true, true, true, true, false, false, true, true],
		[true, true, true, true, true, false, true, true, true]]
	var persona_moves: Array[Dictionary] = []
	for persona_id in [0, 1, 2]:
		var persona_move := choose_move(persona_board, persona_reserves, 2, "C", 3, persona_id)
		assert(persona_move in legal_moves(persona_board, persona_reserves, 2, "C"))
		persona_moves.append(persona_move)
	assert(persona_moves[0] == {"rank": 1, "cell": 4})
	assert(persona_moves[1] == {"rank": 9, "cell": 1})
	assert(persona_moves[2] == {"rank": 7, "cell": 1})
	assert(persona_board[0] == [{"player": 2, "rank": 6}],
		"Persona lookahead modified live board")
	# A rank-9 cover is forbidden if the cell already has two pieces.
	board[2] = [{"player": 1, "rank": 2}, {"player": 2, "rank": 4}]
	assert(not {"rank": 9, "cell": 2} in legal_moves(board, reserves, 1, "CD"))
	# Fast no-allocation threat count must match full board simulation in
	# every mode, both players, already-won and stack-ceiling positions.
	var boards: Array = [
		[[],[],[],[],[],[],[],[],[]],
		board.duplicate(true),
		[[{"player": 1, "rank": 1}], [{"player": 1, "rank": 2}], [],
			[{"player": 2, "rank": 1}], [], [], [], [], []],
		[[{"player": 1, "rank": 2}, {"player": 2, "rank": 5}],
			[{"player": 1, "rank": 3}], [], [], [], [], [], [], []],
	]
	for scenario in boards:
		for mode in ["C", "D", "CD"]:
			for active_player in [1, 2]:
				var reference := _reference_winning_replies(scenario, reserves, active_player, mode)
				assert(_winning_replies(scenario, reserves, active_player, mode) == reference,
					"Optimized AI threat count differs from full simulation")
	# v146 Easy must return exactly the same win bonus as its old
	# full-copy evaluator. This native fixture executes inside Godot when
	# the authorized runner becomes available; the independent Python
	# regression covers additional reachable game states offline.
	for scenario in boards:
		for mode in ["C", "D", "CD"]:
			for active_player in [1, 2]:
				var already_won := is_win(scenario, active_player, mode)
				for candidate in legal_moves(scenario, reserves, active_player, mode):
					var after_candidate: Dictionary = _after_move(scenario, reserves, active_player, candidate)
					var old_win := is_win(after_candidate["board"], active_player, mode)
					var fast_win := already_won or _wins_after_legal_move(scenario, active_player, mode, candidate)
					assert(old_win == fast_win, "Easy no-copy win score diverged from v145")
	# Native copy-on-write contract: a hypothetical move must be value-identical
	# to the former deep-copy evaluator and must NEVER spend a real reserve or
	# mutate a live board stack. Exercise both players and all three rule modes.
	for scenario in boards:
		for mode in ["C", "D", "CD"]:
			for active_player in [1, 2]:
				for candidate in legal_moves(scenario, reserves, active_player, mode):
					var source_board: Array = scenario.duplicate(true)
					var source_reserves: Array = reserves.duplicate(true)
					var result: Dictionary = _after_move(scenario, reserves, active_player, candidate)
					var expected_board: Array = source_board.duplicate(true)
					var expected_reserves: Array = source_reserves.duplicate(true)
					expected_board[int(candidate["cell"])].append({"player": active_player, "rank": int(candidate["rank"])})
					expected_reserves[active_player - 1][int(candidate["rank"]) - 1] = false
					assert(result["board"] == expected_board and result["reserves"] == expected_reserves,
						"AI copy-on-write diverged from deep-copy oracle")
					assert(scenario == source_board and reserves == source_reserves,
						"AI hypothetical move mutated live board or reserve")
					# Mutating the copied destination again must not affect its source.
					result["board"][int(candidate["cell"])].append({"player": active_player, "rank": 10})
					assert(scenario == source_board, "AI target stack was aliased to live state")
					result["reserves"][active_player - 1][int(candidate["rank"]) - 1] = true
					assert(reserves == source_reserves, "AI active reserve was aliased to live state")
	# All ranks spent: no legal reply even if a line was already won.
	var spent: Array = [[false,false,false,false,false,false,false,false,false],
		[false,false,false,false,false,false,false,false,false]]
	assert(_winning_replies(boards[2], spent, 1, "C") == 0)
	return true
