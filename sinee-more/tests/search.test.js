import test from 'node:test';
import assert from 'node:assert/strict';
import { RULE_C, LIGHT } from '../ai/constants.js';
import { createInitialPosition } from '../ai/rules.js';
import {
  searchFixedDepth, TranspositionTable, TT_LOWER, makeSearchKey
} from '../ai/search.js';

const evalMaterial = (p, root) =>
  p.board.reduce((score, stack) => {
    const top = stack.at(-1);
    if (!top) return score;
    return score + (top.player === root ? top.rank : -top.rank);
  }, 0);

test('cached and uncached alpha-beta agree deterministically', () => {
  const position = createInitialPosition(LIGHT);
  const a = searchFixedDepth(position, {
    rule: RULE_C, rootPlayer: LIGHT, depth: 2,
    evaluate: evalMaterial, useTable: false
  });
  const b = searchFixedDepth(position, {
    rule: RULE_C, rootPlayer: LIGHT, depth: 2,
    evaluate: evalMaterial, useTable: true,
    table: new TranspositionTable()
  });
  assert.equal(b.score, a.score);
  assert.deepEqual(b.move, a.move);
});

test('lower-bound cutoff entry is not reused as an exact value', () => {
  const position = createInitialPosition(LIGHT);
  const table = new TranspositionTable();

  searchFixedDepth(position, {
    rule: RULE_C, rootPlayer: LIGHT, depth: 1,
    evaluate: evalMaterial, useTable: true, table,
    alpha: -Infinity, beta: 0
  });

  const entry = table.get(makeSearchKey(position, RULE_C));
  assert.equal(entry.flag, TT_LOWER);
  assert.equal(entry.score, 1);

  const full = searchFixedDepth(position, {
    rule: RULE_C, rootPlayer: LIGHT, depth: 1,
    evaluate: evalMaterial, useTable: true, table,
    alpha: -Infinity, beta: Infinity
  });
  assert.equal(full.score, 9);
  assert.deepEqual(full.move, { player: LIGHT, rank: 9, cell: 0 });
});
