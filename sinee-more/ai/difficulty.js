export const DIFFICULTY = Object.freeze({
  easy: Object.freeze({
    timeBudgetMs: 80,
    maxDepth: 3,
    regretBand: 35,
    openingRegretBand: 140,
    personaWeight: 0.6,
    openingPersonaWeight: 9,
    openingCandidateLimit: 40,
    strategicNoise: 0.25,
    strategicErrorRate: 0.90,
    strategicErrorSeverity: 1.00,
    forcingBudgetShare: 0.08,
    guardian: 'full'
  }),
  medium: Object.freeze({
    timeBudgetMs: 220,
    maxDepth: 5,
    regretBand: 16,
    openingRegretBand: 80,
    personaWeight: 0.6,
    openingPersonaWeight: 6,
    openingCandidateLimit: 30,
    strategicNoise: 0.10,
    strategicErrorRate: 0.58,
    strategicErrorSeverity: 0.85,
    forcingBudgetShare: 0.12,
    guardian: 'full'
  }),
  hard: Object.freeze({
    timeBudgetMs: 650,
    maxDepth: 8,
    regretBand: 3,
    openingRegretBand: 40,
    personaWeight: 0.35,
    openingPersonaWeight: 3,
    openingCandidateLimit: 12,
    strategicNoise: 0,
    strategicErrorRate: 0,
    strategicErrorSeverity: 0,
    forcingBudgetShare: 0.20,
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
