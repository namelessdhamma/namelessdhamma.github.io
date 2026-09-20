import test from 'node:test';
import assert from 'node:assert/strict';
import { LIGHT, DARK, RULE_C, RULE_D, RULE_CD } from '../ai/constants.js';
import { createInitialPosition, applyMove, getLegalMoves } from '../ai/rules.js';
import {
  getImmediateWins, getImmediateThreatCells, getSafeMoves, getTacticalCandidates
} from '../ai/guardian.js';
import {
  immediateWinFixture, immediateBlockFixture,
  increasingLadderFixture, decreasingLadderFixture
} from '../fixtures/regressions.js';
import { buildQualificationCorpus } from '../tools/corpus.js';

function sameMove(a, b) {
  return a.player === b.player && a.rank === b.rank && a.cell === b.cell;
}

test('guardian returns immediate wins before style preferences', () => {
  for (const fx of [
    immediateWinFixture(),
    increasingLadderFixture(),
    decreasingLadderFixture()
  ]) {
    const result = getTacticalCandidates(fx.position, fx.position.turn, fx.rule);
    assert.equal(result.tier, 'WIN_NOW', fx.name);
    assert.ok(result.moves.some(move => sameMove(move, fx.winningMove)), fx.name);
  }
});

test('guardian removes moves that allow an immediate opponent win when a safe move exists', () => {
  const fx = immediateBlockFixture();
  const safe = getSafeMoves(fx.position, fx.position.turn, fx.rule);
  assert.ok(safe.length > 0);
  for (const move of safe) {
    const next = applyMove(fx.position, move, fx.rule);
    assert.equal(getImmediateWins(next, next.turn, fx.rule).length, 0);
  }
  const result = getTacticalCandidates(fx.position, fx.position.turn, fx.rule);
  assert.equal(result.tier, 'MUST_DEFEND');
  assert.deepEqual(result.moves, safe);
});

test('guardian identifies an unanswerable locked double threat as FORCING', () => {
  let p = createInitialPosition(LIGHT);
  p = applyMove(p, { player: LIGHT, rank: 1, cell: 0 }, RULE_C);
  p = applyMove(p, { player: DARK, rank: 1, cell: 3 }, RULE_C);
  p = applyMove(p, { player: LIGHT, rank: 2, cell: 5 }, RULE_C);
  p = applyMove(p, { player: DARK, rank: 2, cell: 7 }, RULE_C);

  assert.deepEqual(getImmediateWins(p, LIGHT, RULE_C), []);

  const result = getTacticalCandidates(p, p.turn, RULE_C);
  assert.equal(result.tier, 'FORCING');
  assert.ok(
    result.moves.some(move => move.cell === 2 && move.rank === 9),
    JSON.stringify(result.moves)
  );

  const forcingMove = result.moves.find(move => move.cell === 2 && move.rank === 9);
  const next = applyMove(p, forcingMove, RULE_C);
  assert.ok(getImmediateWins(next, LIGHT, RULE_C).length >= 2);

  for (const reply of getLegalMoves(next, next.turn, RULE_C)) {
    const afterReply = applyMove(next, reply, RULE_C);
    if (afterReply.status === 'win') {
      assert.equal(afterReply.winner, LIGHT);
    } else {
      assert.ok(
        getImmediateWins(afterReply, LIGHT, RULE_C).length > 0,
        JSON.stringify({ forcingMove, reply })
      );
    }
  }
});

test('guardian always returns legal candidates across C D and CD', () => {
  for (const rule of [RULE_C, RULE_D, RULE_CD]) {
    const p = createInitialPosition(LIGHT);
    const result = getTacticalCandidates(p, LIGHT, rule);
    assert.ok(result.moves.length > 0);
    assert.ok(['SAFE', 'ALL_LEGAL'].includes(result.tier));
  }
});


test('early positions expose all legal moves as safe when opponent cannot yet have two visible tops', () => {
  for (const rule of [RULE_C, RULE_D, RULE_CD]) {
    const p = createInitialPosition(LIGHT);
    assert.deepEqual(getImmediateWins(p, LIGHT, rule), []);
    const safe = getSafeMoves(p, LIGHT, rule);
    assert.equal(safe.length, 81);
  }
});


test('immediate-win scan is restricted to cells that can complete a line', () => {
  let p = createInitialPosition(LIGHT);
  p = applyMove(p, { player: LIGHT, rank: 2, cell: 0 }, RULE_C);
  p = applyMove(p, { player: DARK, rank: 1, cell: 4 }, RULE_C);
  p = applyMove(p, { player: LIGHT, rank: 5, cell: 1 }, RULE_C);

  assert.deepEqual(
    getImmediateThreatCells(p, LIGHT, RULE_C),
    [2]
  );

  const wins = getImmediateWins(p, LIGHT, RULE_C);
  assert.ok(wins.length > 0);
  assert.ok(wins.every(move => move.cell === 2));
});

