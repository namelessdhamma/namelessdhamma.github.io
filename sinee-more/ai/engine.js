import { LINES } from './constants.js';
import { topPiece } from './rules.js';
import { evaluatePosition } from './evaluation.js';
import { searchIterative } from './search.js';
import { getTacticalCandidates } from './guardian.js';
import { scorePersonaMove, PERSONAS } from './personas.js';
import { createRng } from './rng.js';
import { resolveDifficulty } from './difficulty.js';

function sameMove(a, b) {
  return !!a && !!b &&
    a.player === b.player && a.rank === b.rank && a.cell === b.cell;
}

function moveKey(move) {
  return `${move.player}:${move.rank}:${move.cell}`;
}


const MONOTONIC_TRIPLES = (() => {
  const triples = [];
  for (let a = 1; a <= 9; a += 1) {
    for (let b = 1; b <= 9; b += 1) {
      for (let c = 1; c <= 9; c += 1) {
        if ((a < b && b < c) || (a > b && b > c)) triples.push([a,b,c]);
      }
    }
  }
  return triples;
})();

function ladderRoleFlexibility(cell, rank) {
  let count = 0;
  for (const line of LINES) {
    const index = line.indexOf(cell);
    if (index < 0) continue;
    for (const triple of MONOTONIC_TRIPLES) {
      if (triple[index] === rank) count += 1;
    }
  }
  return count;
}

function cheapOpeningScore(move, rule) {
  const location = move.cell === 4 ? 8 : (move.cell % 2 === 0 ? 5 : 3);
  const rankEconomy = (10 - move.rank) * 0.18;
  if (rule === 'D' || rule === 'CD') {
    return ladderRoleFlexibility(move.cell, move.rank) * 1.4 + location + rankEconomy;
  }
  return location + rankEconomy;
}

function cheapMoveQuality(position, move, rule) {
  const location = move.cell === 4 ? 7 : (move.cell % 2 === 0 ? 4 : 2);
  const resource = (10 - move.rank) * 0.85;
  const target = topPiece(position, move.cell);
  let score = location + resource;
  if (target) {
    score += 8 + target.rank * 1.25;
    if ((rule === 'C' || rule === 'CD') && position.board[move.cell].length === 1) {
      score += 5;
    }
  }
  if (rule === 'D' || rule === 'CD') {
    score += ladderRoleFlexibility(move.cell, move.rank) * 0.55;
  }
  return score;
}

function choosePlausibleMistake(position, moves, rule, severity, rng) {
  if (!moves.length) return null;
  const ranked = [...moves]
    .map(move => ({ move, quality: cheapMoveQuality(position, move, rule) }))
    .sort((a, b) =>
      a.quality - b.quality ||
      b.move.rank - a.move.rank ||
      a.move.cell - b.move.cell
    );
  const fraction = Math.max(0.08, Math.min(0.35, severity * 0.32));
  const span = Math.max(1, Math.ceil(ranked.length * fraction));
  return ranked[Math.floor(rng() * span)].move;
}

function openingSearchCandidates(position, moves, rule, policy) {
  if (position.moves > 1 || moves.length <= 1) return moves;
  const dynamicLimit = Math.max(
    6,
    Math.min(
      policy.openingCandidateLimit,
      Math.floor(Math.max(1, policy.timeBudgetMs) / 20) + 5
    )
  );
  return [...moves]
    .sort((a, b) =>
      cheapOpeningScore(b, rule) - cheapOpeningScore(a, rule) ||
      a.cell - b.cell ||
      a.rank - b.rank
    )
    .slice(0, dynamicLimit);
}

function collectNearBestCandidates(rootScores, tacticalMoves, bestMove, regretBand) {
  const scoreMap = new Map(
    (rootScores ?? []).map(item => [moveKey(item.move), item.score])
  );

  if (!scoreMap.size && bestMove) {
    return [{ move: bestMove, score: 0 }];
  }

  let best = -Infinity;
  for (const move of tacticalMoves) {
    const score = scoreMap.get(moveKey(move));
    if (score != null && score > best) best = score;
  }

  if (best === -Infinity) {
    return bestMove ? [{ move: bestMove, score: 0 }] : [];
  }

  return tacticalMoves
    .map(move => ({ move, score: scoreMap.get(moveKey(move)) }))
    .filter(item => item.score != null && item.score >= best - regretBand);
}

function collectTopCandidates(rootScores, tacticalMoves, bestMove, limit) {
  const allowed = new Set(tacticalMoves.map(moveKey));
  const ranked = (rootScores ?? [])
    .filter(item => allowed.has(moveKey(item.move)))
    .sort((a, b) =>
      b.score - a.score ||
      a.move.cell - b.move.cell ||
      a.move.rank - b.move.rank
    );
  if (!ranked.length) {
    return bestMove ? [{ move: bestMove, score: 0 }] : [];
  }
  return ranked
    .slice(0, Math.max(1, limit))
    .map((item, index) => ({
      move: item.move,
      score: -index * 2,
      rawScore: item.score
    }));
}

