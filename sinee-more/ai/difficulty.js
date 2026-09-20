export const DIFFICULTY = Object.freeze({
  easy: Object.freeze({
    timeBudgetMs: 80,
    maxDepth: 3,
    regretBand: 50,
    openingRegretBand: 220,
    personaWeight: 0.85,
    openingPersonaWeight: 2.2,
    strategicNoise: 0.30,
    guardian: 'full'
  }),
  medium: Object.freeze({
    timeBudgetMs: 220,
    maxDepth: 5,
    regretBand: 28,
    openingRegretBand: 170,
    personaWeight: 0.55,
    openingPersonaWeight: 1.8,
    strategicNoise: 0.18,
    guardian: 'full'
  }),
  hard: Object.freeze({
    timeBudgetMs: 650,
    maxDepth: 8,
    regretBand: 1.5,
    openingRegretBand: 120,
    personaWeight: 0.22,
    openingPersonaWeight: 1.5,
    strategicNoise: 0,
    guardian: 'full'
  })
});

export function resolveDifficulty(id = 'medium', timeBudgetOverrideMs = null) {
  const base = DIFFICULTY[id] ?? DIFFICULTY.medium;
  return {
    ...base,
    timeBudgetMs: timeBudgetOverrideMs == null
      ? base.timeBudgetMs
      : Math.max(0, Number(timeBudgetOverrideMs))
  };
}
