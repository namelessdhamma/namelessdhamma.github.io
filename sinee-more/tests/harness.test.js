import test from 'node:test';
import assert from 'node:assert/strict';
import { RULE_C } from '../ai/constants.js';
import { getLegalMoves } from '../ai/rules.js';
import { runGame } from '../tools/selfplay.js';
import { buildQualificationCorpus } from '../tools/corpus.js';

const firstLegalAgent = {
  choose(position, ctx) {
    return ctx.getLegalMoves(position, position.turn, ctx.rule)[0] ?? null;
  }
};

test('headless runner completes and records moves and timing', () => {
  const report = runGame({
    rule: RULE_C,
    lightAgent: firstLegalAgent,
    darkAgent: firstLegalAgent,
    maxPlies: 40
  });
  assert.ok(['light', 'dark', 'draw'].includes(report.result));
  assert.ok(report.plies > 0);
  assert.equal(report.moves.length, report.plies);
  assert.ok(report.moves.every(x => typeof x.elapsedMs === 'number'));
});

test('qualification corpus is deterministic, unique, and non-terminal', () => {
  const a = buildQualificationCorpus({ count: 100, seed: 0x51eaea });
  const b = buildQualificationCorpus({ count: 100, seed: 0x51eaea });
  assert.equal(a.length, 100);
  assert.deepEqual(a.map(x => x.key), b.map(x => x.key));
  assert.equal(new Set(a.map(x => x.key)).size, 100);
  assert.ok(a.every(x => x.position.status === 'playing'));
  assert.ok(a.every(x => getLegalMoves(x.position, x.position.turn, x.rule).length > 1));
});
