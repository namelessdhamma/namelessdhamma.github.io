import { LINES, otherPlayer } from './constants.js';
import { getLegalMoves, isLegalMove, applyMove, topPiece } from './rules.js';

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

export function getImmediateThreatCells(position, player, rule) {
  if (!position || position.status !== 'playing') return [];
  const cells = new Set();

  for (const line of LINES) {
    let owned = 0;
    let target = -1;

    for (const cell of line) {
      const top = topPiece(position, cell);
      if (top?.player === player) owned += 1;
      else target = cell;
    }

    if (owned === 2 && target >= 0) cells.add(target);
  }

  return [...cells].sort((a, b) => a - b);
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
      const next = applyMove(probe, move, rule);
      if (next?.status === 'win' && next.winner === player) wins.push(move);
    }
  }
  return wins;
}

export function getSafeMoves(position, player, rule) {
  if (!position || position.status !== 'playing') return [];
  const probe = position.turn === player
    ? position
    : { ...position, turn: player };
  const legal = getLegalMoves(probe, player, rule);
  const opponent = otherPlayer(player);
  if (visibleTopCount(position, opponent) < 2) return legal;
  return legal.filter(move => {
    const next = applyMove(probe, move, rule);
    if (!next) return false;
    if (next.status === 'win') return next.winner === player;
    return getImmediateWins(next, opponent, rule).length === 0;
  });
}

function forcingMoves(position, player, rule, candidates) {
  if (position.moves < 2) return [];
  const probe = position.turn === player
    ? position
    : { ...position, turn: player };
  const out = [];

  for (const move of candidates) {
    const next = applyMove(probe, move, rule);
    if (!next || next.status !== 'playing') continue;

    // First use the cheap double-threat test. Only rare candidates that
    // create 2+ immediate wins pay for reply verification.
    const threats = getImmediateWins(next, player, rule);
    if (threats.length < 2) continue;

    if (next.turn === player) {
      out.push(move);
      continue;
    }

    let forced = true;
    const replies = getLegalMoves(next, next.turn, rule);
    for (const reply of replies) {
      const afterReply = applyMove(next, reply, rule);
      if (!afterReply) continue;
      if (afterReply.status === 'win' && afterReply.winner !== player) {
        forced = false;
        break;
      }
      if (
        afterReply.status === 'playing' &&
        getImmediateWins(afterReply, player, rule).length === 0
      ) {
        forced = false;
        break;
      }
    }

    if (forced) out.push(move);
  }
  return out;
}

export function getTacticalCandidates(position, player = position.turn, rule) {
  const probe = position.turn === player
    ? position
    : { ...position, turn: player };
  const legal = getLegalMoves(probe, player, rule);
  if (!legal.length) return { tier: 'ALL_LEGAL', moves: [] };

  const wins = getImmediateWins(probe, player, rule);
  if (wins.length) return { tier: 'WIN_NOW', moves: wins };

  const safe = getSafeMoves(probe, player, rule);
  if (safe.length && safe.length < legal.length) {
    return { tier: 'MUST_DEFEND', moves: safe };
  }

  const base = safe.length ? safe : legal;
  const forcing = forcingMoves(probe, player, rule, base);
  if (forcing.length) return { tier: 'FORCING', moves: forcing };

  if (safe.length) return { tier: 'SAFE', moves: safe };
  return { tier: 'ALL_LEGAL', moves: legal };
}

export { sameMove };
