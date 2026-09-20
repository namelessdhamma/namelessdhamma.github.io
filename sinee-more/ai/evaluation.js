import {
  LIGHT, DARK, LINES, otherPlayer, usesStack2, usesLadder
} from './constants.js';
import { topPiece } from './rules.js';

export const BASE_PROFILE = Object.freeze({
  terminal: 100000,
  boardControl: 5,
  centerControl: 3,
  closedCell: 18,
  coverMobility: 1.2,
  resource: 0.08,
  ladderResource: 0.35,
  linePressure: 7,
  forkPressure: 10,
  ladderPlan: 0.9,
  ladderOwned: 8,
  ladderBlocked: 11,
  ladderGlobalCapacity: 16,
  ladderResourceConflict: 8
});

const LADDER_TRIPLES = [];
for (let a = 1; a <= 9; a += 1) {
  for (let b = 1; b <= 9; b += 1) {
    for (let c = 1; c <= 9; c += 1) {
      if ((a < b && b < c) || (a > b && b > c)) {
        LADDER_TRIPLES.push(Object.freeze([a, b, c]));
      }
    }
  }
}
Object.freeze(LADDER_TRIPLES);

function available(position, player, rank) {
  return position.remaining[player].includes(rank);
}

function canCoverCell(position, player, cell, targetRank, rule) {
  const stack = position.board[cell];
  const top = topPiece(position, cell);
  if (!top) return available(position, player, targetRank);
  if (top.player === player) return top.rank === targetRank;
  if (usesStack2(rule) && stack.length >= 2) return false;
  return targetRank > top.rank && available(position, player, targetRank);
}

function ownTopCount(position, player, line) {
  let count = 0;
  for (const cell of line) {
    if (topPiece(position, cell)?.player === player) count += 1;
  }
  return count;
}

export function enumerateLadderPlans(position, player, line, rule = 'D') {
  const plans = [];

  for (const triple of LADDER_TRIPLES) {
    const requiredRanks = [];
    let coverCount = 0;
    let emptyCount = 0;
    let valid = true;

    for (let i = 0; i < 3; i += 1) {
      const cell = line[i];
      const targetRank = triple[i];
      const top = topPiece(position, cell);

      if (top?.player === player) {
        if (top.rank !== targetRank) {
          valid = false;
          break;
        }
        continue;
      }

      if (!canCoverCell(position, player, cell, targetRank, rule)) {
        valid = false;
        break;
      }

      requiredRanks.push(targetRank);
      if (top) coverCount += 1;
      else emptyCount += 1;
    }

    if (!valid) continue;
    if (new Set(requiredRanks).size !== requiredRanks.length) continue;

    plans.push({
      line: [...line],
      triple: [...triple],
      requiredRanks: [...requiredRanks].sort((a, b) => a - b),
      coverCount,
      emptyCount
    });
  }

  const dedup = new Map();
  for (const plan of plans) {
    const key = `${plan.triple.join(',')}|${plan.requiredRanks.join(',')}`;
    if (!dedup.has(key)) dedup.set(key, plan);
  }
  return [...dedup.values()];
}

export function maxCompatiblePlanCount(linePlanGroups) {
  const groups = linePlanGroups.filter(group => group.length > 0);

  function visit(groupIndex, used) {
    if (groupIndex >= groups.length) return 0;

    let best = visit(groupIndex + 1, used);
    for (const plan of groups[groupIndex]) {
      if (plan.requiredRanks.some(rank => used.has(rank))) continue;
      const next = new Set(used);
      for (const rank of plan.requiredRanks) next.add(rank);
      best = Math.max(best, 1 + visit(groupIndex + 1, next));
    }
    return best;
  }

  return visit(0, new Set());
}

export function countGlobalLadderCapacity(position, player, rule = 'D') {
  const activeGroups = [];
  let totalViablePlans = 0;

  for (const line of LINES) {
    const own = ownTopCount(position, player, line);
    const plans = enumerateLadderPlans(position, player, line, rule);
    totalViablePlans += plans.length;
    if (own >= 2 && plans.length) activeGroups.push(plans);
  }

  return {
    activeLinePlans: activeGroups.length,
    compatibleActivePlans: maxCompatiblePlanCount(activeGroups),
    totalViablePlans
  };
}

function resourceValue(position, player) {
  return position.remaining[player].reduce((sum, rank) => sum + rank * rank, 0);
}

