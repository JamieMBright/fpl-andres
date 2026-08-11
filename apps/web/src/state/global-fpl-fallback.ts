import { z } from "zod";

import type { Freshness } from "./freshness";

const globalSnapshotSchema = z
  .object({
    schemaVersion: z.literal(1),
    generatedAt: z.iso.datetime(),
    bootstrap: z.object({
      elements: z.array(z.looseObject({})),
      element_types: z.array(z.looseObject({})),
      teams: z.array(z.looseObject({})),
      events: z.array(z.looseObject({})),
    }),
    fixtures: z.array(z.looseObject({})),
  })
  .strict();

export interface GlobalFplFallback {
  bootstrap: unknown;
  fixtures: unknown;
  freshness: Freshness;
}

export async function fetchGlobalFplFallback(
  fetchApi: typeof fetch,
  signal?: AbortSignal,
  now = Date.now(),
): Promise<GlobalFplFallback> {
  const response = await fetchApi("/fpl-global.json", {
    headers: { Accept: "application/json" },
    signal: signal ?? null,
  });
  if (!response.ok) throw new TypeError("global FPL fallback is unavailable");
  const parsed = globalSnapshotSchema.parse(await response.json());
  const capturedAt = Date.parse(parsed.generatedAt);
  return {
    bootstrap: parsed.bootstrap,
    fixtures: parsed.fixtures,
    freshness: {
      capturedAt,
      stale: true,
      ageSeconds: Math.max(0, Math.round((now - capturedAt) / 1_000)),
    },
  };
}
