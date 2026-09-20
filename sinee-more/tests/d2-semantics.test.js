import test from 'node:test';
import assert from 'node:assert/strict';
import { RULE_C, RULE_D, RULE_CD, LIGHT } from '../ai/constants.js';
import { createInitialPosition, applyMove, getLegalMoves } from '../ai/rules.js';
import { resolveDifficulty } from '../ai/difficulty.js';
import { selectSearchCandidates, collectDeliberateErrorCandidates } from '../ai/engine.js';
function afterTwoMoves(rule = RULE_D) {
  let p = createInitialPosition(LIGHT);
  p = applyMove(p, { player: 'light', rank: 5, cell: 4 }, rule);
  p = applyMove(p, { player: 'dark', rank: 4, cell: 0 }, rule);
  return p;
}
function keys(moves){return moves.map(m=>`${m.player}:${m.rank}:${m.cell}`).sort();}
for (const difficulty of ['easy','medium']) {
  test(`${difficulty} D deliberate search uses same non-opening root set as normal`, () => {
    const position = afterTwoMoves();
    const moves = getLegalMoves(position, position.turn, RULE_D);
    const policy = resolveDifficulty(difficulty, null, RULE_D);
    const common = {tacticalTier:'SAFE',tacticalMoves:moves,decisionMoves:moves,rule:RULE_D,policy,difficulty};
    const normal = selectSearchCandidates(position,{...common,deliberateError:false});
    const deliberate = selectSearchCandidates(position,{...common,deliberateError:true});
    assert.deepEqual(keys(deliberate), keys(normal));
  });
}
test('non-D deliberate searches remain bounded', () => {
  for (const rule of [RULE_C,RULE_CD]) {
    const position = afterTwoMoves(rule);
    const moves = getLegalMoves(position, position.turn, rule);
    const policy = resolveDifficulty('easy', null, rule);
    const deliberate = selectSearchCandidates(position,{tacticalTier:'SAFE',tacticalMoves:moves,decisionMoves:moves,rule,policy,deliberateError:true,difficulty:'easy'});
    assert.ok(deliberate.length <= policy.errorCandidateLimit);
  }
});
test('D deliberate candidates honor each tier own normal regret band', () => {
  const moves=[
    {player:'light',rank:1,cell:0},
    {player:'light',rank:2,cell:1},
    {player:'light',rank:3,cell:2},
    {player:'light',rank:4,cell:3}
  ];
  const root=[
    {move:moves[0],score:100},
    {move:moves[1],score:75},
    {move:moves[2],score:55},
    {move:moves[3],score:20}
  ];
  const mediumBand=resolveDifficulty('medium',null,RULE_D).regretBand;
  const easyBand=resolveDifficulty('easy',null,RULE_D).regretBand;
  const med=collectDeliberateErrorCandidates(root,moves,moves[0],0.85,true,mediumBand);
  const easy=collectDeliberateErrorCandidates(root,moves,moves[0],1.0,false,easyBand);
  assert.ok(med.every(x=>x.searchRegret > mediumBand));
  assert.ok(easy.every(x=>x.searchRegret > easyBand));
});
