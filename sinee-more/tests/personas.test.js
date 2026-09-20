import test from 'node:test';
import assert from 'node:assert/strict';
import { createRng } from '../ai/rng.js';
import {
  PERSONAS, scorePersonaMove, selectPersonaAtGameStart
} from '../ai/personas.js';
import { getTacticalCandidates } from '../ai/guardian.js';
import { buildQualificationCorpus } from '../tools/corpus.js';

function bestMove(position, rule, personaId) {
  const tactical = getTacticalCandidates(position, position.turn, rule);
  const scored = tactical.moves.map(move => ({
    move,
    score: scorePersonaMove(position, move, rule, personaId)
  })).sort((a, b) =>
    b.score - a.score ||
    a.move.cell - b.move.cell ||
    a.move.rank - b.move.rank
  );
  return scored[0]?.move ?? null;
}

function key(move) {
  return move ? `${move.cell}:${move.rank}` : '-';
}

test('seeded RNG is reproducible', () => {
  const a = createRng(12345);
  const b = createRng(12345);
  assert.deepEqual(
    Array.from({ length: 20 }, () => a()),
    Array.from({ length: 20 }, () => b())
  );
});

test('Mixed selects one known persona and avoids immediate repetition', () => {
  const rng = createRng(7);
  const first = selectPersonaAtGameStart('mixed', '', rng);
  const second = selectPersonaAtGameStart('mixed', first, rng);
  assert.ok(Object.hasOwn(PERSONAS, first));
  assert.ok(Object.hasOwn(PERSONAS, second));
  assert.notEqual(second, first);
  assert.equal(selectPersonaAtGameStart('hunter', first, rng), 'hunter');
});

test('persona preferences diverge across deterministic corpus', () => {
  const corpus = buildQualificationCorpus({ count: 100, seed: 0x51eaea });
  const ids = Object.keys(PERSONAS);
  const selections = new Map(ids.map(id => [id, []]));

  for (const item of corpus) {
    for (const id of ids) {
      selections.get(id).push(key(bestMove(item.position, item.rule, id)));
    }
  }

  const disagreements = [];
  for (let i = 0; i < ids.length; i += 1) {
    for (let j = i + 1; j < ids.length; j += 1) {
      let different = 0;
      for (let k = 0; k < corpus.length; k += 1) {
        if (selections.get(ids[i])[k] !== selections.get(ids[j])[k]) different += 1;
      }
      disagreements.push(different / corpus.length);
    }
  }

  assert.ok(disagreements.every(x => x >= 0.10), JSON.stringify(disagreements));
  assert.ok(disagreements.filter(x => x >= 0.20).length >= 3, JSON.stringify(disagreements));
});


test('nearby integer seeds do not collapse to the same first RNG band', () => {
  const first = Array.from({ length: 64 }, (_, index) =>
    createRng(index + 1)()
  );
  const low = first.filter(x => x < 0.25).length;
  const high = first.filter(x => x >= 0.75).length;
  assert.ok(low >= 6 && low <= 26, JSON.stringify({ low, first }));
  assert.ok(high >= 6 && high <= 26, JSON.stringify({ high, first }));
});
