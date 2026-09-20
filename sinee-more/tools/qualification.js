import fs from 'node:fs';
import { pathToFileURL } from 'node:url';
import {
  LIGHT, DARK, RULE_C, RULE_D, RULE_CD
} from '../ai/constants.js';
import { createInitialPosition } from '../ai/rules.js';
import { chooseMove } from '../ai/engine.js';
import { resolveDifficulty } from '../ai/difficulty.js';
import {
  getImmediateWins, getSafeMoves, getTacticalCandidates
} from '../ai/guardian.js';
import { evaluatePosition } from '../ai/evaluation.js';
import {
  scorePersonaMove, PERSONAS, selectPersonaAtGameStart
} from '../ai/personas.js';
import { createRng } from '../ai/rng.js';
import {
  searchFixedDepth, TranspositionTable
} from '../ai/search.js';
import {
  TRANSFORMS, transformPosition, canonicalize
} from '../ai/symmetry.js';
import { runGame } from './selfplay.js';
import { buildQualificationCorpus } from './corpus.js';
import {
  immediateWinFixture, immediateBlockFixture,
  increasingLadderFixture, decreasingLadderFixture
} from '../fixtures/regressions.js';

export const GATES = Object.freeze({
  tacticalHardBlunders: 0,
  cachedUncachedMismatches: 0,
  symmetryMismatches: 0,
  hardVsMediumMinScore: 0.53,
  mediumVsEasyMinScore: 0.53,
  minPairwisePersonaDisagreement: 0.10,
  minStrongPersonaPairsAt20Pct: 3,
  maxMixedOpeningShare: 0.75,
  maxBudgetOverrunMs: 40
});

const RULES = Object.freeze([RULE_C, RULE_D, RULE_CD]);
const PERSONA_IDS = Object.freeze(Object.keys(PERSONAS));

function sameMove(a, b) {
  return !!a && !!b &&
    a.player === b.player && a.rank === b.rank && a.cell === b.cell;
}

function moveKey(move) {
  return move ? `${move.player}:${move.cell}:${move.rank}` : '-';
}

function percentile(values, p) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.max(
    0,
    Math.min(sorted.length - 1, Math.ceil(p * sorted.length) - 1)
  );
  return sorted[index];
}

function makeAgent({
  difficulty, persona, seed, qualificationBudgetScale, timings
}) {
  let ply = 0;
  return {
    choose(position, ctx) {
      const policy = resolveDifficulty(difficulty);
      const budget = policy.timeBudgetMs * qualificationBudgetScale;
      const result = chooseMove(position, {
        rule: ctx.rule,
        difficulty,
        persona,
        seed: (seed + ply * 2654435761) >>> 0,
        timeBudgetOverrideMs: budget
      });
      timings.push({
        difficulty,
        budget,
        elapsedMs: result.metrics.elapsedMs,
        guardianMs: result.metrics.guardianElapsedMs ?? 0,
        searchMs: result.metrics.searchElapsedMs ?? 0,
        overrunMs: Math.max(0, result.metrics.elapsedMs - budget),
        nodes: result.metrics.nodes,
        ttHits: result.metrics.ttHits,
        depth: result.metrics.completedDepth,
        deliberateError: result.metrics.deliberateError === true
      });
      ply += 1;
      return result;
    }
  };
}

