import { LIGHT } from '../ai/constants.js';
import { createInitialPosition, applyMove } from '../ai/rules.js';

export function playSequence(rule, moves, first = LIGHT) {
  let position = createInitialPosition(first);
  for (const [player, rank, cell] of moves) {
    const next = applyMove(position, { player, rank, cell }, rule);
    if (!next) throw new Error(`illegal fixture move: ${player} ${rank} @ ${cell}`);
    position = next;
  }
  return position;
}
