class_name BlueSeaSearch
extends RefCounted

const INF := 1.0e30

static func _same_move(a, b) -> bool:
	return a != null and b != null and int(a.player) == int(b.player) and int(a.rank) == int(b.rank) and int(a.cell) == int(b.cell)

static func _sort_moves(moves: Array) -> Array:
	var out := moves.duplicate(true)
	out.sort_custom(func(a, b):
		if int(a.cell) != int(b.cell): return int(a.cell) < int(b.cell)
		return int(a.rank) < int(b.rank)
	)
	return out

static func _prioritize(moves: Array, preferred) -> Array:
	if preferred == null: return moves
	for i in range(moves.size()):
		if _same_move(moves[i], preferred):
			if i > 0:
				var move = moves.pop_at(i)
				moves.push_front(move)
			break
	return moves

static func _node(position: Dictionary, depth: int, alpha: float, beta: float, ctx: Dictionary, ply: int = 0) -> Dictionary:
	ctx.nodes += 1
	if depth <= 0 or BlueSeaRules.is_terminal(position):
		return {"score": BlueSeaEvaluation.evaluate_position(position, ctx.root_player, ctx.rule, ctx.profile), "move": null}
	var maximizing := int(position.turn) == int(ctx.root_player)
	var best_score := -INF if maximizing else INF
	var best_move = null
	var moves: Array
	if ply == 0 and not ctx.root_candidates.is_empty():
		moves = ctx.root_candidates.duplicate(true)
	else:
		moves = _sort_moves(BlueSeaRules.get_legal_moves(position, int(position.turn), ctx.rule))
	if ply == 0:
		moves = _prioritize(moves, ctx.preferred_move)
	if moves.is_empty():
		return {"score": BlueSeaEvaluation.evaluate_position(position, ctx.root_player, ctx.rule, ctx.profile), "move": null}
	for move in moves:
		var next = BlueSeaRules.apply_move(position, move, ctx.rule)
		if next == null: continue
		var child := _node(next, depth - 1, alpha, beta, ctx, ply + 1)
		var score := float(child.score)
		if ply == 0: ctx.root_scores.append({"move": move.duplicate(true), "score": score})
		if best_move == null or (maximizing and score > best_score) or ((not maximizing) and score < best_score):
			best_score = score
			best_move = move.duplicate(true)
		if maximizing: alpha = max(alpha, best_score)
		else: beta = min(beta, best_score)
		if alpha >= beta: break
	return {"score": best_score, "move": best_move}

static func search_fixed_depth(position: Dictionary, rule: String, depth: int, root_player: int = -1, profile: Dictionary = BlueSeaEvaluation.BASE_PROFILE, preferred_move = null, root_candidates: Array = []) -> Dictionary:
	if root_player == -1: root_player = int(position.turn)
	var ctx := {
		"rule": rule, "root_player": root_player, "profile": profile,
		"preferred_move": preferred_move, "root_candidates": root_candidates.duplicate(true),
		"nodes": 0, "root_scores": []
	}
	var result := _node(position, max(0, depth), -INF, INF, ctx)
	result.nodes = ctx.nodes
	result.completed_depth = depth
	result.root_scores = ctx.root_scores
	return result

static func search_iterative(position: Dictionary, rule: String, max_depth: int, root_player: int = -1, profile: Dictionary = BlueSeaEvaluation.BASE_PROFILE, root_candidates: Array = []) -> Dictionary:
	if root_player == -1: root_player = int(position.turn)
	var legal := root_candidates.duplicate(true) if not root_candidates.is_empty() else _sort_moves(BlueSeaRules.get_legal_moves(position, int(position.turn), rule))
	var fallback = null if legal.is_empty() else legal[0].duplicate(true)
	var best := {
		"score": BlueSeaEvaluation.evaluate_position(position, root_player, rule, profile),
		"move": fallback, "nodes": 0, "completed_depth": 0,
		"root_scores": [], "principal_variation": [] if fallback == null else [fallback]
	}
	var total_nodes := 0
	for depth in range(1, max(1, max_depth) + 1):
		var current := search_fixed_depth(position, rule, depth, root_player, profile, best.move if int(best.completed_depth) > 0 else null, legal)
		total_nodes += int(current.nodes)
		best = current
		best.nodes = total_nodes
		best.principal_variation = [] if best.move == null else [best.move]
	return best
