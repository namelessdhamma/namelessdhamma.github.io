import { getLegalMoves, applyMove } from './rules.js';

export const TT_EXACT = 'EXACT';
export const TT_LOWER = 'LOWER_BOUND';
export const TT_UPPER = 'UPPER_BOUND';

export class TranspositionTable {
  constructor() {
    this.map = new Map();
  }
  get(key) { return this.map.get(key); }
  set(key, entry) { this.map.set(key, entry); }
  clear() { this.map.clear(); }
  get size() { return this.map.size; }
}

export function makeSearchKey(position, rule) {
  const board = position.board.map(stack =>
    stack.map(piece => `${piece.player[0]}${piece.rank}`).join('.')
  ).join('/');
  return [
    rule,
    position.turn,
    position.status,
    position.winner ?? '-',
    board,
    position.remaining.light.join(','),
    position.remaining.dark.join(',')
  ].join('|');
}

function compareMoves(a, b) {
  return a.cell - b.cell || a.rank - b.rank || a.player.localeCompare(b.player);
}

function classifyBound(score, alphaOriginal, betaOriginal) {
  if (score <= alphaOriginal) return TT_UPPER;
  if (score >= betaOriginal) return TT_LOWER;
  return TT_EXACT;
}

function node(position, depth, alpha, beta, ctx) {
  ctx.nodes += 1;
  if (depth <= 0 || position.status !== 'playing') {
    return { score: ctx.evaluate(position, ctx.rootPlayer), move: null };
  }

  const key = ctx.key(position, ctx.rule);
  const alphaOriginal = alpha;
  const betaOriginal = beta;
  let entry = null;

  if (ctx.useTable) {
    entry = ctx.table.get(key);
    if (entry && entry.depth >= depth) {
      ctx.ttHits += 1;
      if (entry.flag === TT_EXACT) return { score: entry.score, move: entry.move };
      if (entry.flag === TT_LOWER) alpha = Math.max(alpha, entry.score);
      if (entry.flag === TT_UPPER) beta = Math.min(beta, entry.score);
      if (alpha >= beta) return { score: entry.score, move: entry.move, bound: entry.flag };
    }
  }

  const maximizing = position.turn === ctx.rootPlayer;
  let bestScore = maximizing ? -Infinity : Infinity;
  let bestMove = null;
  const moves = getLegalMoves(position, position.turn, ctx.rule).sort(compareMoves);

  if (!moves.length) {
    return { score: ctx.evaluate(position, ctx.rootPlayer), move: null };
  }

  for (const move of moves) {
    const next = applyMove(position, move, ctx.rule);
    const child = node(next, depth - 1, alpha, beta, ctx);
    const score = child.score;

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

  if (ctx.useTable) {
    ctx.table.set(key, {
      depth,
      score: bestScore,
      move: bestMove,
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
  key = makeSearchKey
}) {
  const ctx = {
    rule, rootPlayer, evaluate, useTable, table, key,
    nodes: 0, ttHits: 0
  };
  const result = node(position, depth, alpha, beta, ctx);
  return {
    ...result,
    nodes: ctx.nodes,
    ttHits: ctx.ttHits,
    completedDepth: depth,
    table
  };
}
