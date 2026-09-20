import { LINES } from './constants.js';
import { topPiece, applyMove } from './rules.js';
import { evaluatePosition } from './evaluation.js';
import { searchIterative } from './search.js';
import { getTacticalCandidates, getSafeMoves } from './guardian.js';
import { scorePersonaMove, createPersonaScoringContext, PERSONAS } from './personas.js';
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

function boundedMistakeSample(position, moves, rule, limit = 18) {
  if (moves.length <= limit) return [...moves];

  const cheap = [...moves]
    .map(move => ({ move, quality: cheapMoveQuality(position, move, rule) }))
    .sort((a, b) =>
      a.quality - b.quality ||
      b.move.rank - a.move.rank ||
      a.move.cell - b.move.cell
    );

  const selected = cheap.slice(0, Math.ceil(limit * 0.6)).map(x => x.move);
  const stride = Math.max(1, Math.floor(cheap.length / Math.max(1, limit - selected.length)));
  for (let i = 0; selected.length < limit && i < cheap.length; i += stride) {
    const move = cheap[i].move;
    if (!selected.some(x => sameMove(x, move))) selected.push(move);
  }
  return selected.slice(0, limit);
}

function choosePlausibleMistake(position, moves, rule, severity, rng) {
  if (!moves.length) return null;

  const player = position.turn;
  const sample = boundedMistakeSample(position, moves, rule);
  const ranked = sample
    .map(move => {
      const next = applyMove(position, move, rule);
      const objectiveScore = next
        ? evaluatePosition(next, player, rule)
        : Infinity;
      return {
        move,
        objectiveScore,
        cheapQuality: cheapMoveQuality(position, move, rule)
      };
    })
    .sort((a, b) =>
      a.objectiveScore - b.objectiveScore ||
      a.cheapQuality - b.cheapQuality ||
      b.move.rank - a.move.rank ||
      a.move.cell - b.move.cell
    );

  const fraction = Math.max(
    0.06,
    Math.min(0.35, 0.35 - severity * 0.28)
  );
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
  const ranked = [...moves].sort((a, b) =>
    cheapOpeningScore(b, rule) - cheapOpeningScore(a, rule) ||
    a.cell - b.cell ||
    a.rank - b.rank
  );
  const selected = ranked.slice(0, dynamicLimit);

  // Prevent the bounded opening search from becoming center-only.
  // This keeps at least one strategically plausible representative of
  // center, corner and edge play, while still starting from the strongest
  // generic opening shortlist. The shortlist may grow by at most two moves.
  const ensureClass = predicate => {
    if (selected.some(predicate)) return;
    const candidate = ranked.find(predicate);
    if (!candidate) return;
    selected.push(candidate);
  };
  ensureClass(move => move.cell === 4);
  ensureClass(move => [0, 2, 6, 8].includes(move.cell));
  ensureClass(move => [1, 3, 5, 7].includes(move.cell));

  return [...new Map(selected.map(move => [moveKey(move), move])).values()];
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

function collectOpeningCandidates(
  rootScores,
  tacticalMoves,
  bestMove,
  regretBand,
  limit
) {
  const allowed = new Set(tacticalMoves.map(moveKey));
  const ranked = (rootScores ?? [])
    .filter(item => allowed.has(moveKey(item.move)))
    .sort((a, b) =>
      b.score - a.score ||
      a.move.cell - b.move.cell ||
      a.move.rank - b.move.rank
    );

  if (!ranked.length) {
    return bestMove ? [{ move: bestMove, score: 0, rawScore: 0 }] : [];
  }

  const bestScore = ranked[0].score;
  const band = Math.max(1e-9, regretBand);
  return ranked
    .filter(item => item.score >= bestScore - regretBand)
    .slice(0, Math.max(1, limit))
    .map(item => ({
      move: item.move,
      rawScore: item.score,
      // Once a move is inside the objective safety band, compress the
      // difference so persona can express style without leaving the band.
      score: -4 * ((bestScore - item.score) / band)
    }));
}

function collectDeliberateErrorCandidates(
  rootScores,
  allowedMoves,
  fallbackMove,
  severity
) {
  const allowed = new Set(allowedMoves.map(moveKey));
  const ranked = (rootScores ?? [])
    .filter(item => allowed.has(moveKey(item.move)))
    .sort((a, b) =>
      b.score - a.score ||
      a.move.cell - b.move.cell ||
      a.move.rank - b.move.rank
    );

  if (ranked.length <= 1) {
    return fallbackMove
      ? [{ move: fallbackMove, score: 0, searchRegret: null }]
      : [];
  }

  const bestScore = ranked[0].score;
  const severity01 = Math.max(0, Math.min(1.5, severity));
  const startFraction = Math.min(0.92, 0.35 + severity01 * 0.38);
  const start = Math.max(1, Math.floor(ranked.length * startFraction));
  const tail = ranked.slice(start);

  return (tail.length ? tail : ranked.slice(1)).map(item => ({
    move: item.move,
    score: item.score,
    searchRegret: bestScore - item.score
  }));
}

function chooseByPersona(position, rule, personaId, candidates, personaWeight, noise, rng) {
  if (candidates.length <= 1) return candidates[0]?.move ?? null;

  const personaContext = createPersonaScoringContext(position, rule);
  const raw = candidates.map(item => ({
    ...item,
    personaScore: scorePersonaMove(
      position,
      item.move,
      rule,
      personaId,
      personaContext
    )
  }));
  const minPersona = Math.min(...raw.map(item => item.personaScore));
  const maxPersona = Math.max(...raw.map(item => item.personaScore));
  const spanPersona = Math.max(1e-9, maxPersona - minPersona);

  const scored = raw.map(item => {
    const personaNormalized =
      ((item.personaScore - minPersona) / spanPersona) * 2 - 1;
    return {
      ...item,
      personaNormalized,
      combinedScore: item.score + personaNormalized * personaWeight
    };
  });

  scored.sort((a, b) =>
    b.combinedScore - a.combinedScore ||
    b.score - a.score ||
    b.personaNormalized - a.personaNormalized ||
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
  const engineStarted = performance.now();
  const personaId = Object.hasOwn(PERSONAS, persona) ? persona : 'architect';
  const policy = resolveDifficulty(difficulty, timeBudgetOverrideMs, rule);
  const forcingDeadline =
    engineStarted + policy.timeBudgetMs * policy.forcingBudgetShare;
  const tactical = getTacticalCandidates(
    position,
    position.turn,
    rule,
    { deadline: forcingDeadline, now: () => performance.now() }
  );
  const rng = createRng(seed);

  if (!tactical.moves.length) {
    return {
      move: null,
      score: evaluatePosition(position, position.turn, rule),
      persona: personaId,
      metrics: {
        elapsedMs: performance.now() - engineStarted,
        guardianElapsedMs: performance.now() - engineStarted,
        searchElapsedMs: 0,
        nodes: 0,
        ttHits: 0,
        completedDepth: 0,
        timedOut: false,
        tacticalTier: tactical.tier,
        forcingSkipped: Boolean(tactical.forcingSkipped)
      }
    };
  }

  const deliberateError =
    (tactical.tier === 'SAFE' ||
      tactical.tier === 'ALL_LEGAL' ||
      tactical.tier === 'FORCING') &&
    policy.strategicErrorRate > 0 &&
    rng() < policy.strategicErrorRate;

  let decisionMoves = tactical.moves;
  if (deliberateError && tactical.tier === 'FORCING') {
    const forcing = new Set(tactical.moves.map(moveKey));
    const safe = getSafeMoves(position, position.turn, rule);
    const nonForcingSafe = safe.filter(move => !forcing.has(moveKey(move)));
    decisionMoves = nonForcingSafe.length ? nonForcingSafe : safe;
  }

  const searchCandidates =
    tactical.tier === 'WIN_NOW' || tactical.tier === 'MUST_DEFEND'
      ? tactical.moves
      : openingSearchCandidates(position, decisionMoves, rule, policy);

  const guardianElapsedMs = performance.now() - engineStarted;
  const remainingSearchBudgetMs = Math.max(
    0,
    policy.timeBudgetMs - guardianElapsedMs
  );

  const searchResult = searchIterative(position, {
    rule,
    rootPlayer: position.turn,
    evaluate: (state, rootPlayer) =>
      evaluatePosition(state, rootPlayer, rule),
    timeBudgetMs: remainingSearchBudgetMs,
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
  } else if (deliberateError) {
    accepted = collectDeliberateErrorCandidates(
      searchResult.rootScores,
      searchCandidates,
      searchResult.move,
      policy.strategicErrorSeverity
    );

    if (
      accepted.length <= 1 &&
      searchResult.completedDepth === 0 &&
      decisionMoves.length > 1
    ) {
      const fallback = choosePlausibleMistake(
        position,
        decisionMoves,
        rule,
        policy.strategicErrorSeverity,
        rng
      );
      accepted = fallback
        ? [{ move: fallback, score: 0, searchRegret: null }]
        : accepted;
    }
  } else {
    accepted = position.moves <= 1
      ? (
          searchResult.completedDepth === 0
            ? searchCandidates.map((move, index) => ({
                move,
                score: -Math.min(index, 4),
                rawScore: null
              }))
            : collectOpeningCandidates(
                searchResult.rootScores,
                searchCandidates,
                searchResult.move,
                policy.openingRegretBand,
                policy.openingCandidateLimit
              )
        )
      : collectNearBestCandidates(
          searchResult.rootScores,
          decisionMoves,
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

  const selectedCandidate = accepted.find(item => sameMove(item.move, move));
  const rawOpeningScores = position.moves <= 1
    ? accepted
        .map(item => item.rawScore)
        .filter(value => typeof value === 'number' && Number.isFinite(value))
    : [];
  const openingRegret =
    rawOpeningScores.length && typeof selectedCandidate?.rawScore === 'number'
      ? Math.max(...rawOpeningScores) - selectedCandidate.rawScore
      : null;

  return {
    move,
    score: searchResult.score,
    persona: personaId,
    metrics: {
      elapsedMs: performance.now() - engineStarted,
      guardianElapsedMs,
      searchElapsedMs: searchResult.elapsedMs ?? 0,
      nodes: searchResult.nodes ?? 0,
      ttHits: searchResult.ttHits ?? 0,
      completedDepth: searchResult.completedDepth ?? 0,
      timedOut: Boolean(searchResult.timedOut),
      tacticalTier: tactical.tier,
      forcingSkipped: Boolean(tactical.forcingSkipped),
      deliberateError,
      strategicRegret:
        deliberateError && typeof selectedCandidate?.searchRegret === 'number'
          ? selectedCandidate.searchRegret
          : null,
      openingRegret
    }
  };
}
