import type { TeamStateOverrides } from "@fpl-andres/contracts";
import { ZodError } from "zod";

import { TeamStateOverridesConflictError } from "../../state/team-state-overrides";

/**
 * Parsing and formatting for the manager corrections form.
 *
 * Audit item #114. `TeamStateCorrections.tsx` was 720 lines, of which eight
 * pure functions were reachable only by rendering the component and typing into
 * it. They are the part most worth testing directly: every one of them turns
 * something a person typed into a number the optimiser will trust.
 *
 * Every parser takes the field id so a failure can move focus to the input that
 * caused it. An error message that names a field the user cannot find is only
 * marginally better than no message.
 */

export interface TransferDraft {
  key: number;
  elementOutId: string;
  elementInId: string;
  sellingPrice: string;
  purchasePrice: string;
}

export type TransferField = Exclude<keyof TransferDraft, "key">;

export interface CorrectionError {
  message: string;
  fieldId?: string;
}

export class CorrectionInputError extends Error {
  constructor(
    message: string,
    readonly fieldId?: string,
  ) {
    super(message);
    this.name = "CorrectionInputError";
  }
}

/** FPL prices in tenths, so "4.5" is 45 and never 4.5. */
export function parseOptionalTenths(
  value: string,
  label: string,
  fieldId?: string,
): number | null {
  const normalized = value.trim();
  if (normalized === "") return null;
  const match = /^(\d+)(?:\.(\d))?$/.exec(normalized);
  if (!match) {
    throw new CorrectionInputError(
      `${label} must be a non-negative amount with at most 1 decimal place.`,
      fieldId,
    );
  }
  const whole = Number(match[1]);
  const decimal = Number(match[2] ?? "0");
  const tenths = whole * 10 + decimal;
  if (!Number.isSafeInteger(tenths)) {
    throw new CorrectionInputError(
      `${label} is outside the supported range.`,
      fieldId,
    );
  }
  return tenths;
}

export function parseOptionalInteger(
  value: string,
  label: string,
  fieldId?: string,
): number | null {
  const normalized = value.trim();
  if (normalized === "") return null;
  if (!/^\d+$/.test(normalized)) {
    throw new CorrectionInputError(
      `${label} must be a non-negative integer.`,
      fieldId,
    );
  }
  const parsed = Number(normalized);
  if (!Number.isSafeInteger(parsed)) {
    throw new CorrectionInputError(
      `${label} is outside the supported range.`,
      fieldId,
    );
  }
  return parsed;
}

export function parseRequiredInteger(
  value: string,
  label: string,
  fieldId: string,
): number {
  const parsed = parseOptionalInteger(value, label, fieldId);
  if (parsed === null || parsed < 1 || parsed > 4_294_967_295) {
    throw new CorrectionInputError(
      `${label} must be a positive FPL element ID.`,
      fieldId,
    );
  }
  return parsed;
}

export function parseRequiredTenths(
  value: string,
  label: string,
  fieldId: string,
): number {
  const parsed = parseOptionalTenths(value, label, fieldId);
  if (parsed === null) {
    throw new CorrectionInputError(
      `${label} is required for each transfer.`,
      fieldId,
    );
  }
  return parsed;
}

export function parseTransfers(
  transfers: TransferDraft[],
  formId: string,
): TeamStateOverrides["queuedTransfers"] {
  if (transfers.length === 0) return null;
  return transfers.map((transfer, index) => ({
    elementOutId: parseRequiredInteger(
      transfer.elementOutId,
      `Transfer ${index + 1} player out`,
      `${formId}-transfer-${transfer.key}-elementOutId`,
    ),
    elementInId: parseRequiredInteger(
      transfer.elementInId,
      `Transfer ${index + 1} player in`,
      `${formId}-transfer-${transfer.key}-elementInId`,
    ),
    sellingPriceTenths: parseRequiredTenths(
      transfer.sellingPrice,
      `Transfer ${index + 1} selling price`,
      `${formId}-transfer-${transfer.key}-sellingPrice`,
    ),
    purchasePriceTenths: parseRequiredTenths(
      transfer.purchasePrice,
      `Transfer ${index + 1} purchase price`,
      `${formId}-transfer-${transfer.key}-purchasePrice`,
    ),
  }));
}

export function parseAvailableChips(
  value: string,
  fieldId: string,
): string[] | null {
  const chips = value
    .split(",")
    .map((chip) => chip.trim())
    .filter(Boolean);
  if (chips.length === 0) return null;
  if (new Set(chips).size !== chips.length) {
    throw new CorrectionInputError("List each available chip once.", fieldId);
  }
  return chips.sort();
}

export function correctionError(caught: unknown): CorrectionError {
  if (caught instanceof CorrectionInputError) {
    return caught.fieldId
      ? { message: caught.message, fieldId: caught.fieldId }
      : { message: caught.message };
  }
  // Its own message, because this one is actionable and specific: the manager
  // has to reload before saving, and no other failure here asks that.
  if (caught instanceof TeamStateOverridesConflictError) {
    return { message: caught.message };
  }
  if (caught instanceof ZodError) {
    return {
      message: caught.issues[0]?.message ?? "Review the manager corrections.",
    };
  }
  // Deliberately not the caught message: it may be a QuotaExceededError from
  // storage, and "QuotaExceededError" tells a manager nothing they can act on.
  return {
    message:
      "Corrections could not be saved in this browser. Check storage access and try again.",
  };
}

export function formatTenthsInput(value: number): string {
  return `${Math.floor(value / 10)}.${value % 10}`;
}
