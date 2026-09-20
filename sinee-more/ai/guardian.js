import { otherPlayer } from './constants.js';
import { getLegalMoves, applyMove } from './rules.js';

function sameMove(a, b) {
  return !!a && !!b &&
    a.player === b.player && a.rank === b.rank && a.cell === b.cell;
}

export function getImmediateWins(position, player, rule) {
  if (!position || position.status !== 'playing') return [];
  const probe = position.turn === player
    ? position
    : { ...position, turn: player };
  const legal = getLegalMoves(probe, player, rule);
  return legal.filter(move => {
    const next = applyMove(probe, move, rule);
    return next?.status === 'win' && next.winner === player;
  });
}

export function getSafeMoves(position, player, rule) {
  if (!position || position.status !== 'playing') return [];
  const probe = position.turn === player
    ? position
    : { ...position, turn: player };
  return getLegalMoves(probe, player, rule).filter(move => {
    const next = applyMove(probe, move, rule);
    if (!next) return false;
    if (next.status === 'win') return next.winner === player;
    return getImmediateWins(next, otherPlayer(player), rule).length === 0;
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

    // A true tactical fork means that, before the opponent replies,
    // the mover would have at least two distinct immediate wins next turn.
    // This bounded definition avoids an exhaustive reply × reply scan.
    if (getImmediateWins(next, player, rule).length >= 2) out.push(move);
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
