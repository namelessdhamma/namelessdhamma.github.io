export const DIFFICULTY = Object.freeze({
  easy: Object.freeze({
    timeBudgetMs: 80,
    maxDepth: 3,
    regretBand: 35,
    openingRegretBand: 220,
    personaWeight: 0.6,
    openingPersonaWeight: 6,
    openingCandidateLimit: 40,
    strategicNoise: 0.42,
    guardian: 'full'
  }),
  medium: Object.freeze({
    timeBudgetMs: 220,
    maxDepth: 5,
    regretBand: 16,
    openingRegretBand: 170,
    personaWeight: 0.6,
    openingPersonaWeight: 6,
    openingCandidateLimit: 30,
    strategicNoise: 0.16,
    guardian: 'full'
  }),
  hard: Object.freeze({
    timeBudgetMs: 650,
    maxDepth: 8,
    regretBand: 5,
    openingRegretBand: 120,
    personaWeight: 0.6,
    openingPersonaWeight: 6,
    openingCandidateLimit: 24,
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
