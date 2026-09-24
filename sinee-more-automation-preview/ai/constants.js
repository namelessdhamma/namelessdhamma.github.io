export const LIGHT = 'light';
export const DARK = 'dark';
export const RULE_C = 'C';
export const RULE_D = 'D';
export const RULE_CD = 'CD';

export const LINES = Object.freeze([
  Object.freeze([0,1,2]), Object.freeze([3,4,5]), Object.freeze([6,7,8]),
  Object.freeze([0,3,6]), Object.freeze([1,4,7]), Object.freeze([2,5,8]),
  Object.freeze([0,4,8]), Object.freeze([2,4,6])
]);

export const RANKS = Object.freeze([1,2,3,4,5,6,7,8,9]);

export function otherPlayer(player) {
  return player === LIGHT ? DARK : LIGHT;
}

export function usesStack2(rule) {
  return rule === RULE_C || rule === RULE_CD;
}

export function usesLadder(rule) {
  return rule === RULE_D || rule === RULE_CD;
}
