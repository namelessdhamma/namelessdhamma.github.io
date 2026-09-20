import test from 'node:test';
import assert from 'node:assert/strict';
import { LIGHT, DARK, RULE_C, RULE_D, RULE_CD } from '../ai/constants.js';
import { createInitialPosition } from '../ai/rules.js';
import {
  BASE_PROFILE,
  enumerateLadderPlans,
  maxCompatiblePlanCount,
  countGlobalLadderCapacity,
  evaluatePosition
} from '../ai/evaluation.js';

function positionWithPieces(pieces, turn = LIGHT) {
  const p = createInitialPosition(turn);
  for (const { player, rank, cell, under = false } of pieces) {
    const stack = p.board[cell];
    if (under) stack.unshift({ player, rank });
    else stack.push({ player, rank });
    p.remaining[player] = p.remaining[player].filter(x => x !== rank);
  }
  return p;
}

test('D ladder feasibility prefers a flexible center rank over an extreme center rank without a special ban', () => {
  const center5 = positionWithPieces([{ player: LIGHT, rank: 5, cell: 4 }]);
  const center9 = positionWithPieces([{ player: LIGHT, rank: 9, cell: 4 }]);

  const plans5 = enumerateLadderPlans(center5, LIGHT, [0,4,8], RULE_D);
  const plans9 = enumerateLadderPlans(center9, LIGHT, [0,4,8], RULE_D);

  assert.ok(plans5.length > 0);
  assert.equal(plans9.length, 0);
  assert.ok(
    evaluatePosition(center5, LIGHT, RULE_D, BASE_PROFILE) >
    evaluatePosition(center9, LIGHT, RULE_D, BASE_PROFILE)
  );
});

test('ladder plan enumeration records concrete required ranks', () => {
  const p = positionWithPieces([
    { player: LIGHT, rank: 2, cell: 0 },
    { player: LIGHT, rank: 7, cell: 1 },
    { player: LIGHT, rank: 8, cell: 3 }
  ]);
  const rowPlans = enumerateLadderPlans(p, LIGHT, [0,1,2], RULE_D);
  const colPlans = enumerateLadderPlans(p, LIGHT, [0,3,6], RULE_D);

  assert.deepEqual(rowPlans.map(x => x.requiredRanks), [[9]]);
  assert.deepEqual(colPlans.map(x => x.requiredRanks), [[9]]);
  assert.equal(maxCompatiblePlanCount([rowPlans, colPlans]), 1);
});

test('global ladder capacity accounts for shared remaining-rank conflicts', () => {
  const p = positionWithPieces([
    { player: LIGHT, rank: 2, cell: 0 },
    { player: LIGHT, rank: 7, cell: 1 },
    { player: LIGHT, rank: 8, cell: 3 }
  ]);
  const analysis = countGlobalLadderCapacity(p, LIGHT, RULE_D);
  assert.ok(analysis.activeLinePlans >= 2);
  assert.ok(analysis.compatibleActivePlans < analysis.activeLinePlans);
});

test('C values ownership of an irreversibly closed center cell', () => {
  const lightOwns = positionWithPieces([
    { player: DARK, rank: 2, cell: 4 },
    { player: LIGHT, rank: 9, cell: 4 }
  ]);
  const darkOwns = positionWithPieces([
    { player: LIGHT, rank: 2, cell: 4 },
    { player: DARK, rank: 9, cell: 4 }
  ]);
  assert.ok(
    evaluatePosition(lightOwns, LIGHT, RULE_C, BASE_PROFILE) >
    evaluatePosition(darkOwns, LIGHT, RULE_C, BASE_PROFILE)
  );
});

test('evaluation is pure and does not mutate the position', () => {
  const p = positionWithPieces([
    { player: LIGHT, rank: 3, cell: 0 },
    { player: DARK, rank: 5, cell: 4 }
  ]);
  const before = structuredClone(p);
  evaluatePosition(p, LIGHT, RULE_CD, BASE_PROFILE);
  assert.deepEqual(p, before);
});

test('CD accounts for stack closure while preserving ladder semantics', () => {
  const open = positionWithPieces([
    { player: LIGHT, rank: 2, cell: 0 },
    { player: LIGHT, rank: 5, cell: 1 }
  ]);
  const blocked = positionWithPieces([
    { player: LIGHT, rank: 2, cell: 0 },
    { player: LIGHT, rank: 5, cell: 1 },
    { player: LIGHT, rank: 6, cell: 2, under: true },
    { player: DARK, rank: 9, cell: 2 }
  ]);
  assert.ok(
    evaluatePosition(open, LIGHT, RULE_CD, BASE_PROFILE) >
    evaluatePosition(blocked, LIGHT, RULE_CD, BASE_PROFILE)
  );
});


test('D opening values maximum center flexibility and rank economy over a high blocking center', () => {
  const center5 = positionWithPieces([{ player: LIGHT, rank: 5, cell: 4 }], DARK);
  const center7 = positionWithPieces([{ player: LIGHT, rank: 7, cell: 4 }], DARK);
  assert.ok(
    evaluatePosition(center5, LIGHT, RULE_D, BASE_PROFILE) >
    evaluatePosition(center7, LIGHT, RULE_D, BASE_PROFILE),
    JSON.stringify({
      center5: evaluatePosition(center5, LIGHT, RULE_D, BASE_PROFILE),
      center7: evaluatePosition(center7, LIGHT, RULE_D, BASE_PROFILE)
    })
  );
});


test('non-terminal evaluation remains zero-sum symmetric', () => {
  const p = positionWithPieces([
    { player: LIGHT, rank: 3, cell: 0 },
    { player: DARK, rank: 6, cell: 4 },
    { player: LIGHT, rank: 5, cell: 8 }
  ], DARK);
  for (const rule of [RULE_C, RULE_D, RULE_CD]) {
    const light = evaluatePosition(p, LIGHT, rule, BASE_PROFILE);
    const dark = evaluatePosition(p, DARK, rule, BASE_PROFILE);
    assert.ok(Math.abs(light + dark) < 1e-9, `${rule}: ${light} / ${dark}`);
  }
});
