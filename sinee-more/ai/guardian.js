import { LINES, otherPlayer, usesLadder } from './constants.js';
import { getLegalMoves, isLegalMove, topPiece } from './rules.js';

function sameMove(a, b) {
  return !!a && !!b &&
    a.player === b.player && a.rank === b.rank && a.cell === b.cell;
}

function visibleTopCount(position, player) {
  let count = 0;
  for (let cell = 0; cell < 9; cell += 1) {
    if (topPiece(position, cell)?.player === player) count += 1;
  }
  return count;
}


function getLegalMovesOnCells(position, player, rule, cells) {
  const probe = position.turn === player
    ? position
    : { ...position, turn: player };
  const out = [];
  for (const rank of probe.remaining[player]) {
    for (const cell of cells) {
      const move = { player, rank, cell };
      if (isLegalMove(probe, move, rule)) out.push(move);
    }
  }
  return out;
}


function simulateNonWinningMove(position, move) {
  const board = position.board.slice();
  board[move.cell] = [
    ...position.board[move.cell],
    { player: move.player, rank: move.rank }
  ];
  return {
    ...position,
    board,
    remaining: {
      ...position.remaining,
      [move.player]: position.remaining[move.player]
        .filter(rank => rank !== move.rank)
    },
    turn: otherPlayer(move.player),
    moves: position.moves + 1,
    status: 'playing',
    winner: null,
    winLine: null
  };
}

function getImmediateThreatLines(position, player) {
  if (!position || position.status !== 'playing') return [];
  const out = [];

  for (const line of LINES) {
    let owned = 0;
    let target = -1;

    for (const cell of line) {
      const top = topPiece(position, cell);
      if (top?.player === player) owned += 1;
      else target = cell;
    }

    if (owned === 2 && target >= 0) out.push({ line, target });
  }
  return out;
}

export function getImmediateThreatCells(position, player, rule) {
  const cells = new Set(
    getImmediateThreatLines(position, player).map(item => item.target)
  );
  return [...cells].sort((a, b) => a - b);
}


function isWinningVisibleLine(position, player, rule, move) {
  for (const line of LINES) {
    if (!line.includes(move.cell)) continue;

    const ranks = [];
    let owned = true;
    for (const cell of line) {
      if (cell === move.cell) {
        ranks.push(move.rank);
        continue;
      }

      const top = topPiece(position, cell);
      if (!top || top.player !== player) {
        owned = false;
        break;
      }
      ranks.push(top.rank);
    }

    if (!owned) continue;
    if (!usesLadder(rule)) return true;

    if (
      (ranks[0] < ranks[1] && ranks[1] < ranks[2]) ||
      (ranks[0] > ranks[1] && ranks[1] > ranks[2])
    ) {
      return true;
    }
  }
  return false;
}

export function getImmediateWins(position, player, rule) {
  if (!position || position.status !== 'playing') return [];
  const probe = position.turn === player
    ? position
    : { ...position, turn: player };
  const threatCells = getImmediateThreatCells(probe, player, rule);
  if (!threatCells.length) return [];

  const wins = [];
  for (const rank of probe.remaining[player]) {
    for (const cell of threatCells) {
      const move = { player, rank, cell };
      if (!isLegalMove(probe, move, rule)) continue;
      if (isWinningVisibleLine(probe, player, rule, move)) wins.push(move);
    }
  }
  return wins;
}

