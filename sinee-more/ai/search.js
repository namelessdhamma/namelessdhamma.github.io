import { getLegalMoves, applyMove } from './rules.js';
import { canonicalize, rawPositionKey, transformMove, inverseTransformMove } from './symmetry.js';

export const TT_EXACT = 'EXACT';
export const TT_LOWER = 'LOWER_BOUND';
export const TT_UPPER = 'UPPER_BOUND';

const TIMEOUT = Symbol('SEARCH_TIMEOUT');

export class TranspositionTable {
  constructor() {
    this.map = new Map();
  }
  get(key) { return this.map.get(key); }
  set(key, entry) { this.map.set(key, entry); }
  clear() { this.map.clear(); }
  get size() { return this.map.size; }
}

export function makeSearchKey(position, rule, rootPlayer = position.turn) {
  return `${canonicalize(position, rule).key}|root:${rootPlayer}`;
}

function compareMoves(a, b) {
  return a.cell - b.cell || a.rank - b.rank || a.player.localeCompare(b.player);
}

function sameMove(a, b) {
  return !!a && !!b &&
    a.player === b.player && a.rank === b.rank && a.cell === b.cell;
}

function prioritize(moves, preferred) {
  if (!preferred) return moves;
  const index = moves.findIndex(move => sameMove(move, preferred));
  if (index > 0) {
    const [move] = moves.splice(index, 1);
    moves.unshift(move);
  }
  return moves;
}

function classifyBound(score, alphaOriginal, betaOriginal) {
  if (score <= alphaOriginal) return TT_UPPER;
  if (score >= betaOriginal) return TT_LOWER;
  return TT_EXACT;
}

function checkDeadline(ctx) {
  if (ctx.deadline !== Infinity && ctx.now() >= ctx.deadline) throw TIMEOUT;
}

function node(position, depth, alpha, beta, ctx, ply = 0) {
  checkDeadline(ctx);
  ctx.nodes += 1;
  if (depth <= 0 || position.status !== 'playing') {
    return { score: ctx.evaluate(position, ctx.rootPlayer), move: null };
  }

  const canonical = ctx.useSymmetry
    ? canonicalize(position, ctx.rule)
    : { key: rawPositionKey(position, ctx.rule), transformId: 0 };
  const key = `${canonical.key}|root:${ctx.rootPlayer}`;
  const alphaOriginal = alpha;
  const betaOriginal = beta;
  let entry = null;
  let entryLocalMove = null;

  if (ctx.useTable) {
    entry = ctx.table.get(key);
    if (entry?.move) {
      entryLocalMove = ctx.useSymmetry
        ? inverseTransformMove(entry.move, canonical.transformId)
        : entry.move;
    }
    if (entry && entry.depth >= depth) {
      ctx.ttHits += 1;
      if (entry.flag === TT_EXACT) return { score: entry.score, move: entryLocalMove };
      if (entry.flag === TT_LOWER) alpha = Math.max(alpha, entry.score);
      if (entry.flag === TT_UPPER) beta = Math.min(beta, entry.score);
      if (alpha >= beta) return { score: entry.score, move: entryLocalMove, bound: entry.flag };
    }
  }

  const maximizing = position.turn === ctx.rootPlayer;
  let bestScore = maximizing ? -Infinity : Infinity;
  let bestMove = null;
  let moves = ply === 0 && ctx.rootCandidates
    ? [...ctx.rootCandidates]
    : getLegalMoves(position, position.turn, ctx.rule);
  moves.sort(compareMoves);
  if (ply === 0) prioritize(moves, ctx.preferredMove);
  else if (entryLocalMove) prioritize(moves, entryLocalMove);

  if (!moves.length) {
    return { score: ctx.evaluate(position, ctx.rootPlayer), move: null };
  }

  for (const move of moves) {
    const next = applyMove(position, move, ctx.rule);
    if (!next) continue;
    const child = node(next, depth - 1, alpha, beta, ctx, ply + 1);
    const score = child.score;

    if (ply === 0) ctx.rootScores.push({ move, score });

    if (
      bestMove === null ||
      (maximizing && score > bestScore) ||
      (!maximizing && score < bestScore)
    ) {
      bestScore = score;
      bestMove = move;
    }

    if (maximizing) alpha = Math.max(alpha, bestScore);
    else beta = Math.min(beta, bestScore);
    if (alpha >= beta) break;
  }

  if (ctx.useTable && bestMove) {
    ctx.table.set(key, {
      depth,
      score: bestScore,
      move: ctx.useSymmetry ? transformMove(bestMove, canonical.transformId) : bestMove,
      flag: classifyBound(bestScore, alphaOriginal, betaOriginal)
    });
  }

  return { score: bestScore, move: bestMove };
}

export function searchFixedDepth(position, {
  rule,
  rootPlayer = position.turn,
  depth,
  evaluate,
  useTable = true,
  table = new TranspositionTable(),
  alpha = -Infinity,
  beta = Infinity,
  key = makeSearchKey,
  useSymmetry = true,
  now = () => performance.now(),
  deadline = Infinity,
  preferredMove = null,
  rootCandidates = null
}) {
  const ctx = {
    rule, rootPlayer, evaluate, useTable, table, key, useSymmetry,
    now, deadline, preferredMove, rootCandidates,
    nodes: 0, ttHits: 0, rootScores: []
  };
  const result = node(position, depth, alpha, beta, ctx);
  return {
    ...result,
    nodes: ctx.nodes,
    ttHits: ctx.ttHits,
    completedDepth: depth,
    rootScores: ctx.rootScores,
    table
  };
}

export function searchIterative(position, {
  rule,
  rootPlayer = position.turn,
  evaluate,
  timeBudgetMs,
  maxDepth,
  now = () => performance.now(),
  useTable = true,
  table = new TranspositionTable(),
  key = makeSearchKey,
  useSymmetry = true,
  rootCandidates = null
}) {
  const legal = rootCandidates?.length
    ? [...rootCandidates].sort(compareMoves)
    : getLegalMoves(position, position.turn, rule).sort(compareMoves);
  const started = now();
  const deadline = started + Math.max(0, timeBudgetMs);
  const fallback = legal[0] ?? null;
  let best = {
    score: evaluate(position, rootPlayer),
    move: fallback,
    nodes: 0,
    ttHits: 0,
    completedDepth: 0,
    rootScores: fallback ? [{ move: fallback, score: evaluate(position, rootPlayer) }] : [],
    principalVariation: fallback ? [fallback] : [],
    table
  };
  let totalNodes = 0;
  let totalHits = 0;

  for (let depth = 1; depth <= maxDepth; depth += 1) {
    try {
      const current = searchFixedDepth(position, {
        rule,
        rootPlayer,
        depth,
        evaluate,
        useTable,
        table,
        key,
        useSymmetry,
        now,
        deadline,
        preferredMove: best.move,
        rootCandidates: legal
      });
      totalNodes += current.nodes;
      totalHits += current.ttHits;
      best = {
        ...current,
        nodes: totalNodes,
        ttHits: totalHits,
        principalVariation: current.move ? [current.move] : []
      };
    } catch (error) {
      if (error !== TIMEOUT) throw error;
      return {
        ...best,
        timedOut: true,
        elapsedMs: now() - started
      };
    }
  }

  return {
    ...best,
    timedOut: false,
    elapsedMs: now() - started
  };
}