test('positions without two owned tops on a line have no immediate threat cells', () => {
  let p = createInitialPosition(LIGHT);
  p = applyMove(p, { player: LIGHT, rank: 5, cell: 4 }, RULE_D);
  assert.deepEqual(getImmediateThreatCells(p, LIGHT, RULE_D), []);
  assert.deepEqual(getImmediateWins(p, LIGHT, RULE_D), []);
});


test('safe-move scan returns all legal moves when opponent has no line threat', () => {
  let p = createInitialPosition(LIGHT);
  p = applyMove(p, { player: LIGHT, rank: 2, cell: 4 }, RULE_C);
  p = applyMove(p, { player: DARK, rank: 3, cell: 0 }, RULE_C);
  p = applyMove(p, { player: LIGHT, rank: 4, cell: 8 }, RULE_C);
  p = applyMove(p, { player: DARK, rank: 5, cell: 5 }, RULE_C);

  // Dark has two visible tops, but they do not share a winning line.
  assert.deepEqual(getImmediateThreatCells(p, DARK, RULE_C), []);
  const legal = getLegalMoves(p, p.turn, RULE_C);
  const safe = getSafeMoves(p, p.turn, RULE_C);
  assert.deepEqual(safe, legal);
});


test('expired Guardian budget skips optional forcing scan but never skips immediate wins', () => {
  const win = immediateWinFixture();
  const winResult = getTacticalCandidates(
    win.position,
    win.position.turn,
    win.rule,
    { deadline: 0, now: () => 1 }
  );
  assert.equal(winResult.tier, 'WIN_NOW');

  let p = createInitialPosition(LIGHT);
  p = applyMove(p, { player: LIGHT, rank: 1, cell: 0 }, RULE_C);
  p = applyMove(p, { player: DARK, rank: 1, cell: 3 }, RULE_C);
  p = applyMove(p, { player: LIGHT, rank: 2, cell: 5 }, RULE_C);
  p = applyMove(p, { player: DARK, rank: 2, cell: 7 }, RULE_C);

  const bounded = getTacticalCandidates(
    p,
    p.turn,
    RULE_C,
    { deadline: 0, now: () => 1 }
  );
  assert.equal(bounded.tier, 'SAFE');
  assert.equal(bounded.forcingSkipped, true);
});


test('optimized immediate-win scan matches brute-force rule execution', () => {
  const corpus = buildQualificationCorpus({ count: 36, seed: 0x9911aa });
  for (const item of corpus) {
    const player = item.position.turn;
    const expected = getLegalMoves(item.position, player, item.rule)
      .filter(move => {
        const next = applyMove(item.position, move, item.rule);
        return next?.status === 'win' && next.winner === player;
      })
      .map(move => `${move.cell}:${move.rank}`)
      .sort();

    const actual = getImmediateWins(item.position, player, item.rule)
      .map(move => `${move.cell}:${move.rank}`)
      .sort();

    assert.deepEqual(actual, expected, item.name);
  }
});


test('optimized safe-move scan matches brute one-ply defense', () => {
  const corpus = buildQualificationCorpus({ count: 24, seed: 0x551177 });
  for (const item of corpus) {
    const player = item.position.turn;
    const expected = getLegalMoves(item.position, player, item.rule)
      .filter(move => {
        const next = applyMove(item.position, move, item.rule);
        if (!next) return false;
        if (next.status === 'win') return next.winner === player;
        const opponent = player === LIGHT ? DARK : LIGHT;
        if (next.turn !== opponent) return true;
        return !getLegalMoves(next, opponent, item.rule).some(reply => {
          const after = applyMove(next, reply, item.rule);
          return after?.status === 'win' && after.winner === opponent;
        });
      })
      .map(move => `${move.cell}:${move.rank}`)
      .sort();

    const actual = getSafeMoves(item.position, player, item.rule)
      .map(move => `${move.cell}:${move.rank}`)
      .sort();

    assert.deepEqual(actual, expected, item.name);
  }
});


test('two opponent tops do not restrict safe moves when the third cell is un-coverable', () => {
  let p = createInitialPosition(LIGHT);
  p = applyMove(p, { player: LIGHT, rank: 9, cell: 2 }, RULE_C);
  p = applyMove(p, { player: DARK, rank: 1, cell: 0 }, RULE_C);
  p = applyMove(p, { player: LIGHT, rank: 1, cell: 4 }, RULE_C);
  p = applyMove(p, { player: DARK, rank: 2, cell: 1 }, RULE_C);

  assert.deepEqual(getImmediateThreatCells(p, DARK, RULE_C), [2]);
  assert.deepEqual(getImmediateWins(p, DARK, RULE_C), []);

  const legal = getLegalMoves(p, p.turn, RULE_C);
  const safe = getSafeMoves(p, p.turn, RULE_C);
  assert.deepEqual(safe, legal);
});
