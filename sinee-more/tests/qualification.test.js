import test from 'node:test';
import assert from 'node:assert/strict';
import { GATES, runQualification, runStrengthProbe, mirroredStrengthPhase } from '../tools/qualification.js';

test('qualification exposes the v1 release gates', () => {
  assert.equal(GATES.tacticalHardBlunders, 0);
  assert.equal(GATES.cachedUncachedMismatches, 0);
  assert.equal(GATES.symmetryMismatches, 0);
  assert.equal(GATES.hardVsMediumMinScore, 0.53);
  assert.equal(GATES.mediumVsEasyMinScore, 0.53);
  assert.equal(GATES.minPairwisePersonaDisagreement, 0.10);
  assert.equal(GATES.minStrongPersonaPairsAt20Pct, 3);
  assert.equal(GATES.maxMixedOpeningShare, 0.75);
  assert.equal(GATES.maxBudgetOverrunMs, 40);
});


test('strength quartet mirrors roles without changing agent RNG identities', () => {
  const phases = [0, 1, 2, 3].map(gameIndex =>
    mirroredStrengthPhase(gameIndex, 1000)
  );

  assert.deepEqual(
    phases.map(x => [x.aIsLight, x.firstPlayer]),
    [
      [true, 'light'],
      [false, 'light'],
      [true, 'dark'],
      [false, 'dark']
    ]
  );
  assert.equal(new Set(phases.map(x => x.agentASeed)).size, 1);
  assert.equal(new Set(phases.map(x => x.agentBSeed)).size, 1);

  const next = mirroredStrengthPhase(4, 1000);
  assert.notEqual(next.agentASeed, phases[0].agentASeed);
  assert.notEqual(next.agentBSeed, phases[0].agentBSeed);
  assert.equal(next.quartet, 1);
});

test('fast qualification returns a complete report shape', () => {
  const report = runQualification({
    gamesPerPair: 1,
    seed: 1,
    enforceStatisticalGates: false,
    qualificationBudgetScale: 0,
    corpusSize: 24
  });
  assert.equal(typeof report.ok, 'boolean');
  assert.ok(report.gates);
  assert.ok(report.metrics);
  assert.ok(report.metrics.tactical);
  assert.ok(report.metrics.searchConsistency);
  assert.ok(report.metrics.symmetry);
  assert.ok(report.metrics.personas);
  assert.ok(report.metrics.strength);
  assert.ok(report.metrics.openings);
  assert.ok(report.metrics.timing.byDifficulty);
  assert.ok(report.metrics.timing.byDifficulty.easy);
  assert.ok(report.metrics.timing.byDifficulty.medium);
  assert.ok(report.metrics.timing.byDifficulty.hard);
  assert.equal(typeof report.metrics.timing.forcingSkippedRate, 'number');
  assert.equal(typeof report.metrics.timing.guardianShare, 'number');
  assert.equal(typeof report.metrics.timing.meanStrategicRegret, 'number');
  assert.equal(typeof report.metrics.timing.p95StrategicRegret, 'number');
  assert.ok(Array.isArray(report.failures));
});


test('focused strength probe omits unrelated qualification work', () => {
  const report = runStrengthProbe({
    gamesPerPair: 1,
    seed: 11,
    qualificationBudgetScale: 0
  });
  assert.equal(typeof report.ok, 'boolean');
  assert.ok(report.metrics.strength.hardVsMedium);
  assert.ok(report.metrics.strength.mediumVsEasy);
  assert.equal(
    typeof report.metrics.strength.hardVsMedium.score95CI.low,
    'number'
  );
  assert.equal(
    typeof report.metrics.strength.hardVsMedium.score95CI.high,
    'number'
  );
  assert.equal(
    typeof report.metrics.strength.hardVsMedium.gateMargin,
    'number'
  );
  assert.equal(
    typeof report.metrics.strength.hardVsMedium.ciClearsGate,
    'boolean'
  );
  assert.equal(
    typeof report.metrics.strength.hardVsMedium.ruleSpread,
    'number'
  );
  assert.equal(
    typeof report.metrics.strength.mediumVsEasy.gateMargin,
    'number'
  );
  assert.ok(report.metrics.timing.byDifficulty);
  assert.equal('personas' in report.metrics, false);
  assert.equal('openings' in report.metrics, false);
  assert.ok(Array.isArray(report.failures));
});


test('focused strength probe can isolate CD calibration', () => {
  const report = runStrengthProbe({
    gamesPerPair: 1,
    seed: 19,
    qualificationBudgetScale: 0,
    rules: ['CD']
  });
  assert.deepEqual(report.config.rules, ['CD']);
  assert.equal(report.config.totalGamesPerDifficultyMatchup, 4);
  assert.deepEqual(
    Object.keys(report.metrics.strength.hardVsMedium.byRule),
    ['CD']
  );
  assert.deepEqual(
    Object.keys(report.metrics.strength.mediumVsEasy.byRule),
    ['CD']
  );
  assert.equal(report.metrics.strength.hardVsMedium.weakestRule, 'CD');
  assert.equal(report.metrics.strength.mediumVsEasy.weakestRule, 'CD');
});
