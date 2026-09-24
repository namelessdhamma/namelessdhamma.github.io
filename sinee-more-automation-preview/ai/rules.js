import {
  LIGHT, DARK, RULE_C, RANKS, LINES, otherPlayer, usesStack2, usesLadder
} from './constants.js';

export function createInitialPosition(firstPlayer = LIGHT) {
  return {
    board: Array.from({ length: 9 }, () => []),
    remaining: {
      [LIGHT]: [...RANKS],
      [DARK]: [...RANKS]
    },
    turn: firstPlayer,
    status: 'playing',
    winner: null,
    winLine: null,
    moves: 0,
    passes: 0
  };
}

export function clonePosition(position) {
  return {
    ...position,
    board: position.board.map(stack => stack.map(piece => ({ ...piece }))),
    remaining: {
      [LIGHT]: [...position.remaining[LIGHT]],
      [DARK]: [...position.remaining[DARK]]
    },
    winLine: position.winLine ? [...position.winLine] : null
  };
}

export function topPiece(position, cell) {
  const stack = position.board[cell];
  return stack && stack.length ? stack[stack.length - 1] : null;
}

export function isLegalMove(position, move, rule = RULE_C) {
  if (!position || position.status !== 'playing') return false;
  if (!move || move.player !== position.turn) return false;
  if (!Number.isInteger(move.cell) || move.cell < 0 || move.cell > 8) return false;
  if (!Number.isInteger(move.rank) || !position.remaining[move.player]?.includes(move.rank)) return false;

  const stack = position.board[move.cell];
  const top = topPiece(position, move.cell);
  if (!top) return true;
  if (top.player === move.player || move.rank <= top.rank) return false;
  if (usesStack2(rule) && stack.length >= 2) return false;
  return true;
}

export function getLegalMoves(position, player = position.turn, rule = RULE_C) {
  if (!position || position.status !== 'playing' || player !== position.turn) return [];
  const out = [];
  for (const rank of position.remaining[player]) {
    for (let cell = 0; cell < 9; cell += 1) {
      const move = { player, rank, cell };
      if (isLegalMove(position, move, rule)) out.push(move);
    }
  }
  return out;
}

function winningLine(position, player, rule) {
  for (const line of LINES) {
    const ranks = [];
    let owned = true;
    for (const cell of line) {
      const top = topPiece(position, cell);
      if (!top || top.player !== player) {
        owned = false;
        break;
      }
      ranks.push(top.rank);
    }
    if (!owned) continue;
    const ladder =
      (ranks[0] < ranks[1] && ranks[1] < ranks[2]) ||
      (ranks[0] > ranks[1] && ranks[1] > ranks[2]);
    if (!usesLadder(rule) || ladder) return [...line];
  }
  return null;
}

export function getWinner(position, rule = RULE_C) {
  for (const player of [LIGHT, DARK]) {
    const line = winningLine(position, player, rule);
    if (line) return { player, line };
  }
  return null;
}

export function isTerminal(position) {
  return position.status !== 'playing';
}

export function applyMove(position, move, rule = RULE_C) {
  if (!isLegalMove(position, move, rule)) return null;

  const next = clonePosition(position);
  const ranks = next.remaining[move.player];
  ranks.splice(ranks.indexOf(move.rank), 1);
  next.board[move.cell].push({ player: move.player, rank: move.rank });
  next.moves += 1;

  const win = getWinner(next, rule);
  if (win) {
    next.status = 'win';
    next.winner = win.player;
    next.winLine = win.line;
    next.turn = win.player;
    return next;
  }

  next.turn = otherPlayer(move.player);
  if (getLegalMoves(next, next.turn, rule).length) return next;

  next.turn = move.player;
  if (getLegalMoves(next, next.turn, rule).length) {
    next.passes += 1;
    return next;
  }

  next.status = 'draw';
  next.winner = null;
  next.winLine = null;
  return next;
}
