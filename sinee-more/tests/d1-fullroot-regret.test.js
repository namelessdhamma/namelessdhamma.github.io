import test from 'node:test';
import assert from 'node:assert/strict';
import { RULE_C, RULE_D, LIGHT } from '../ai/constants.js';
import { createInitialPosition, applyMove, getLegalMoves } from '../ai/rules.js';
import { resolveDifficulty } from '../ai/difficulty.js';
import {
  selectSearchCandidates,
  collectDeliberateErrorCandidates
} from '../ai/engine.js';

function afterTwoMoves() {
  let p = createInitialPosition(LIGHT);
  p = applyMove(p, { player: 'light', rank: 5, cell: 4 }, RULE_D);
  p = applyMove(p, { player: 'dark', rank: 4, cell: 0 }, RULE_D);
  return p;
}

function keys(moves) {
  return moves.map(m => `${m.player}:${m.rank}:${m.cell}`).sort();
}

test('Medium D deliberate error searches the same non-opening root set as normal play', () => {
  const position = afterTwoMoves();
  const moves = getLegalMoves(position, position.turn, RULE_D);
  const policy = resolveDifficulty('medium', 220, RULE_D);
  const common = {
    tacticalTier: 'SAFE',
    tacticalMoves: moves,
    decisionMoves: moves,
    rule: RULE_D,
    policy,
    difficulty: 'medium'
  };
  const normal = selectSearchCandidates(position, {
    ...common,
    deliberateError: false
  });
  const deliberate = selectSearchCandidates(position, {
    ...common,
    deliberateError: true
  });
  assert.deepEqual(keys(deliberate), keys(normal));
  assert.equal(deliberate.length, moves.length);
});

test('Easy and non-D deliberate errors remain bounded', () => {
  const position = afterTwoMoves();
  const dMoves = getLegalMoves(position, position.turn, RULE_D);
  const easyPolicy = resolveDifficulty('easy', 80, RULE_D);
  const easy = selectSearchCandidates(position, {
    tacticalTier: 'SAFE',
    tacticalMoves: dMoves,
    decisionMoves: dMoves,
    rule: RULE_D,
    policy: easyPolicy,
    deliberateError: true,
    difficulty: 'easy'
  });
  assert.ok(easy.length <= easyPolicy.errorCandidateLimit);
  assert.ok(easy.length < dMoves.length);

  const cPolicy = resolveDifficulty('medium', 220, RULE_C);
  const cMoves = getLegalMoves(position, position.turn, RULE_C);
  const mediumC = selectSearchCandidates(position, {
    tacticalTier: 'SAFE',
    tacticalMoves: cMoves,
    decisionMoves: cMoves,
    rule: RULE_C,
    policy: cPolicy,
    deliberateError: true,
    difficulty: 'medium'
  });
  assert.ok(mediumC.length <= cPolicy.errorCandidateLimit);
});

test('Medium D terminal protection preserves proven wins and excludes forced losses', () => {
  const moves = [
    { player: 'light', rank: 1, cell: 0 },
    { player: 'light', rank: 2, cell: 1 },
    { player: 'light', rank: 3, cell: 2 }
  ];
  const win = collectDeliberateErrorCandidates([
    { move: moves[0], score: 100010 },
    { move: moves[1], score: 80 },
    { move: moves[2], score: -100010 }
  ], moves, moves[0], 0.85, true);
  assert.deepEqual(win.map(x => x.move), [moves[0]]);

  const guarded = collectDeliberateErrorCandidates([
    { move: moves[0], score: 100 },
    { move: moves[1], score: 50 },
    { move: moves[2], score: -100010 }
  ], moves, moves[0], 0.85, true);
  assert.ok(guarded.every(x => x.move !== moves[2]));
});

test('Medium D deliberate candidates must fall outside the normal regret band', () => {
  const moves = [
    { player: 'light', rank: 1, cell: 0 },
    { player: 'light', rank: 2, cell: 1 },
    { player: 'light', rank: 3, cell: 2 }
  ];
  const candidates = collectDeliberateErrorCandidates([
    { move: moves[0], score: 100 },
    { move: moves[1], score: 90 },
    { move: moves[2], score: 70 }
  ], moves, moves[0], 0.85, true, 16);
  assert.deepEqual(candidates.map(x => x.move), [moves[2]]);

  const none = collectDeliberateErrorCandidates([
    { move: moves[0], score: 100 },
    { move: moves[1], score: 90 }
  ], moves.slice(0, 2), moves[0], 0.85, true, 16);
  assert.deepEqual(none, []);
});
