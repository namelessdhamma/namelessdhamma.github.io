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
  return ranked.slice(0, Math.max(1, limit));
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

  const searchResult = searchIterative(position, {
    rule,
    rootPlayer: position.turn,
    evaluate: (state, rootPlayer) =>
      evaluatePosition(state, rootPlayer, rule),
    timeBudgetMs: policy.timeBudgetMs,
    maxDepth: policy.maxDepth,
    rootCandidates: tactical.moves
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
      ? collectTopCandidates(
          searchResult.rootScores,
          tactical.moves,
          searchResult.move,
          policy.openingCandidateLimit
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