function boardControl(position, player, profile) {
  let score = 0;
  for (let cell = 0; cell < 9; cell += 1) {
    const top = topPiece(position, cell);
    if (!top) continue;
    const sign = top.player === player ? 1 : -1;
    score += sign * profile.boardControl;
    if (cell === 4) score += sign * profile.centerControl;
  }
  return score;
}

function closedCellValue(position, player, rule, profile) {
  if (!usesStack2(rule)) return 0;
  let score = 0;
  for (let cell = 0; cell < 9; cell += 1) {
    if (position.board[cell].length < 2) continue;
    const top = topPiece(position, cell);
    const sign = top.player === player ? 1 : -1;
    const locationFactor = cell === 4 ? 1.35 : (cell % 2 === 0 ? 1.1 : 1);
    score += sign * profile.closedCell * locationFactor;
  }
  return score;
}

function coverMobility(position, player, rule) {
  let count = 0;
  for (let cell = 0; cell < 9; cell += 1) {
    const stack = position.board[cell];
    const top = topPiece(position, cell);
    if (!top || top.player === player) continue;
    if (usesStack2(rule) && stack.length >= 2) continue;
    for (const rank of position.remaining[player]) {
      if (rank > top.rank) count += 1;
    }
  }
  return count;
}

function classicLineFeatures(position, player) {
  let pressure = 0;
  let nearWins = 0;

  for (const line of LINES) {
    let own = 0;
    let opponent = 0;
    let empty = 0;
    for (const cell of line) {
      const top = topPiece(position, cell);
      if (!top) empty += 1;
      else if (top.player === player) own += 1;
      else opponent += 1;
    }

    if (opponent === 0) {
      pressure += own * own;
      if (own === 2 && empty === 1) nearWins += 1;
    }
  }

  return { pressure, nearWins };
}

function ladderPotential(position, player, rule, profile) {
  let score = 0;
  for (const line of LINES) {
    const own = ownTopCount(position, player, line);
    const plans = enumerateLadderPlans(position, player, line, rule);
    if (plans.length) {
      score += Math.min(40, plans.length) * profile.ladderPlan;
      score += own * own * profile.ladderOwned;
      const cheapestCoverCount = Math.min(...plans.map(plan => plan.coverCount));
      score -= cheapestCoverCount * 1.5;
    } else if (own > 0) {
      score -= own * profile.ladderBlocked;
    }
  }

  const global = countGlobalLadderCapacity(position, player, rule);
  score += global.compatibleActivePlans * profile.ladderGlobalCapacity;
  score -= Math.max(
    0,
    global.activeLinePlans - global.compatibleActivePlans
  ) * profile.ladderResourceConflict;

  return score;
}

function terminalScore(position, rootPlayer, profile) {
  if (position.status === 'draw') return 0;
  if (position.status !== 'win') return null;
  const tempo = Math.max(0, 20 - position.moves);
  return position.winner === rootPlayer
    ? profile.terminal + tempo
    : -profile.terminal - tempo;
}

export function evaluatePosition(
  position,
  rootPlayer,
  rule,
  profile = BASE_PROFILE
) {
  const terminal = terminalScore(position, rootPlayer, profile);
  if (terminal !== null) return terminal;

  const opponent = otherPlayer(rootPlayer);
  let score = 0;

  score += boardControl(position, rootPlayer, profile);
  score += closedCellValue(position, rootPlayer, rule, profile);

  const rootCover = coverMobility(position, rootPlayer, rule);
  const oppCover = coverMobility(position, opponent, rule);
  score += (rootCover - oppCover) * profile.coverMobility;

  score += (
    resourceValue(position, rootPlayer) -
    resourceValue(position, opponent)
  ) * profile.resource;

  if (usesLadder(rule)) {
    score += (
      resourceValue(position, rootPlayer) -
      resourceValue(position, opponent)
    ) * profile.ladderResource;
    score += ladderPotential(position, rootPlayer, rule, profile);
    score -= ladderPotential(position, opponent, rule, profile);
  } else {
    const rootLines = classicLineFeatures(position, rootPlayer);
    const oppLines = classicLineFeatures(position, opponent);
    score += (rootLines.pressure - oppLines.pressure) * profile.linePressure;
    score += (rootLines.nearWins - oppLines.nearWins) * profile.forkPressure;
  }

  return score;
}
