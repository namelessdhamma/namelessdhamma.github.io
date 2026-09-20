import test from 'node:test';
import assert from 'node:assert/strict';
import { RULE_C, RULE_D, RULE_CD, LIGHT } from '../ai/constants.js';
import { createInitialPosition, applyMove } from '../ai/rules.js';
import { DIFFICULTY, resolveDifficulty } from '../ai/difficulty.js';
import { chooseMove } from '../ai/engine.js';
import {
  immediateWinFixture, immediateBlockFixture,
  increasingLadderFixture, decreasingLadderFixture
} from '../fixtures/regressions.js';
import { getSafeMoves, getImmediateWins } from '../ai/guardian.js';

function sameMove(a, b) {
  return !!a && !!b &&
    a.player === b.player && a.rank === b.rank && a.cell === b.cell;
}

test('difficulty policies increase search budget and tighten regret', () => {
  assert.ok(DIFFICULTY.easy.timeBudgetMs < DIFFICULTY.medium.timeBudgetMs);
  assert.ok(DIFFICULTY.medium.timeBudgetMs < DIFFICULTY.hard.timeBudgetMs);
  assert.ok(DIFFICULTY.easy.regretBand > DIFFICULTY.medium.regretBand);
  assert.ok(DIFFICULTY.medium.regretBand > DIFFICULTY.hard.regretBand);
  assert.ok(DIFFICULTY.easy.forcingBudgetShare < DIFFICULTY.medium.forcingBudgetShare);
  assert.ok(DIFFICULTY.medium.forcingBudgetShare < DIFFICULTY.hard.forcingBudgetShare);
  assert.ok(DIFFICULTY.easy.strategicErrorRate > DIFFICULTY.medium.strategicErrorRate);
  assert.ok(DIFFICULTY.medium.strategicErrorRate > DIFFICULTY.hard.strategicErrorRate);
  assert.ok(DIFFICULTY.easy.strategicErrorSeverity > DIFFICULTY.medium.strategicErrorSeverity);
  assert.ok(DIFFICULTY.medium.strategicErrorSeverity > DIFFICULTY.hard.strategicErrorSeverity);
  assert.equal(resolveDifficulty('hard', 17).timeBudgetMs, 17);
  assert.equal(resolveDifficulty('medium', null, RULE_C).strategicErrorRate, DIFFICULTY.medium.strategicErrorRate);
  assert.ok(resolveDifficulty('medium', null, RULE_CD).strategicErrorRate > DIFFICULTY.medium.strategicErrorRate);
  assert.equal(resolveDifficulty('hard', null, RULE_CD).strategicErrorRate, 0);
});

test('hard always takes a known immediate win across personas', () => {
  const fixtures = [
    immediateWinFixture(),
    increasingLadderFixture(),
    decreasingLadderFixture()
  ];
  for (const fx of fixtures) {
    for (const persona of ['architect','hunter','sentinel','trickster']) {
      const result = chooseMove(fx.position, {
        rule: fx.rule,
        difficulty: 'hard',
        persona,
        seed: 123,
        timeBudgetOverrideMs: 20
      });
      const wins = getImmediateWins(fx.position, fx.position.turn, fx.rule);
      assert.ok(wins.some(move => sameMove(move, result.move)), `${fx.name}/${persona}`);
      assert.equal(result.metrics.tacticalTier, 'WIN_NOW');
    }
  }
});

test('hard never leaves a known immediate loss when safe moves exist', () => {
  const fx = immediateBlockFixture();
  const safe = getSafeMoves(fx.position, fx.position.turn, fx.rule);
  const result = chooseMove(fx.position, {
    rule: fx.rule,
    difficulty: 'hard',
    persona: 'hunter',
    seed: 7,
    timeBudgetOverrideMs: 30
  });
  assert.ok(safe.some(move => sameMove(move, result.move)));
  assert.equal(result.metrics.tacticalTier, 'MUST_DEFEND');
});

test('same position config and seed returns the same move', () => {
  let p = createInitialPosition(LIGHT);
  p = applyMove(p, { player: LIGHT, rank: 2, cell: 0 }, RULE_C);
  const config = {
    rule: RULE_C,
    difficulty: 'medium',
    persona: 'trickster',
    seed: 991,
    timeBudgetOverrideMs: 25
  };
  const a = chooseMove(p, config);
  const b = chooseMove(p, config);
  assert.deepEqual(a.move, b.move);
  assert.equal(typeof a.metrics.elapsedMs, 'number');
  assert.equal(typeof a.metrics.nodes, 'number');
  assert.equal(typeof a.metrics.completedDepth, 'number');
  assert.equal(typeof a.metrics.guardianElapsedMs, 'number');
  assert.equal(typeof a.metrics.searchElapsedMs, 'number');
  assert.ok(a.metrics.elapsedMs >= a.metrics.guardianElapsedMs + a.metrics.searchElapsedMs - 1);
});

