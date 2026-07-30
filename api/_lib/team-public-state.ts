import { createHash } from "node:crypto";

import {
  publicTeamStateSchema,
  type PlayerIdentity,
  type PublicTeamState,
} from "@fpl-andres/contracts";
import { z } from "zod";

const entrySchema = z
  .object({
    id: z.int().min(1).max(4_294_967_295),
    name: z.string().trim().min(1).max(100),
    started_event: z.int().min(1).max(38),
    current_event: z.int().min(1).max(38),
    last_deadline_bank: z.int().nonnegative(),
    last_deadline_value: z.int().nonnegative(),
    last_deadline_total_transfers: z.int().nonnegative(),
  })
  .passthrough();

const picksSchema = z
  .object({
    active_chip: z.string().trim().min(1).max(50).nullable(),
    entry_history: z
      .object({
        event: z.int().min(1).max(38),
        bank: z.int().nonnegative(),
        value: z.int().nonnegative(),
        event_transfers: z.int().nonnegative(),
        event_transfers_cost: z.int().nonnegative(),
      })
      .passthrough(),
    picks: z.array(
      z
        .object({
          element: z.int().positive(),
          position: z.int().min(1).max(15),
          multiplier: z.int().min(0).max(3),
          is_captain: z.boolean(),
          is_vice_captain: z.boolean(),
        })
        .passthrough(),
    ),
  })
  .passthrough();

const timestampSchema = z.iso.datetime();

export class TeamPublicStateContractError extends Error {
  override name = "TeamPublicStateContractError";
  override readonly cause?: unknown;
  constructor(message: string, options?: { cause?: unknown }) {
    super(message);
    if (options?.cause !== undefined) {
      this.cause = options.cause;
    }
  }
}

interface AssembleTeamPublicStateInput {
  entryBytes: Uint8Array;
  entryFetchedAt: string;
  picksBytes: Uint8Array;
  picksFetchedAt: string;
  stateSourceBytes: Uint8Array;
  stateSourceFetchedAt: string;
  stateAsOf: string;
  identities?: ReadonlyMap<number, PlayerIdentity>;
}

export function assembleTeamPublicState({
  entryBytes,
  entryFetchedAt,
  picksBytes,
  picksFetchedAt,
  stateSourceBytes,
  stateSourceFetchedAt,
  stateAsOf,
  identities,
}: AssembleTeamPublicStateInput): PublicTeamState {
  const validatedStateAsOf = timestampSchema.parse(stateAsOf);
  const validatedEntryFetchedAt = timestampSchema.parse(entryFetchedAt);
  const validatedPicksFetchedAt = timestampSchema.parse(picksFetchedAt);
  const validatedStateSourceFetchedAt =
    timestampSchema.parse(stateSourceFetchedAt);
  if (Date.parse(validatedEntryFetchedAt) < Date.parse(validatedStateAsOf)) {
    throw new TeamPublicStateContractError(
      "entry evidence cannot predate stateAsOf",
    );
  }
  if (Date.parse(validatedPicksFetchedAt) < Date.parse(validatedStateAsOf)) {
    throw new TeamPublicStateContractError(
      "picks evidence cannot predate stateAsOf",
    );
  }
  if (
    Date.parse(validatedStateSourceFetchedAt) < Date.parse(validatedStateAsOf)
  ) {
    throw new TeamPublicStateContractError(
      "deadline evidence cannot predate stateAsOf",
    );
  }
  const entry = parseJsonBytes(entryBytes, entrySchema, "entry");
  const picks = parseJsonBytes(picksBytes, picksSchema, "picks");

  if (entry.current_event !== picks.entry_history.event) {
    throw new TeamPublicStateContractError("entry and picks event disagree");
  }
  if (entry.last_deadline_bank !== picks.entry_history.bank) {
    throw new TeamPublicStateContractError("entry and picks bank disagree");
  }
  if (entry.last_deadline_value !== picks.entry_history.value) {
    throw new TeamPublicStateContractError("entry and picks value disagree");
  }

  return publicTeamStateSchema.parse({
    entryId: entry.id,
    event: entry.current_event,
    bankTenths: entry.last_deadline_bank,
    squadValueTenths: entry.last_deadline_value,
    eventTransfers: picks.entry_history.event_transfers,
    eventTransferCostPoints: picks.entry_history.event_transfers_cost,
    totalTransfers: entry.last_deadline_total_transfers,
    activeChip: picks.active_chip,
    picks: picks.picks.map((pick) => ({
      elementId: pick.element,
      squadPosition: pick.position,
      multiplier: pick.multiplier,
      isCaptain: pick.is_captain,
      isViceCaptain: pick.is_vice_captain,
      identity: identities?.get(pick.element) ?? null,
    })),
    stateAsOf: validatedStateAsOf,
    dataAvailableAt: latestTimestamp(
      latestTimestamp(validatedEntryFetchedAt, validatedPicksFetchedAt),
      validatedStateSourceFetchedAt,
    ),
    evidenceLevel: "observed",
    sourceHashes: [
      hashBytes(entryBytes),
      hashBytes(picksBytes),
      hashBytes(stateSourceBytes),
    ].sort(),
  });
}

function parseJsonBytes<Schema extends z.ZodType>(
  bytes: Uint8Array,
  schema: Schema,
  label: string,
): z.infer<Schema> {
  let value: unknown;
  try {
    value = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch (error) {
    throw new TeamPublicStateContractError(
      `${label} bytes are not valid UTF-8 JSON`,
      {
        cause: error,
      },
    );
  }
  try {
    return schema.parse(value);
  } catch (error) {
    throw new TeamPublicStateContractError(
      `${label} payload failed its source contract`,
      {
        cause: error,
      },
    );
  }
}

function hashBytes(bytes: Uint8Array): string {
  return `sha256:${createHash("sha256").update(bytes).digest("hex")}`;
}

function latestTimestamp(left: string, right: string): string {
  return Date.parse(left) >= Date.parse(right) ? left : right;
}
