import test from 'node:test';
import assert from 'node:assert/strict';
import { GATES, runQualification, runStrengthProbe } from '../tools/qualification.js';

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
  assert.ok(report.metrics.timing.byDifficulty);
  assert.equal('personas' in report.metrics, false);
  assert.equal('openings' in report.metrics, false);
  assert.ok(Array.isArray(report.failures));
});
