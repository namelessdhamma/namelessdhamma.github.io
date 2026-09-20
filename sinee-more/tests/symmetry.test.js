import test from 'node:test';
import assert from 'node:assert/strict';
import { LIGHT, DARK, RULE_C } from '../ai/constants.js';
import { createInitialPosition, applyMove } from '../ai/rules.js';
import {
  TRANSFORMS, transformPosition, transformMove, inverseTransformMove, canonicalize
} from '../ai/symmetry.js';
import { searchFixedDepth, TranspositionTable } from '../ai/search.js';

function asymmetricPosition() {
  let p = createInitialPosition(LIGHT);
  p = applyMove(p, { player: LIGHT, rank: 2, cell: 0 }, RULE_C);
  p = applyMove(p, { player: DARK, rank: 4, cell: 1 }, RULE_C);
  p = applyMove(p, { player: LIGHT, rank: 6, cell: 4 }, RULE_C);
  p = applyMove(p, { player: DARK, rank: 7, cell: 0 }, RULE_C);
  return p;
}

const evalMaterial = (p, root) =>
  p.board.reduce((score, stack) => {
    const top = stack.at(-1);
    if (!top) return score;
    const location = stack === p.board[4] ? 0.1 : 0;
    return score + (top.player === root ? top.rank + location : -top.rank - location);
  }, 0);

test('all eight move transforms round-trip', () => {
  const move = { player: LIGHT, rank: 7, cell: 1 };
  assert.equal(TRANSFORMS.length, 8);
  for (let id = 0; id < 8; id += 1) {
    assert.deepEqual(inverseTransformMove(transformMove(move, id), id), move);
  }
});

test('transformPosition preserves asymmetric stack order', () => {
  const p = asymmetricPosition();
  const rotated = transformPosition(p, 1);
  assert.deepEqual(rotated.board[2], [
    { player: LIGHT, rank: 2 },
    { player: DARK, rank: 7 }
  ]);
  assert.deepEqual(rotated.remaining, p.remaining);
});

test('all symmetries share one canonical key', () => {
  const p = asymmetricPosition();
  const key = canonicalize(p, RULE_C).key;
  for (let id = 0; id < 8; id += 1) {
    assert.equal(canonicalize(transformPosition(p, id), RULE_C).key, key);
  }
});

test('TT best move maps back across symmetric positions', () => {
  const p = asymmetricPosition();
  const table = new TranspositionTable();
  const a = searchFixedDepth(p, {
    rule: RULE_C, rootPlayer: p.turn, depth: 2,
    evaluate: evalMaterial, table, useTable: true, useSymmetry: true
  });
  const rotated = transformPosition(p, 1);
  const b = searchFixedDepth(rotated, {
    rule: RULE_C, rootPlayer: rotated.turn, depth: 2,
    evaluate: evalMaterial, table, useTable: true, useSymmetry: true
  });
  assert.ok(b.ttHits > 0);
  assert.deepEqual(b.move, transformMove(a.move, 1));
});

test('symmetry canonicalization does not increase searched node count', () => {
  const p = asymmetricPosition();
  const plain = searchFixedDepth(p, {
    rule: RULE_C, rootPlayer: p.turn, depth: 3,
    evaluate: evalMaterial, useTable: true, useSymmetry: false,
    table: new TranspositionTable()
  });
  const symmetric = searchFixedDepth(p, {
    rule: RULE_C, rootPlayer: p.turn, depth: 3,
    evaluate: evalMaterial, useTable: true, useSymmetry: true,
    table: new TranspositionTable()
  });
  assert.equal(symmetric.score, plain.score);
  assert.ok(symmetric.nodes <= plain.nodes);
});
