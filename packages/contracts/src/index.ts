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
    contentHash: z
      .string()
      .regex(/^sha256:[a-fA-F0-9]{64}$/)
      .transform((value) => value.toLowerCase()),
    upstreamReference: z.string().min(1),
  })
  .refine(
    ({ dataAvailableAt, fetchedAt }) =>
      Date.parse(dataAvailableAt) <= Date.parse(fetchedAt),
    {
      message: "dataAvailableAt cannot be later than fetchedAt",
      path: ["dataAvailableAt"],
    },
  );

export type SourceSnapshot = z.infer<typeof sourceSnapshotSchema>;
