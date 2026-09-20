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
  assert.equal(resolveDifficulty('hard', 17).timeBudgetMs, 17);
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
