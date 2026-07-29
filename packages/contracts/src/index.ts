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

export const publicTeamPickSchema = z
  .object({
    elementId: z.int().positive(),
    squadPosition: z.int().min(1).max(15),
    multiplier: z.int().min(0).max(3),
    isCaptain: z.boolean(),
    isViceCaptain: z.boolean(),
  })
  .strict()
  .refine(({ isCaptain, isViceCaptain }) => !(isCaptain && isViceCaptain), {
    message: "a pick cannot be both captain and vice-captain",
  });

export type PublicTeamPick = z.infer<typeof publicTeamPickSchema>;

const sourceHashSchema = z.string().regex(/^sha256:[a-f0-9]{64}$/);

export const publicTeamStateSchema = z
  .object({
    entryId: z.int().positive(),
    event: eventIdSchema,
    bankTenths: z.int().nonnegative(),
    squadValueTenths: z.int().nonnegative(),
    eventTransfers: z.int().nonnegative(),
    eventTransferCostPoints: z.int().nonnegative(),
    totalTransfers: z.int().nonnegative(),
    activeChip: z.string().trim().min(1).max(50).nullable(),
    picks: z.array(publicTeamPickSchema),
    stateAsOf: z.iso.datetime(),
    dataAvailableAt: z.iso.datetime(),
    evidenceLevel: z.literal("observed"),
    sourceHashes: z.array(sourceHashSchema).min(1),
  })
  .strict()
  .superRefine((state, context) => {
    if (Date.parse(state.dataAvailableAt) < Date.parse(state.stateAsOf)) {
      context.addIssue({
        code: "custom",
        message: "public team evidence cannot predate stateAsOf",
        path: ["dataAvailableAt"],
      });
    }
    if (state.picks.length !== 15) {
      context.addIssue({
        code: "custom",
        message: "public team state requires exactly 15 picks",
        path: ["picks"],
      });
    }
    if (
      new Set(state.picks.map(({ squadPosition }) => squadPosition)).size !== 15
    ) {
      context.addIssue({
        code: "custom",
        message: "public team picks must occupy positions 1 through 15",
        path: ["picks"],
      });
    }
    if (new Set(state.picks.map(({ elementId }) => elementId)).size !== 15) {
      context.addIssue({
        code: "custom",
        message: "public team picks must contain 15 distinct elements",
        path: ["picks"],
      });
    }
    if (state.picks.filter(({ isCaptain }) => isCaptain).length !== 1) {
      context.addIssue({
        code: "custom",
        message: "public team state requires exactly one captain",
        path: ["picks"],
      });
    }
    if (state.picks.filter(({ isViceCaptain }) => isViceCaptain).length !== 1) {
      context.addIssue({
        code: "custom",
        message: "public team state requires exactly one vice-captain",
        path: ["picks"],
      });
    }
    const sortedUniqueHashes = [...new Set(state.sourceHashes)].sort();
    if (
      sortedUniqueHashes.length !== state.sourceHashes.length ||
      sortedUniqueHashes.some(
        (hash, index) => hash !== state.sourceHashes[index],
      )
    ) {
      context.addIssue({
        code: "custom",
        message: "source hashes must be sorted and unique",
        path: ["sourceHashes"],
      });
    }
  });

export type PublicTeamState = z.infer<typeof publicTeamStateSchema>;

export const managerTeamPlayerSchema = z
  .object({
    elementId: z.int().positive(),
    squadPosition: z.int().min(1).max(15),
    purchasePriceTenths: z.int().nonnegative(),
    sellingPriceTenths: z.int().nonnegative(),
  })
  .strict();

export type ManagerTeamPlayer = z.infer<typeof managerTeamPlayerSchema>;

export const queuedTransferSchema = z
  .object({
    elementOutId: z.int().positive(),
    elementInId: z.int().positive(),
    sellingPriceTenths: z.int().nonnegative(),
    purchasePriceTenths: z.int().nonnegative(),
  })
  .strict()
  .refine(({ elementInId, elementOutId }) => elementInId !== elementOutId, {
    message: "queued transfer must change the element",
  });

export type QueuedTransfer = z.infer<typeof queuedTransferSchema>;

const chipNameSchema = z.string().trim().min(1).max(50);

export const teamStateOverridesSchema = z
  .object({
    source: z.literal("manager"),
    basedOnStateAsOf: z.iso.datetime(),
    updatedAt: z.iso.datetime(),
    bankTenths: z.int().nonnegative().nullable(),
    availableFreeTransfers: z.int().nonnegative().nullable(),
    currentSquad: z.array(managerTeamPlayerSchema).nullable(),
    queuedTransfers: z.array(queuedTransferSchema).nullable(),
    availableChips: z.array(chipNameSchema).nullable(),
  })
  .strict()
  .superRefine((overrides, context) => {
    if (
      Date.parse(overrides.updatedAt) < Date.parse(overrides.basedOnStateAsOf)
    ) {
      context.addIssue({
        code: "custom",
        message: "updatedAt cannot predate basedOnStateAsOf",
        path: ["updatedAt"],
      });
    }
    if (
      overrides.bankTenths === null &&
      overrides.availableFreeTransfers === null &&
      overrides.currentSquad === null &&
      overrides.queuedTransfers === null &&
      overrides.availableChips === null
    ) {
      context.addIssue({
        code: "custom",
        message: "at least one manager override is required",
      });
    }
    if (overrides.currentSquad !== null) {
      if (overrides.currentSquad.length !== 15) {
        context.addIssue({
          code: "custom",
          message: "manager current squad requires exactly 15 players",
          path: ["currentSquad"],
        });
      }
      if (
        new Set(
          overrides.currentSquad.map(({ squadPosition }) => squadPosition),
        ).size !== 15
      ) {
        context.addIssue({
          code: "custom",
          message: "manager current squad must occupy positions 1 through 15",
          path: ["currentSquad"],
        });
      }
      if (
        new Set(overrides.currentSquad.map(({ elementId }) => elementId))
          .size !== 15
      ) {
        context.addIssue({
          code: "custom",
          message: "manager current squad must contain 15 distinct elements",
          path: ["currentSquad"],
        });
      }
    }
    if (overrides.queuedTransfers !== null) {
      const outgoing = overrides.queuedTransfers.map(
        ({ elementOutId }) => elementOutId,
      );
      const incoming = overrides.queuedTransfers.map(
        ({ elementInId }) => elementInId,
      );
      if (
        new Set(outgoing).size !== outgoing.length ||
        new Set(incoming).size !== incoming.length
      ) {
        context.addIssue({
          code: "custom",
          message: "queued transfer elements must be unique",
          path: ["queuedTransfers"],
        });
      }
      if (incoming.some((elementId) => outgoing.includes(elementId))) {
        context.addIssue({
          code: "custom",
          message: "queued incoming elements cannot already be outgoing",
          path: ["queuedTransfers"],
        });
      }
    }
    if (overrides.availableChips !== null) {
      const sortedUniqueChips = [...new Set(overrides.availableChips)].sort();
      if (
        sortedUniqueChips.length !== overrides.availableChips.length ||
        sortedUniqueChips.some(
          (chip, index) => chip !== overrides.availableChips?.[index],
        )
      ) {
        context.addIssue({
          code: "custom",
          message: "available chips must be sorted and unique",
          path: ["availableChips"],
        });
      }
    }
  });

export type TeamStateOverrides = z.infer<typeof teamStateOverridesSchema>;