export function getSafeMoves(position, player, rule) {
  if (!position || position.status !== 'playing') return [];
  const probe = position.turn === player
    ? position
    : { ...position, turn: player };
  const opponent = otherPlayer(player);

  if (visibleTopCount(position, opponent) < 2) {
    return getLegalMoves(probe, player, rule);
  }

  const opponentWins = getImmediateWins(probe, opponent, rule);
  if (!opponentWins.length) {
    return getLegalMoves(probe, player, rule);
  }

  const winningTargets = new Set(opponentWins.map(move => move.cell));
  const threatLines = getImmediateThreatLines(probe, opponent)
    .filter(item => winningTargets.has(item.target));

  const relevantCells = new Set();
  for (const item of threatLines) {
    for (const cell of item.line) relevantCells.add(cell);
  }

  const ownWins = getImmediateWins(probe, player, rule);
  const candidates = new Map();

  for (const move of ownWins) {
    candidates.set(`${move.cell}:${move.rank}`, move);
  }
  for (const move of getLegalMovesOnCells(probe, player, rule, relevantCells)) {
    candidates.set(`${move.cell}:${move.rank}`, move);
  }

  const ownWinningMoves = new Set(
    ownWins.map(move => `${move.cell}:${move.rank}`)
  );

  return [...candidates.values()]
    .sort((a, b) => a.rank - b.rank || a.cell - b.cell)
    .filter(move => {
      if (ownWinningMoves.has(`${move.cell}:${move.rank}`)) return true;
      const next = simulateNonWinningMove(probe, move);
      return getImmediateWins(next, opponent, rule).length === 0;
    });
}

function forcingMoves(position, player, rule, candidates, options = {}) {
  const now = options.now ?? (() => performance.now());
  const deadline = options.deadline ?? Infinity;
  if (position.moves < 2) return [];
  const probe = position.turn === player
    ? position
    : { ...position, turn: player };
  const out = [];

  for (const move of candidates) {
    if (now() >= deadline) break;
    const next = simulateNonWinningMove(probe, move);

    // First use the cheap double-threat test. Only rare candidates that
    // create 2+ immediate wins pay for reply verification.
    const threats = getImmediateWins(next, player, rule);
    if (threats.length < 2) continue;

    if (next.turn === player) {
      out.push(move);
      continue;
    }

    // If the opponent can win immediately, this is not a forcing attack.
    if (getImmediateWins(next, next.turn, rule).length) continue;

    // A defensive reply can neutralize our immediate threats only by
    // changing a cell on one of the supporting threat lines. Restricting
    // verification to those cells preserves exactness while avoiding scans
    // of strategically irrelevant replies.
    const relevantCells = new Set();
    for (const item of getImmediateThreatLines(next, player)) {
      for (const cell of item.line) relevantCells.add(cell);
    }

    let forced = true;
    const replies = getLegalMovesOnCells(
      next,
      next.turn,
      rule,
      relevantCells
    );

    for (const reply of replies) {
      if (now() >= deadline) {
        forced = false;
        break;
      }
      const afterReply = simulateNonWinningMove(next, reply);
      if (getImmediateWins(afterReply, player, rule).length === 0) {
        forced = false;
        break;
      }
    }

    if (forced) out.push(move);
  }
  return out;
}

export function getTacticalCandidates(position, player = position.turn, rule, options = {}) {
  const probe = position.turn === player
    ? position
    : { ...position, turn: player };
  const legal = getLegalMoves(probe, player, rule);
  if (!legal.length) return { tier: 'ALL_LEGAL', moves: [], forcingSkipped: false };

  const wins = getImmediateWins(probe, player, rule);
  if (wins.length) return { tier: 'WIN_NOW', moves: wins, forcingSkipped: false };

  const safe = getSafeMoves(probe, player, rule);
  if (safe.length && safe.length < legal.length) {
    return { tier: 'MUST_DEFEND', moves: safe, forcingSkipped: false };
  }

  const base = safe.length ? safe : legal;
  const now = options.now ?? (() => performance.now());
  const deadline = options.deadline ?? Infinity;
  const forcingSkipped = now() >= deadline;

  if (!forcingSkipped) {
    const forcing = forcingMoves(probe, player, rule, base, { now, deadline });
    if (forcing.length) {
      return { tier: 'FORCING', moves: forcing, forcingSkipped: false };
    }
  }

  if (safe.length) return { tier: 'SAFE', moves: safe, forcingSkipped };
  return { tier: 'ALL_LEGAL', moves: legal, forcingSkipped };
}

export { sameMove };
