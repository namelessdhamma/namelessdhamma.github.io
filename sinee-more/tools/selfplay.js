import { LIGHT, DARK } from '../ai/constants.js';
import { createInitialPosition, applyMove, getLegalMoves } from '../ai/rules.js';

function unwrapChoice(choice) {
  if (!choice) return { move: null, metrics: null };
  if (choice.move) return { move: choice.move, metrics: choice.metrics ?? null };
  return { move: choice, metrics: choice.metrics ?? null };
}

export function runGame({
  rule,
  lightAgent,
  darkAgent,
  firstPlayer = LIGHT,
  maxPlies = 40
}) {
  let position = createInitialPosition(firstPlayer);
  const moves = [];

  while (position.status === 'playing' && moves.length < maxPlies) {
    const agent = position.turn === LIGHT ? lightAgent : darkAgent;
    const started = performance.now();
    const raw = agent.choose(position, { rule, getLegalMoves });
    const elapsedMs = performance.now() - started;
    const { move, metrics } = unwrapChoice(raw);
    if (!move) break;

    const player = position.turn;
    const next = applyMove(position, move, rule);
    if (!next) throw new Error(`agent returned illegal move: ${JSON.stringify(move)}`);
    position = next;
    moves.push({ move, elapsedMs, player, metrics });
  }

  const result = position.status === 'win' ? position.winner : 'draw';
  return { result, plies: moves.length, moves, position };
}

export function runMatchup({
  rule,
  agentA,
  agentB,
  games = 2,
  maxPlies = 40
}) {
  const reports = [];
  for (let i = 0; i < games; i += 1) {
    const swap = i % 2 === 1;
    reports.push(runGame({
      rule,
      lightAgent: swap ? agentB : agentA,
      darkAgent: swap ? agentA : agentB,
      firstPlayer: i % 4 < 2 ? LIGHT : DARK,
      maxPlies
    }));
  }
  return {
    games: reports.length,
    reports,
    results: reports.reduce((acc, report) => {
      acc[report.result] = (acc[report.result] ?? 0) + 1;
      return acc;
    }, { [LIGHT]: 0, [DARK]: 0, draw: 0 })
  };
}