function tacticalMetrics(qualificationBudgetScale, seed) {
  const winFixtures = [
    immediateWinFixture(),
    increasingLadderFixture(),
    decreasingLadderFixture()
  ];
  const failures = [];
  let checked = 0;

  for (const fx of winFixtures) {
    for (const persona of PERSONA_IDS) {
      const budget = Math.max(
        1,
        resolveDifficulty('hard').timeBudgetMs * qualificationBudgetScale
      );
      const result = chooseMove(fx.position, {
        rule: fx.rule,
        difficulty: 'hard',
        persona,
        seed: (seed + checked) >>> 0,
        timeBudgetOverrideMs: budget
      });
      const immediate = getImmediateWins(
        fx.position, fx.position.turn, fx.rule
      );
      checked += 1;
      if (!immediate.some(move => sameMove(move, result.move))) {
        failures.push(`${fx.name}/${persona}: missed immediate win`);
      }
    }
  }

  const block = immediateBlockFixture();
  const safe = getSafeMoves(
    block.position, block.position.turn, block.rule
  );
  for (const persona of PERSONA_IDS) {
    const budget = Math.max(
      1,
      resolveDifficulty('hard').timeBudgetMs * qualificationBudgetScale
    );
    const result = chooseMove(block.position, {
      rule: block.rule,
      difficulty: 'hard',
      persona,
      seed: (seed + checked) >>> 0,
      timeBudgetOverrideMs: budget
    });
    checked += 1;
    if (safe.length && !safe.some(move => sameMove(move, result.move))) {
      failures.push(`${block.name}/${persona}: left immediate loss`);
    }
  }

  return {
    checked,
    blunders: failures.length,
    failures
  };
}

function searchConsistencyMetrics(corpus) {
  let mismatches = 0;
  const details = [];
  const sample = corpus.slice(0, Math.min(12, corpus.length));

  for (const item of sample) {
    const evaluate = (position, root) =>
      evaluatePosition(position, root, item.rule);

    const plain = searchFixedDepth(item.position, {
      rule: item.rule,
      rootPlayer: item.position.turn,
      depth: 2,
      evaluate,
      useTable: false,
      useSymmetry: false
    });

    const cached = searchFixedDepth(item.position, {
      rule: item.rule,
      rootPlayer: item.position.turn,
      depth: 2,
      evaluate,
      useTable: true,
      useSymmetry: false,
      table: new TranspositionTable()
    });

    if (
      plain.score !== cached.score ||
      !sameMove(plain.move, cached.move)
    ) {
      mismatches += 1;
      details.push(item.name);
    }
  }

  return {
    checked: sample.length,
    mismatches,
    details
  };
}

function symmetryMetrics(corpus) {
  let mismatches = 0;
  const details = [];
  const sample = corpus.slice(0, Math.min(12, corpus.length));

  for (const item of sample) {
    const target = canonicalize(item.position, item.rule).key;
    for (let id = 0; id < TRANSFORMS.length; id += 1) {
      const key = canonicalize(
        transformPosition(item.position, id),
        item.rule
      ).key;
      if (key !== target) {
        mismatches += 1;
        details.push(`${item.name}/t${id}`);
      }
    }
  }

  return {
    checked: sample.length * TRANSFORMS.length,
    mismatches,
    details
  };
}

function personaMetrics(corpus) {
  const selections = new Map(PERSONA_IDS.map(id => [id, []]));

  for (const item of corpus) {
    const tactical = getTacticalCandidates(
      item.position, item.position.turn, item.rule
    );
    for (const id of PERSONA_IDS) {
      const best = tactical.moves
        .map(move => ({
          move,
          score: scorePersonaMove(
            item.position, move, item.rule, id
          )
        }))
        .sort((a, b) =>
          b.score - a.score ||
          a.move.cell - b.move.cell ||
          a.move.rank - b.move.rank
        )[0]?.move ?? null;
      selections.get(id).push(moveKey(best));
    }
  }

  const pairs = [];
  for (let i = 0; i < PERSONA_IDS.length; i += 1) {
    for (let j = i + 1; j < PERSONA_IDS.length; j += 1) {
      const a = PERSONA_IDS[i];
      const b = PERSONA_IDS[j];
      let different = 0;
      for (let k = 0; k < corpus.length; k += 1) {
        if (
          selections.get(a)[k] !==
          selections.get(b)[k]
        ) {
          different += 1;
        }
      }
      pairs.push({
        a,
        b,
        disagreement: corpus.length
          ? different / corpus.length
          : 0
      });
    }
  }

  return {
    positions: corpus.length,
    pairs,
    minPairwiseDisagreement: pairs.length
      ? Math.min(...pairs.map(x => x.disagreement))
      : 0,
    strongPairsAt20Pct: pairs.filter(
      x => x.disagreement >= 0.20
    ).length
  };
}

