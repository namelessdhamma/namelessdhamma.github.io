import test from 'node:test';
import assert from 'node:assert/strict';
import { LIGHT, DARK, RULE_C, RULE_D, RULE_CD } from '../ai/constants.js';
import { createInitialPosition, applyMove, getLegalMoves, getWinner } from '../ai/rules.js';

test('empty position has 81 legal placements per player', () => {
  const p = createInitialPosition(LIGHT);
  assert.equal(getLegalMoves(p, LIGHT, RULE_C).length, 81);
});

test('C closes a cell after one cover', () => {
  let p = createInitialPosition(LIGHT);
  p = applyMove(p, { player: LIGHT, rank: 4, cell: 0 }, RULE_C);
  p = applyMove(p, { player: DARK, rank: 5, cell: 0 }, RULE_C);
  assert.equal(getLegalMoves(p, LIGHT, RULE_C).some(m => m.cell === 0), false);
});

test('D recognizes strictly increasing visible ranks', () => {
  let p = createInitialPosition(LIGHT);
  p = applyMove(p, { player: LIGHT, rank: 2, cell: 0 }, RULE_D);
  p = applyMove(p, { player: DARK, rank: 1, cell: 3 }, RULE_D);
  p = applyMove(p, { player: LIGHT, rank: 5, cell: 1 }, RULE_D);
  p = applyMove(p, { player: DARK, rank: 2, cell: 4 }, RULE_D);
  p = applyMove(p, { player: LIGHT, rank: 8, cell: 2 }, RULE_D);
  assert.deepEqual(getWinner(p, RULE_D), { player: LIGHT, line: [0, 1, 2] });
});

test('D recognizes strictly decreasing visible ranks', () => {
  let p = createInitialPosition(LIGHT);
  p = applyMove(p, { player: LIGHT, rank: 8, cell: 0 }, RULE_D);
  p = applyMove(p, { player: DARK, rank: 1, cell: 3 }, RULE_D);
  p = applyMove(p, { player: LIGHT, rank: 5, cell: 1 }, RULE_D);
  p = applyMove(p, { player: DARK, rank: 2, cell: 4 }, RULE_D);
  p = applyMove(p, { player: LIGHT, rank: 2, cell: 2 }, RULE_D);
  assert.deepEqual(getWinner(p, RULE_D), { player: LIGHT, line: [0, 1, 2] });
});

test('CD combines ladder win condition with stack depth 2', () => {
  let p = createInitialPosition(LIGHT);
  p = applyMove(p, { player: LIGHT, rank: 2, cell: 0 }, RULE_CD);
  p = applyMove(p, { player: DARK, rank: 4, cell: 0 }, RULE_CD);
  assert.equal(getLegalMoves(p, LIGHT, RULE_CD).some(m => m.cell === 0), false);
});
