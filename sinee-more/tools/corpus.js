import { LIGHT, RULE_C, RULE_D, RULE_CD } from '../ai/constants.js';
import { createInitialPosition, applyMove, getLegalMoves } from '../ai/rules.js';

function createSeededRng(seed) {
  let x = seed >>> 0;
  return () => {
    x ^= x << 13; x >>>= 0;
    x ^= x >>> 17; x >>>= 0;
    x ^= x << 5; x >>>= 0;
    return x / 0x100000000;
  };
}

function stateKey(position, rule) {
  const board = position.board.map(stack =>
    stack.map(piece => `${piece.player[0]}${piece.rank}`).join('.')
  ).join('/');
  return [
    rule,
    position.turn,
    board,
    position.remaining.light.join(','),
    position.remaining.dark.join(',')
  ].join('|');
}

export function buildQualificationCorpus({ count = 100, seed = 0x51eaea } = {}) {
  const rng = createSeededRng(seed);
  const rules = [RULE_C, RULE_D, RULE_CD];
  const found = new Map();

  for (let attempt = 0; found.size < count && attempt < count * 500; attempt += 1) {
    const rule = rules[attempt % rules.length];
    let position = createInitialPosition(attempt % 2 ? 'dark' : LIGHT);
    const targetPlies = 2 + Math.floor(rng() * 8);

    for (let ply = 0; ply < targetPlies && position.status === 'playing'; ply += 1) {
      const legal = getLegalMoves(position, position.turn, rule);
      if (!legal.length) break;
      const move = legal[Math.floor(rng() * legal.length)];
      position = applyMove(position, move, rule);
    }

    if (position.status !== 'playing') continue;
    if (getLegalMoves(position, position.turn, rule).length <= 1) continue;
    const key = stateKey(position, rule);
    if (!found.has(key)) {
      found.set(key, {
        name: `corpus-${String(found.size + 1).padStart(3, '0')}`,
        rule,
        position,
        key
      });
    }
  }

  if (found.size < count) {
    throw new Error(`unable to build corpus: requested ${count}, got ${found.size}`);
  }
  return [...found.values()];
}

export { stateKey as corpusStateKey };
