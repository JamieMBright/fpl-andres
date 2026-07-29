import { performance } from "node:perf_hooks";

import { regretCases } from "../fixtures/load";
import { solveQuickPlan } from "../src/index";

const limits = {
  beamWidth: 16,
  candidateLimitPerPosition: 8,
  maxTransfers: 2,
} as const;
const warmupRuns = 20;
const measuredRuns = 200;

for (const fixture of regretCases) {
  for (let run = 0; run < warmupRuns; run += 1) {
    solveQuickPlan(fixture.input, limits);
  }
}

const durations: number[] = [];
let maximumRegret = 0;
let maximumStatesEvaluated = 0;
let maximumFrontierSize = 0;
for (let run = 0; run < measuredRuns; run += 1) {
  for (const fixture of regretCases) {
    const startedAt = performance.now();
    const result = solveQuickPlan(fixture.input, limits);
    durations.push(performance.now() - startedAt);
    const regret = fixture.highsOptimalNetPoints - result.netExpectedPoints;
    if (regret < -1e-8) {
      throw new Error(`${fixture.name} exceeded its HiGHS reference`);
    }
    maximumRegret = Math.max(maximumRegret, regret);
    maximumStatesEvaluated = Math.max(
      maximumStatesEvaluated,
      result.diagnostics.statesEvaluated,
    );
    maximumFrontierSize = Math.max(
      maximumFrontierSize,
      result.diagnostics.maximumFrontierSize,
    );
    if (regret > fixture.maxAllowedRegret + 1e-8) {
      throw new Error(`${fixture.name} exceeded its maximum allowed regret`);
    }
  }
}

durations.sort((left, right) => left - right);
const percentile = (fraction: number): number =>
  durations[
    Math.min(durations.length - 1, Math.ceil(fraction * durations.length) - 1)
  ]!;

console.log(
  JSON.stringify(
    {
      cases: regretCases.length,
      samples: durations.length,
      limits,
      latencyMilliseconds: {
        p50: percentile(0.5),
        p95: percentile(0.95),
        max: durations.at(-1),
      },
      maximumRegret,
      maximumStatesEvaluated,
      maximumFrontierSize,
    },
    null,
    2,
  ),
);
