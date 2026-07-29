import { z } from "zod";

export const evidenceLevelSchema = z.enum([
  "observed",
  "inferred",
  "experimental",
  "unavailable",
]);

export type EvidenceLevel = z.infer<typeof evidenceLevelSchema>;

export const sourceSnapshotSchema = z
  .object({
    source: z.enum(["fpl", "vaastav", "derived"]),
    fetchedAt: z.iso.datetime(),
    dataAvailableAt: z.iso.datetime(),
    contentHash: z.string().regex(/^sha256:[a-f0-9]{64}$/),
    upstreamReference: z.string().min(1),
  })
  .strict()
  .refine(
    ({ dataAvailableAt, fetchedAt }) =>
      Date.parse(dataAvailableAt) <= Date.parse(fetchedAt),
    {
      message: "dataAvailableAt cannot be later than fetchedAt",
      path: ["dataAvailableAt"],
    },
  );

export type SourceSnapshot = z.infer<typeof sourceSnapshotSchema>;

export function parseSourceSnapshot(input: unknown): SourceSnapshot {
  if (typeof input === "object" && input !== null && "contentHash" in input) {
    const candidate = input as Record<string, unknown>;
    if (typeof candidate.contentHash === "string") {
      return sourceSnapshotSchema.parse({
        ...candidate,
        contentHash: candidate.contentHash.toLowerCase(),
      });
    }
  }
  return sourceSnapshotSchema.parse(input);
}

const eventIdSchema = z.int().min(1).max(38);

export const fplEntrySchema = z
  .object({
    id: z.int().min(1).max(4_294_967_295),
    name: z.string().trim().min(1).max(100),
    startedEvent: eventIdSchema,
    currentEvent: eventIdSchema.nullable(),
    lastDeadlineBank: z.int().nonnegative().nullable(),
    lastDeadlineValue: z.int().nonnegative().nullable(),
    lastDeadlineTotalTransfers: z.int().nonnegative(),
  })
  .strict();

export type FplEntry = z.infer<typeof fplEntrySchema>;
