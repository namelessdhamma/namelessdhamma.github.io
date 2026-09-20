import { RULE_CD } from './constants.js';

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
    strategicErrorRate: 0.98,
    strategicErrorSeverity: 1.00,
    errorCandidateLimit: 6,
    cdErrorMultiplier: 1.04,
    cdSeverityMultiplier: 1.40,
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
    errorCandidateLimit: 5,
    cdErrorMultiplier: 1.28,
    cdSeverityMultiplier: 0.65,
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
    errorCandidateLimit: 4,
    cdErrorMultiplier: 1,
    cdSeverityMultiplier: 1,
    forcingBudgetShare: 0.20,
    guardian: 'full'
  })
});

export function resolveDifficulty(
  id = 'medium',
  timeBudgetOverrideMs = null,
  rule = null
) {
  const base = DIFFICULTY[id] ?? DIFFICULTY.medium;
  const strategicErrorRate = rule === RULE_CD
    ? Math.min(1, base.strategicErrorRate * base.cdErrorMultiplier)
    : base.strategicErrorRate;
  const strategicErrorSeverity = rule === RULE_CD
    ? base.strategicErrorSeverity * base.cdSeverityMultiplier
    : base.strategicErrorSeverity;

  return {
    ...base,
    strategicErrorRate,
    strategicErrorSeverity,
    timeBudgetMs: timeBudgetOverrideMs == null
      ? base.timeBudgetMs
      : Math.max(0, Number(timeBudgetOverrideMs))
  };
}