function playStrengthGame({
  rule,
  persona,
  aDifficulty,
  bDifficulty,
  gameIndex,
  seed,
  qualificationBudgetScale,
  timings
}) {
  const phase = gameIndex % 4;
  const aIsLight = phase === 0 || phase === 2;
  const firstPlayer = phase < 2 ? LIGHT : DARK;

  const agentA = makeAgent({
    difficulty: aDifficulty,
    persona,
    seed: seed + gameIndex * 1009 + 17,
    qualificationBudgetScale,
    timings
  });
  const agentB = makeAgent({
    difficulty: bDifficulty,
    persona,
    seed: seed + gameIndex * 1009 + 53,
    qualificationBudgetScale,
    timings
  });

  const report = runGame({
    rule,
    lightAgent: aIsLight ? agentA : agentB,
    darkAgent: aIsLight ? agentB : agentA,
    firstPlayer,
    maxPlies: 40
  });

  const aColor = aIsLight ? LIGHT : DARK;
  const score = report.result === 'draw'
    ? 0.5
    : report.result === aColor ? 1 : 0;

  return {
    score,
    plies: report.plies,
    sequence: report.moves.map(
      item => moveKey(item.move)
    ).join('|')
  };
}

function strengthMatchup({
  aDifficulty,
  bDifficulty,
  gamesPerPair,
  seed,
  qualificationBudgetScale,
  timings
}) {
  let score = 0;
  let games = 0;
  let totalPlies = 0;
  const byRule = {};
  const sequences = new Map();

  for (let r = 0; r < RULES.length; r += 1) {
    const rule = RULES[r];
    byRule[rule] = { score: 0, games: 0, rate: 0 };

    for (let p = 0; p < PERSONA_IDS.length; p += 1) {
      const persona = PERSONA_IDS[p];

      for (let g = 0; g < gamesPerPair; g += 1) {
        const result = playStrengthGame({
          rule,
          persona,
          aDifficulty,
          bDifficulty,
          gameIndex: g,
          seed: seed + r * 100000 + p * 10000,
          qualificationBudgetScale,
          timings
        });
        score += result.score;
        games += 1;
        totalPlies += result.plies;
        byRule[rule].score += result.score;
        byRule[rule].games += 1;
        sequences.set(
          result.sequence,
          (sequences.get(result.sequence) ?? 0) + 1
        );
      }
    }
  }

  for (const rule of RULES) {
    byRule[rule].rate = byRule[rule].games
      ? byRule[rule].score / byRule[rule].games
      : 0;
  }

  const repeatedGames = [...sequences.values()]
    .filter(count => count > 1)
    .reduce((sum, count) => sum + count, 0);

  return {
    aDifficulty,
    bDifficulty,
    games,
    scoreRate: games ? score / games : 0,
    averagePlies: games ? totalPlies / games : 0,
    repeatedSequenceRate: games
      ? repeatedGames / games
      : 0,
    byRule
  };
}

function strengthMetrics({
  gamesPerPair,
  seed,
  qualificationBudgetScale,
  timings
}) {
  return {
    hardVsMedium: strengthMatchup({
      aDifficulty: 'hard',
      bDifficulty: 'medium',
      gamesPerPair,
      seed: seed + 1000000,
      qualificationBudgetScale,
      timings
    }),
    mediumVsEasy: strengthMatchup({
      aDifficulty: 'medium',
      bDifficulty: 'easy',
      gamesPerPair,
      seed: seed + 2000000,
      qualificationBudgetScale,
      timings
    })
  };
}