test('engine always returns a legal coherent move under tiny budget', () => {
  const p = createInitialPosition(LIGHT);
  const result = chooseMove(p, {
    rule: RULE_C,
    difficulty: 'easy',
    persona: 'architect',
    seed: 1,
    timeBudgetOverrideMs: 0
  });
  assert.ok(result.move);
  assert.equal(result.move.player, LIGHT);
  assert.ok(
    result.metrics.timedOut || result.metrics.deliberateError === true,
    JSON.stringify(result.metrics)
  );
  assert.equal(typeof result.metrics.forcingSkipped, 'boolean');
});


test('hard personas do not collapse to one opening script', () => {
  for (const rule of [RULE_C, RULE_D, RULE_CD]) {
    const p = createInitialPosition(LIGHT);
    const results = ['architect','hunter','sentinel','trickster'].map((persona, index) =>
      chooseMove(p, {
        rule,
        difficulty: 'hard',
        persona,
        seed: 100 + index,
        timeBudgetOverrideMs: 30
      })
    );
    const choices = results.map(result => result.move);
    for (const result of results) {
      if (typeof result.metrics.openingRegret === 'number') {
        assert.ok(
          result.metrics.openingRegret <= DIFFICULTY.hard.openingRegretBand + 1e-9,
          `${rule}: opening regret ${result.metrics.openingRegret}`
        );
      }
    }
    const unique = new Set(choices.map(move => `${move.cell}:${move.rank}`));
    assert.ok(
      unique.size >= 2,
      `${rule}: ${JSON.stringify(results.map(result => ({move: result.move, depth: result.metrics.completedDepth, nodes: result.metrics.nodes})))}`
    );
  }
});


test('Hard D never opens with an extreme rank in the center', () => {
  const p = createInitialPosition(LIGHT);
  for (const persona of ['architect','hunter','sentinel','trickster']) {
    const result = chooseMove(p, {
      rule: RULE_D,
      difficulty: 'hard',
      persona,
      seed: 700 + persona.length,
      timeBudgetOverrideMs: 30
    });
    assert.ok(result.move);
    assert.equal(
      result.move.cell === 4 && (result.move.rank === 1 || result.move.rank === 9),
      false,
      `${persona}: ${JSON.stringify(result.move)}`
    );
  }
});


test('opening personas keep distinct identities inside the Hard fallback shortlist', () => {
  const p = createInitialPosition(LIGHT);
  const architect = chooseMove(p, {
    rule: RULE_D, difficulty: 'hard', persona: 'architect',
    seed: 41, timeBudgetOverrideMs: 0
  }).move;
  const hunter = chooseMove(p, {
    rule: RULE_D, difficulty: 'hard', persona: 'hunter',
    seed: 42, timeBudgetOverrideMs: 0
  }).move;
  const sentinel = chooseMove(p, {
    rule: RULE_D, difficulty: 'hard', persona: 'sentinel',
    seed: 43, timeBudgetOverrideMs: 0
  }).move;
  const trickster = chooseMove(p, {
    rule: RULE_D, difficulty: 'hard', persona: 'trickster',
    seed: 44, timeBudgetOverrideMs: 0
  }).move;

  assert.equal(architect.cell, 4);
  assert.notEqual(trickster.cell, 4);
  assert.ok(hunter.rank > sentinel.rank, JSON.stringify({ hunter, sentinel }));
});


test('Easy deliberately deviates more often than Medium on the same safe position', () => {
  const p = createInitialPosition(LIGHT);
  let easyErrors = 0;
  let mediumErrors = 0;

  for (let seed = 1; seed <= 64; seed += 1) {
    const easy = chooseMove(p, {
      rule: RULE_C,
      difficulty: 'easy',
      persona: 'architect',
      seed,
      timeBudgetOverrideMs: 0
    });
    const medium = chooseMove(p, {
      rule: RULE_C,
      difficulty: 'medium',
      persona: 'architect',
      seed,
      timeBudgetOverrideMs: 0
    });
    if (easy.metrics.deliberateError === true) easyErrors += 1;
    if (medium.metrics.deliberateError === true) mediumErrors += 1;
  }

  assert.ok(
    easyErrors >= mediumErrors + 12,
    JSON.stringify({ easyErrors, mediumErrors })
  );
});


test('CD complexity keeps a clear Easy Medium strategic-error gap', () => {
  const p = createInitialPosition(LIGHT);
  let easyErrors = 0;
  let mediumErrors = 0;

  for (let seed = 1; seed <= 64; seed += 1) {
    const easy = chooseMove(p, {
      rule: RULE_CD,
      difficulty: 'easy',
      persona: 'architect',
      seed,
      timeBudgetOverrideMs: 0
    });
    const medium = chooseMove(p, {
      rule: RULE_CD,
      difficulty: 'medium',
      persona: 'architect',
      seed,
      timeBudgetOverrideMs: 0
    });
    if (easy.metrics.deliberateError === true) easyErrors += 1;
    if (medium.metrics.deliberateError === true) mediumErrors += 1;
  }

  assert.ok(
    easyErrors >= mediumErrors + 8,
    JSON.stringify({ easyErrors, mediumErrors })
  );
});
