import test from 'node:test';
import assert from 'node:assert/strict';
import { LIGHT, DARK, RULE_C } from '../ai/constants.js';
import { createInitialPosition, applyMove } from '../ai/rules.js';
import {
  TRANSFORMS, transformMove, inverseTransformMove,
  transformPosition, canonicalize
} from '../ai/symmetry.js';
import { searchFixedDepth } from '../ai/search.js';
import { evaluatePosition } from '../ai/evaluation.js';
import { buildQualificationCorpus } from '../tools/corpus.js';

const evalMaterial = (p, root) =>
  p.board.reduce((score, stack) => {
    const top = stack.at(-1);
    if (!top) return score;
    return score + (top.player === root ? top.rank : -top.rank);
  }, 0);

test('all move transforms round-trip', () => {
  const move = { player: LIGHT, rank: 7, cell: 1 };
  for (let id = 0; id < TRANSFORMS.length; id += 1) {
    assert.deepEqual(
      inverseTransformMove(transformMove(move, id), id),
      move
    );
  }
});

test('asymmetric stack order is preserved by transforms', () => {
  let p = createInitialPosition(LIGHT);
  p = applyMove(p, { player: LIGHT, rank: 2, cell: 0 }, RULE_C);
  p = applyMove(p, { player: DARK, rank: 5, cell: 0 }, RULE_C);
  const t = transformPosition(p, 1);
  const movedCell = TRANSFORMS[1][0];
  assert.deepEqual(t.board[movedCell], [
    { player: LIGHT, rank: 2 },
    { player: DARK, rank: 5 }
  ]);
});

test('all symmetric forms share one canonical key', () => {
  let p = createInitialPosition(LIGHT);
  p = applyMove(p, { player: LIGHT, rank: 2, cell: 0 }, RULE_C);
  p = applyMove(p, { player: DARK, rank: 5, cell: 1 }, RULE_C);
  const keys = TRANSFORMS.map((_, id) =>
    canonicalize(transformPosition(p, id), RULE_C).key
  );
  assert.equal(new Set(keys).size, 1);
});

test('symmetry-aware search preserves score and does not increase nodes', () => {
  let p = createInitialPosition(LIGHT);
  p = applyMove(p, { player: LIGHT, rank: 2, cell: 0 }, RULE_C);
  p = applyMove(p, { player: DARK, rank: 3, cell: 4 }, RULE_C);
  p = applyMove(p, { player: LIGHT, rank: 4, cell: 8 }, RULE_C);
  const plain = searchFixedDepth(p, {
    rule: RULE_C, rootPlayer: p.turn, depth: 3,
    evaluate: evalMaterial, useTable: true, useSymmetry: false
  });
  const sym = searchFixedDepth(p, {
    rule: RULE_C, rootPlayer: p.turn, depth: 3,
    evaluate: evalMaterial, useTable: true, useSymmetry: true
  });
  assert.equal(sym.score, plain.score);
  assert.ok(sym.nodes <= plain.nodes);
});


test('symmetry-enabled search matches plain search on rule-aware corpus positions', () => {
  const corpus = buildQualificationCorpus({ count: 9, seed: 0x51eaea });
  for (const item of corpus) {
    const evaluate = (position, root) =>
      evaluatePosition(position, root, item.rule);
    const plain = searchFixedDepth(item.position, {
      rule: item.rule,
      rootPlayer: item.position.turn,
      depth: 2,
      evaluate,
      useTable: true,
      useSymmetry: false
    });
    const symmetric = searchFixedDepth(item.position, {
      rule: item.rule,
      rootPlayer: item.position.turn,
      depth: 2,
      evaluate,
      useTable: true,
      useSymmetry: true
    });
    assert.equal(
      symmetric.score,
      plain.score,
      `${item.name}/${item.rule}: ${plain.score} vs ${symmetric.score}`
    );
  }
});
