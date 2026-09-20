import { LIGHT, DARK, RULE_C, RULE_D, RULE_CD } from '../ai/constants.js';
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

export function immediateWinFixture() {
  const rule = RULE_C;
  const position = playSequence(rule, [
    [LIGHT,1,0], [DARK,1,3], [LIGHT,2,1], [DARK,2,4]
  ]);
  return {
    name:'c-immediate-win',
    rule,
    position,
    winningMove:{ player:LIGHT, rank:3, cell:2 }
  };
}

export function immediateBlockFixture() {
  const rule = RULE_C;
  const position = playSequence(rule, [
    [LIGHT,1,0], [DARK,1,3], [LIGHT,2,1]
  ]);
  return { name:'c-immediate-block', rule, position, threatenedCell:2 };
}

export function increasingLadderFixture() {
  const rule = RULE_D;
  const position = playSequence(rule, [
    [LIGHT,2,0], [DARK,1,3], [LIGHT,5,1], [DARK,2,4]
  ]);
  return {
    name:'d-increasing-ladder',
    rule,
    position,
    winningMove:{ player:LIGHT, rank:8, cell:2 }
  };
}

export function decreasingLadderFixture() {
  const rule = RULE_D;
  const position = playSequence(rule, [
    [LIGHT,8,0], [DARK,1,3], [LIGHT,5,1], [DARK,2,4]
  ]);
  return {
    name:'d-decreasing-ladder',
    rule,
    position,
    winningMove:{ player:LIGHT, rank:2, cell:2 }
  };
}

export function closedStackFixture() {
  const rule = RULE_CD;
  const position = playSequence(rule, [
    [LIGHT,2,0], [DARK,4,0]
  ]);
  return { name:'cd-closed-stack', rule, position, closedCell:0 };
}