function openingMetrics({
  seed,
  qualificationBudgetScale,
  enforceStatisticalGates
}) {
  const gamesPerRule = enforceStatisticalGates ? 200 : 8;
  const byRule = {};
  let maxOpeningShare = 0;

  for (let r = 0; r < RULES.length; r += 1) {
    const rule = RULES[r];
    const histogram = new Map();
    const regrets = [];
    let unknownRegrets = 0;
    let previousPersona = '';
    const rng = createRng(seed + r * 1000);

    for (let game = 0; game < gamesPerRule; game += 1) {
      const persona = selectPersonaAtGameStart(
        'mixed', previousPersona, rng
      );
      previousPersona = persona;

      const position = createInitialPosition(LIGHT);
      const budget =
        resolveDifficulty('hard').timeBudgetMs *
        qualificationBudgetScale;
      const result = chooseMove(position, {
        rule,
        difficulty: 'hard',
        persona,
        seed: seed + r * 100000 + game,
        timeBudgetOverrideMs: budget
      });
      const key = moveKey(result.move);
      histogram.set(key, (histogram.get(key) ?? 0) + 1);
      if (typeof result.metrics.openingRegret === 'number') {
        regrets.push(result.metrics.openingRegret);
      } else {
        unknownRegrets += 1;
      }
    }

    const peak = histogram.size
      ? Math.max(...histogram.values())
      : 0;
    const share = gamesPerRule
      ? peak / gamesPerRule
      : 0;
    maxOpeningShare = Math.max(maxOpeningShare, share);

    byRule[rule] = {
      games: gamesPerRule,
      uniqueOpenings: histogram.size,
      maxOpeningShare: share,
      meanOpeningRegret: regrets.length
        ? regrets.reduce((a, b) => a + b, 0) / regrets.length
        : null,
      maxOpeningRegret: regrets.length ? Math.max(...regrets) : null,
      unknownOpeningRegrets: unknownRegrets,
      histogram: Object.fromEntries(histogram)
    };
  }

  return {
    gamesPerRule,
    maxOpeningShare,
    byRule
  };
}

function summarizeTiming(timings) {
  const elapsed = timings.map(x => x.elapsedMs);
  const overruns = timings.map(x => x.overrunMs);
  const totalNodes = timings.reduce((sum, x) => sum + x.nodes, 0);
  const totalHits = timings.reduce((sum, x) => sum + x.ttHits, 0);
  const depth = timings.map(x => x.depth);
  const deliberateErrors = timings.filter(x => x.deliberateError).length;
  const guardian = timings.map(x => x.guardianMs ?? 0);
  const search = timings.map(x => x.searchMs ?? 0);

  return {
    samples: timings.length,
    meanMoveMs: elapsed.length
      ? elapsed.reduce((a, b) => a + b, 0) / elapsed.length
      : 0,
    meanGuardianMs: guardian.length
      ? guardian.reduce((a, b) => a + b, 0) / guardian.length
      : 0,
    meanSearchMs: search.length
      ? search.reduce((a, b) => a + b, 0) / search.length
      : 0,
    p95MoveMs: percentile(elapsed, 0.95),
    maxBudgetOverrunMs: overruns.length
      ? Math.max(...overruns)
      : 0,
    meanCompletedDepth: depth.length
      ? depth.reduce((a, b) => a + b, 0) / depth.length
      : 0,
    deliberateErrors,
    deliberateErrorRate: timings.length
      ? deliberateErrors / timings.length
      : 0,
    nodes: totalNodes,
    ttHits: totalHits,
    ttHitRatio: totalNodes ? totalHits / totalNodes : 0
  };
}

function timingMetrics(timings) {
  return {
    ...summarizeTiming(timings),
    byDifficulty: Object.fromEntries(
      ['easy', 'medium', 'hard'].map(difficulty => [
        difficulty,
        summarizeTiming(timings.filter(x => x.difficulty === difficulty))
      ])
    )
  };
}

