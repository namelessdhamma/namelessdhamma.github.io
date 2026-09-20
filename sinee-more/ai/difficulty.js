export const DIFFICULTY = Object.freeze({
  easy: Object.freeze({
    timeBudgetMs: 80,
    maxDepth: 3,
    regretBand: 35,
    strategicNoise: 0.24,
    guardian: 'full'
  }),
  medium: Object.freeze({
    timeBudgetMs: 220,
    maxDepth: 5,
    regretBand: 16,
    strategicNoise: 0.10,
    guardian: 'full'
  }),
  hard: Object.freeze({
    timeBudgetMs: 650,
    maxDepth: 8,
    regretBand: 5,
    strategicNoise: 0.03,
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
