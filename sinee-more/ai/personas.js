import {
  LINES, otherPlayer, usesLadder, usesStack2
} from './constants.js';
import { applyMove, topPiece } from './rules.js';
import { countGlobalLadderCapacity } from './evaluation.js';
import { getImmediateWins } from './guardian.js';

export const PERSONAS = Object.freeze({
  architect: Object.freeze({
    name: 'АРХИТЕКТОР',
    planContinuity: 2.2,
    ladderFlexibility: 2.0,
    forcing: 0.7,
    denial: 0.8,
    fork: 1.0,
    cover: 0.5,
    conservation: 1.2,
    intersection: 1.1
  }),
  hunter: Object.freeze({
    name: 'ОХОТНИК',
    planContinuity: 0.7,
    ladderFlexibility: 0.6,
    forcing: 2.3,
    denial: 0.6,
    fork: 1.5,
    cover: 2.5,
    conservation: -4.0,
    intersection: 0.6
  }),
  sentinel: Object.freeze({
    name: 'СТРАЖ',
    planContinuity: 0.8,
    ladderFlexibility: 0.9,
    forcing: 0.6,
    denial: 2.5,
    fork: 0.7,
    cover: 0.9,
    conservation: 1.6,
    intersection: 0.8
  }),
  trickster: Object.freeze({
    name: 'ЛОВКАЧ',
    planContinuity: 0.9,
    ladderFlexibility: 1.1,
    forcing: 1.2,
    denial: 0.8,
    fork: 3.0,
    cover: 0.9,
    conservation: 0.25,
    intersection: 1.8
  })
});

function lineCountForCell(cell) {
  let count = 0;
  for (const line of LINES) if (line.includes(cell)) count += 1;
  return count;
}

function classicOptionSpace(position, player) {
  let value = 0;
  for (const line of LINES) {
    let own = 0;
    let opp = 0;
    for (const cell of line) {
      const top = topPiece(position, cell);
      if (!top) continue;
      if (top.player === player) own += 1;
      else opp += 1;
    }
    if (opp === 0) value += 1 + own * own * 2;
  }
  return value;
}

function optionSpace(position, player, rule) {
  if (usesLadder(rule)) {
    const cap = countGlobalLadderCapacity(position, player, rule);
    return cap.totalViablePlans * 0.12 +
      cap.activeLinePlans * 3 +
      cap.compatibleActivePlans * 7;
  }
  return classicOptionSpace(position, player);
}

function closedCellDelta(before, after, player, rule) {
  if (!usesStack2(rule)) return 0;
  let delta = 0;
  for (let cell = 0; cell < 9; cell += 1) {
    const a = before.board[cell];
    const b = after.board[cell];
    if (a.length < 2 && b.length >= 2) {
      const top = topPiece(after, cell);
      delta += top?.player === player ? 1 : -1;
    }
  }
  return delta;
}

export function extractPersonaFeatures(position, move, rule) {
  const player = move.player;
  const opponent = otherPlayer(player);
  const beforeTop = topPiece(position, move.cell);
  const ownBefore = optionSpace(position, player, rule);
  const oppBefore = optionSpace(position, opponent, rule);
  const next = applyMove(position, move, rule);
  if (!next) {
    return {
      planContinuity: -1e6,
      ladderFlexibility: -1e6,
      forcing: -1e6,
      denial: -1e6,
      fork: -1e6,
      cover: -1e6,
      conservation: -1e6,
      intersection: -1e6
    };
  }

  const ownAfter = optionSpace(next, player, rule);
  const oppAfter = optionSpace(next, opponent, rule);
  const immediate = next.status === 'win'
    ? 4
    : getImmediateWins(next, player, rule).length;
  const fork = Math.max(0, immediate - 1);
  const cover = beforeTop && beforeTop.player === opponent ? 1 : 0;
  const closure = closedCellDelta(position, next, player, rule);

  return {
    planContinuity: ownAfter - ownBefore + Math.max(0, ownAfter) * 0.03,
    ladderFlexibility: usesLadder(rule) ? ownAfter : 0,
    forcing: immediate * 5 + cover * 2 + closure * 1.5,
    denial: oppBefore - oppAfter + closure * 2,
    fork,
    cover,
    conservation: 10 - move.rank,
    intersection: lineCountForCell(move.cell)
  };
}

function openingPersonaBonus(position, move, personaId) {
  if (position.moves > 1) return 0;
  const lines = lineCountForCell(move.cell);
  const middleRank = Math.max(0, 5 - Math.abs(move.rank - 5));

  if (personaId === 'architect') {
    return (move.cell === 4 ? 28 : lines * 3) + middleRank * 3;
  }
  if (personaId === 'hunter') {
    return move.rank * 5 + lines * 2;
  }
  if (personaId === 'sentinel') {
    return (10 - move.rank) * 5 + lines * 2;
  }
  if (personaId === 'trickster') {
    const offCenter = move.cell === 4 ? -20 : (move.cell % 2 === 0 ? 22 : 32);
    return offCenter + middleRank * 4;
  }
  return 0;
}

export function scorePersonaMove(position, move, rule, personaId) {
  const profile = PERSONAS[personaId] ?? PERSONAS.architect;
  const f = extractPersonaFeatures(position, move, rule);
  return (
    f.planContinuity * profile.planContinuity +
    f.ladderFlexibility * profile.ladderFlexibility +
    f.forcing * profile.forcing +
    f.denial * profile.denial +
    f.fork * profile.fork +
    f.cover * profile.cover +
    f.conservation * profile.conservation +
    f.intersection * profile.intersection +
    openingPersonaBonus(position, move, personaId)
  );
}

export function selectPersonaAtGameStart(styleChoice, previousPersona, rng = Math.random) {
  if (styleChoice !== 'mixed') {
    if (!Object.hasOwn(PERSONAS, styleChoice)) return 'architect';
    return styleChoice;
  }
  const ids = Object.keys(PERSONAS);
  const pool = ids.filter(id => id !== previousPersona);
  const candidates = pool.length ? pool : ids;
  return candidates[Math.floor(rng() * candidates.length)];
}