export function runQualification({
  gamesPerPair = 34,
  seed = 0x51eaea,
  enforceStatisticalGates = true,
  qualificationBudgetScale = 0.04,
  corpusSize = 100
} = {}) {
  const timings = [];
  const corpus = buildQualificationCorpus({
    count: corpusSize,
    seed
  });

  const tactical = tacticalMetrics(
    qualificationBudgetScale,
    seed
  );
  const searchConsistency =
    searchConsistencyMetrics(corpus);
  const symmetry = symmetryMetrics(corpus);
  const personas = personaMetrics(corpus);
  const strength = strengthMetrics({
    gamesPerPair,
    seed,
    qualificationBudgetScale,
    timings
  });
  const openings = openingMetrics({
    seed,
    qualificationBudgetScale,
    enforceStatisticalGates
  });
  const timing = timingMetrics(timings);

  const failures = [];

  if (
    tactical.blunders >
    GATES.tacticalHardBlunders
  ) {
    failures.push(
      `Hard tactical blunders: ${tactical.blunders}`
    );
  }
  if (
    searchConsistency.mismatches >
    GATES.cachedUncachedMismatches
  ) {
    failures.push(
      `Cached/uncached mismatches: ${searchConsistency.mismatches}`
    );
  }
  if (
    symmetry.mismatches >
    GATES.symmetryMismatches
  ) {
    failures.push(
      `Symmetry mismatches: ${symmetry.mismatches}`
    );
  }

  if (enforceStatisticalGates) {
    if (
      personas.minPairwiseDisagreement <
      GATES.minPairwisePersonaDisagreement
    ) {
      failures.push(
        `Persona disagreement too low: ${personas.minPairwiseDisagreement.toFixed(3)}`
      );
    }
    if (
      personas.strongPairsAt20Pct <
      GATES.minStrongPersonaPairsAt20Pct
    ) {
      failures.push(
        `Persona strong pairs: ${personas.strongPairsAt20Pct}`
      );
    }
    if (
      strength.hardVsMedium.scoreRate <
      GATES.hardVsMediumMinScore
    ) {
      failures.push(
        `Hard vs Medium score: ${strength.hardVsMedium.scoreRate.toFixed(3)}`
      );
    }
    if (
      strength.mediumVsEasy.scoreRate <
      GATES.mediumVsEasyMinScore
    ) {
      failures.push(
        `Medium vs Easy score: ${strength.mediumVsEasy.scoreRate.toFixed(3)}`
      );
    }
    if (
      openings.maxOpeningShare >
      GATES.maxMixedOpeningShare
    ) {
      failures.push(
        `Mixed opening share: ${openings.maxOpeningShare.toFixed(3)}`
      );
    }
    if (
      timing.maxBudgetOverrunMs >
      GATES.maxBudgetOverrunMs
    ) {
      failures.push(
        `Budget overrun: ${timing.maxBudgetOverrunMs.toFixed(1)}ms`
      );
    }
  }

  return {
    ok: failures.length === 0,
    gates: GATES,
    config: {
      gamesPerPair,
      totalGamesPerDifficultyMatchup:
        gamesPerPair * RULES.length * PERSONA_IDS.length,
      seed,
      enforceStatisticalGates,
      qualificationBudgetScale,
      corpusSize
    },
    metrics: {
      tactical,
      searchConsistency,
      symmetry,
      personas,
      strength,
      openings,
      timing
    },
    failures
  };
}

function cliArg(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] != null
    ? process.argv[index + 1]
    : fallback;
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  const fast = process.argv.includes('--fast');
  const report = runQualification({
    gamesPerPair: Number(
      cliArg('--games-per-pair', fast ? 1 : 34)
    ),
    seed: Number(cliArg('--seed', 0x51eaea)),
    enforceStatisticalGates: !fast,
    qualificationBudgetScale: Number(
      cliArg('--budget-scale', fast ? 0 : 0.04)
    ),
    corpusSize: Number(
      cliArg('--corpus-size', fast ? 24 : 100)
    )
  });

  const json = JSON.stringify(report, null, 2);
  console.log(json);

  const outputPath = cliArg('--json');
  if (outputPath) fs.writeFileSync(outputPath, json + '\n');

  process.exitCode = report.ok ? 0 : 1;
}