function chooseByPersona(position, rule, personaId, candidates, personaWeight, noise, rng) {
  if (candidates.length <= 1) return candidates[0]?.move ?? null;

  const scored = candidates.map(item => {
    const personaScore = scorePersonaMove(position, item.move, rule, personaId);
    return {
      ...item,
      personaScore,
      combinedScore: item.score + personaScore * personaWeight
    };
  });

  scored.sort((a, b) =>
    b.combinedScore - a.combinedScore ||
    b.score - a.score ||
    b.personaScore - a.personaScore ||
    a.move.cell - b.move.cell ||
    a.move.rank - b.move.rank
  );

  if (noise <= 0) return scored[0].move;

  const span = Math.min(
    scored.length,
    Math.max(1, 1 + Math.floor(noise * scored.length * 2.5))
  );
  const pool = scored.slice(0, span);

  const weights = pool.map((item, index) => {
    const rankWeight = 1 / (1 + index);
    const strategic = Math.max(0.05, 1 - noise * index);
    return rankWeight * strategic;
  });
  const total = weights.reduce((sum, value) => sum + value, 0);
  let roll = rng() * total;
  for (let i = 0; i < pool.length; i += 1) {
    roll -= weights[i];
    if (roll <= 0) return pool[i].move;
  }
  return pool[0].move;
}

export function chooseMove(position, {
  rule,
  difficulty = 'medium',
  persona = 'architect',
  seed = 1,
  timeBudgetOverrideMs = null
} = {}) {
  const personaId = Object.hasOwn(PERSONAS, persona) ? persona : 'architect';
  const policy = resolveDifficulty(difficulty, timeBudgetOverrideMs);
  const tactical = getTacticalCandidates(position, position.turn, rule);
  const rng = createRng(seed);

  if (!tactical.moves.length) {
    return {
      move: null,
      score: evaluatePosition(position, position.turn, rule),
      persona: personaId,
      metrics: {
        elapsedMs: 0,
        nodes: 0,
        ttHits: 0,
        completedDepth: 0,
        timedOut: false,
        tacticalTier: tactical.tier
      }
    };
  }

  if (
    (tactical.tier === 'SAFE' || tactical.tier === 'ALL_LEGAL') &&
    policy.strategicErrorRate > 0 &&
    rng() < policy.strategicErrorRate
  ) {
    const mistake = choosePlausibleMistake(
      position,
      tactical.moves,
      rule,
      policy.strategicErrorSeverity,
      rng
    );
    if (mistake) {
      return {
        move: mistake,
        score: evaluatePosition(position, position.turn, rule),
        persona: personaId,
        metrics: {
          elapsedMs: 0,
          nodes: 0,
          ttHits: 0,
          completedDepth: 0,
          timedOut: false,
          tacticalTier: tactical.tier,
          deliberateError: true
        }
      };
    }
  }

  const searchCandidates =
    tactical.tier === 'WIN_NOW' || tactical.tier === 'MUST_DEFEND'
      ? tactical.moves
      : openingSearchCandidates(position, tactical.moves, rule, policy);

  const searchResult = searchIterative(position, {
    rule,
    rootPlayer: position.turn,
    evaluate: (state, rootPlayer) =>
      evaluatePosition(state, rootPlayer, rule),
    timeBudgetMs: policy.timeBudgetMs,
    maxDepth: policy.maxDepth,
    rootCandidates: searchCandidates
  });

  let accepted;
  if (tactical.tier === 'WIN_NOW') {
    accepted = tactical.moves.map(move => ({
      move,
      score: searchResult.rootScores?.find(x => sameMove(x.move, move))?.score
        ?? searchResult.score
    }));
  } else {
    accepted = position.moves <= 1
      ? (
          searchResult.completedDepth === 0
            ? searchCandidates.map((move, index) => ({
                move,
                score: -index * 2
              }))
            : collectTopCandidates(
                searchResult.rootScores,
                searchCandidates,
                searchResult.move,
                policy.openingCandidateLimit
              )
        )
      : collectNearBestCandidates(
          searchResult.rootScores,
          tactical.moves,
          searchResult.move,
          policy.regretBand
        );
  }

  const move = chooseByPersona(
    position,
    rule,
    personaId,
    accepted,
    position.moves <= 1
      ? policy.openingPersonaWeight
      : policy.personaWeight,
    policy.strategicNoise,
    rng
  ) ?? searchResult.move ?? tactical.moves[0];

  return {
    move,
    score: searchResult.score,
    persona: personaId,
    metrics: {
      elapsedMs: searchResult.elapsedMs ?? 0,
      nodes: searchResult.nodes ?? 0,
      ttHits: searchResult.ttHits ?? 0,
      completedDepth: searchResult.completedDepth ?? 0,
      timedOut: Boolean(searchResult.timedOut),
      tacticalTier: tactical.tier
    }
  };
}
