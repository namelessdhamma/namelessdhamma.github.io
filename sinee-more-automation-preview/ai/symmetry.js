import { LIGHT, DARK } from './constants.js';

export const TRANSFORMS = Object.freeze([
  Object.freeze([0,1,2,3,4,5,6,7,8]),
  Object.freeze([2,5,8,1,4,7,0,3,6]),
  Object.freeze([8,7,6,5,4,3,2,1,0]),
  Object.freeze([6,3,0,7,4,1,8,5,2]),
  Object.freeze([2,1,0,5,4,3,8,7,6]),
  Object.freeze([6,7,8,3,4,5,0,1,2]),
  Object.freeze([0,3,6,1,4,7,2,5,8]),
  Object.freeze([8,5,2,7,4,1,6,3,0])
]);

const INVERSES = TRANSFORMS.map(map => {
  const inverse = Array(9);
  for (let source = 0; source < 9; source += 1) inverse[map[source]] = source;
  return inverse;
});

export function transformMove(move, transformId) {
  if (!move) return null;
  const map = TRANSFORMS[transformId];
  if (!map) throw new RangeError(`invalid transform: ${transformId}`);
  return { ...move, cell: map[move.cell] };
}

export function inverseTransformMove(move, transformId) {
  if (!move) return null;
  const inverse = INVERSES[transformId];
  if (!inverse) throw new RangeError(`invalid transform: ${transformId}`);
  return { ...move, cell: inverse[move.cell] };
}

export function transformPosition(position, transformId) {
  const map = TRANSFORMS[transformId];
  if (!map) throw new RangeError(`invalid transform: ${transformId}`);
  const board = Array.from({ length: 9 }, () => []);
  for (let source = 0; source < 9; source += 1) {
    board[map[source]] = position.board[source].map(piece => ({ ...piece }));
  }
  return {
    ...position,
    board,
    remaining: {
      [LIGHT]: [...position.remaining[LIGHT]],
      [DARK]: [...position.remaining[DARK]]
    },
    winLine: position.winLine ? position.winLine.map(cell => map[cell]) : null
  };
}

function serialize(position, rule) {
  const board = position.board.map(stack =>
    stack.map(piece => `${piece.player === LIGHT ? 'L' : 'D'}${piece.rank}`).join('.')
  ).join('/');
  return [
    rule,
    position.turn,
    position.status,
    position.winner ?? '-',
    board,
    position.remaining[LIGHT].join(','),
    position.remaining[DARK].join(',')
  ].join('|');
}

export function canonicalize(position, rule) {
  let bestKey = null;
  let bestTransform = 0;
  for (let transformId = 0; transformId < TRANSFORMS.length; transformId += 1) {
    const key = serialize(transformPosition(position, transformId), rule);
    if (bestKey === null || key < bestKey) {
      bestKey = key;
      bestTransform = transformId;
    }
  }
  return { key: bestKey, transformId: bestTransform };
}

export function rawPositionKey(position, rule) {
  return serialize(position, rule);
}
