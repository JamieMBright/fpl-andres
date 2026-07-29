import type {
  PublicTeamState,
  TeamStateOverrides,
} from "@fpl-andres/contracts";
import {
  CheckCircle2,
  ChevronDown,
  PencilLine,
  Plus,
  Save,
  Trash2,
  X,
} from "lucide-react";
import { useId, useRef, useState, type FormEvent } from "react";
import { ZodError } from "zod";

import {
  loadTeamStateOverrides,
  removeTeamStateOverrides,
  saveTeamStateOverrides,
} from "../state/team-state-overrides";

interface TeamStateCorrectionsProps {
  state: PublicTeamState;
}

interface TransferDraft {
  key: number;
  elementOutId: string;
  elementInId: string;
  sellingPrice: string;
  purchasePrice: string;
}

type TransferField = Exclude<keyof TransferDraft, "key">;

class CorrectionInputError extends Error {}

export function TeamStateCorrections({ state }: TeamStateCorrectionsProps) {
  const formId = useId();
  const errorRef = useRef<HTMLParagraphElement>(null);
  const existing = useRef(loadExistingOverrides(state)).current;
  const nextTransferKey = useRef(existing?.queuedTransfers?.length ?? 0);
  const [bank, setBank] = useState(() =>
    existing?.bankTenths === null || existing?.bankTenths === undefined
      ? ""
      : formatTenthsInput(existing.bankTenths),
  );
  const [freeTransfers, setFreeTransfers] = useState(() =>
    existing?.availableFreeTransfers === null ||
    existing?.availableFreeTransfers === undefined
      ? ""
      : String(existing.availableFreeTransfers),
  );
  const [availableChips, setAvailableChips] = useState(
    () => existing?.availableChips?.join(", ") ?? "",
  );
  const [transfers, setTransfers] = useState<TransferDraft[]>(() =>
    (existing?.queuedTransfers ?? []).map((transfer, index) => ({
      key: index,
      elementOutId: String(transfer.elementOutId),
      elementInId: String(transfer.elementInId),
      sellingPrice: formatTenthsInput(transfer.sellingPriceTenths),
      purchasePrice: formatTenthsInput(transfer.purchasePriceTenths),
    })),
  );
  const [savedOverrides, setSavedOverrides] =
    useState<TeamStateOverrides | null>(existing);
  const [savedThisSession, setSavedThisSession] = useState(false);
  const [removedThisSession, setRemovedThisSession] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function addTransfer() {
    const key = nextTransferKey.current;
    nextTransferKey.current += 1;
    setTransfers((current) => [
      ...current,
      {
        key,
        elementOutId: "",
        elementInId: "",
        sellingPrice: "",
        purchasePrice: "",
      },
    ]);
  }

  function updateTransfer(key: number, field: TransferField, value: string) {
    setTransfers((current) =>
      current.map((transfer) =>
        transfer.key === key ? { ...transfer, [field]: value } : transfer,
      ),
    );
  }

  function removeTransfer(key: number) {
    setTransfers((current) =>
      current.filter((transfer) => transfer.key !== key),
    );
  }

  function saveCorrections(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const overrides = saveTeamStateOverrides(localStorage, state.entryId, {
        source: "manager",
        basedOnStateAsOf: state.stateAsOf,
        updatedAt: new Date().toISOString(),
        bankTenths: parseOptionalTenths(bank, "Current bank"),
        availableFreeTransfers: parseOptionalInteger(
          freeTransfers,
          "Available free transfers",
        ),
        currentSquad: null,
        queuedTransfers: parseTransfers(transfers),
        availableChips: parseAvailableChips(availableChips),
      });
      setSavedOverrides(overrides);
      setSavedThisSession(true);
      setRemovedThisSession(false);
      setError(null);
    } catch (caught) {
      setSavedThisSession(false);
      setError(correctionErrorMessage(caught));
      queueMicrotask(() => errorRef.current?.focus());
    }
  }

  function removeCorrections() {
    if (
      !window.confirm(
        "Remove the manager corrections saved for this team and public deadline?",
      )
    ) {
      return;
    }
    try {
      removeTeamStateOverrides(localStorage, state.entryId, state.stateAsOf);
      setBank("");
      setFreeTransfers("");
      setAvailableChips("");
      setTransfers([]);
      nextTransferKey.current = 0;
      setSavedOverrides(null);
      setSavedThisSession(false);
      setRemovedThisSession(true);
      setError(null);
    } catch (caught) {
      setRemovedThisSession(false);
      setError(correctionErrorMessage(caught));
      queueMicrotask(() => errorRef.current?.focus());
    }
  }

  return (
    <details className="correction-panel">
      <summary>
        <span>
          <PencilLine aria-hidden="true" size={18} /> Correct Current State
        </span>
        <span className="correction-summary-state">
          {savedOverrides ? "Saved locally" : "Optional"}
          <ChevronDown
            aria-hidden="true"
            className="disclosure-mark"
            size={18}
          />
        </span>
      </summary>
      <div className="correction-panel-body">
        <div className="dossier-heading">
          <div>
            <p className="eyebrow">Private local evidence</p>
            <h2>Manager Corrections</h2>
          </div>
          <span className="evidence-chip evidence-chip-manager">
            <PencilLine aria-hidden="true" size={15} /> Manager supplied
          </span>
        </div>
        <p className="dossier-qualification">
          Record changes made since the public deadline. These values stay in
          this browser and remain separate from the observed FPL snapshot.
        </p>

        {savedThisSession ? (
          <div
            aria-label="Manager correction status"
            className="correction-saved"
            role="status"
          >
            <CheckCircle2 aria-hidden="true" size={18} />
            <span>
              <strong>Manager corrections saved</strong>
              <small>Bound to this team and public deadline.</small>
            </span>
          </div>
        ) : null}
        {removedThisSession ? (
          <div
            aria-label="Manager correction status"
            className="correction-saved"
            role="status"
          >
            <CheckCircle2 aria-hidden="true" size={18} />
            <span>
              <strong>Manager corrections removed</strong>
              <small>The observed FPL snapshot was not changed.</small>
            </span>
          </div>
        ) : null}

        <form
          aria-describedby={error ? `${formId}-error` : undefined}
          className="correction-form"
          noValidate
          onSubmit={saveCorrections}
        >
          <fieldset>
            <legend>Current Balances</legend>
            <div className="correction-field-grid">
              <CorrectionField id={`${formId}-bank`} label="Current bank (£m)">
                <input
                  autoComplete="off"
                  id={`${formId}-bank`}
                  inputMode="decimal"
                  min="0"
                  name="current-bank"
                  onChange={(event) => setBank(event.target.value)}
                  placeholder="1.2…"
                  step="0.1"
                  type="number"
                  value={bank}
                />
              </CorrectionField>
              <CorrectionField
                id={`${formId}-free-transfers`}
                label="Available free transfers"
              >
                <input
                  autoComplete="off"
                  id={`${formId}-free-transfers`}
                  inputMode="numeric"
                  min="0"
                  name="available-free-transfers"
                  onChange={(event) => setFreeTransfers(event.target.value)}
                  placeholder="2…"
                  step="1"
                  type="number"
                  value={freeTransfers}
                />
              </CorrectionField>
              <CorrectionField id={`${formId}-chips`} label="Available chips">
                <input
                  autoComplete="off"
                  id={`${formId}-chips`}
                  name="available-chips"
                  onChange={(event) => setAvailableChips(event.target.value)}
                  placeholder="wildcard, bench_boost…"
                  spellCheck={false}
                  type="text"
                  value={availableChips}
                />
              </CorrectionField>
            </div>
          </fieldset>

          <fieldset>
            <legend>Queued Transfers</legend>
            {transfers.length === 0 ? (
              <p className="correction-empty">No queued transfers recorded.</p>
            ) : (
              <div className="transfer-drafts">
                {transfers.map((transfer, index) => (
                  <fieldset className="transfer-draft" key={transfer.key}>
                    <legend>Transfer {index + 1}</legend>
                    <button
                      aria-label={`Remove queued transfer ${index + 1}`}
                      className="icon-command"
                      onClick={() => removeTransfer(transfer.key)}
                      title={`Remove queued transfer ${index + 1}`}
                      type="button"
                    >
                      <X aria-hidden="true" size={17} />
                    </button>
                    <TransferInput
                      field="elementOutId"
                      formId={formId}
                      index={index}
                      label="Player out"
                      onChange={updateTransfer}
                      transfer={transfer}
                    />
                    <TransferInput
                      field="elementInId"
                      formId={formId}
                      index={index}
                      label="Player in"
                      onChange={updateTransfer}
                      transfer={transfer}
                    />
                    <TransferInput
                      field="sellingPrice"
                      formId={formId}
                      index={index}
                      label="Selling price (£m)"
                      onChange={updateTransfer}
                      transfer={transfer}
                    />
                    <TransferInput
                      field="purchasePrice"
                      formId={formId}
                      index={index}
                      label="Purchase price (£m)"
                      onChange={updateTransfer}
                      transfer={transfer}
                    />
                  </fieldset>
                ))}
              </div>
            )}
            <button
              className="secondary-command add-transfer-command"
              onClick={addTransfer}
              type="button"
            >
              <Plus aria-hidden="true" size={17} /> Add queued transfer
            </button>
          </fieldset>

          {error ? (
            <p
              className="field-error correction-error"
              id={`${formId}-error`}
              ref={errorRef}
              role="alert"
              tabIndex={-1}
            >
              {error}
            </p>
          ) : null}

          <div className="correction-actions">
            <button className="primary-command" type="submit">
              <Save aria-hidden="true" size={18} /> Save corrections
            </button>
            {savedOverrides ? (
              <button
                className="danger-command"
                onClick={removeCorrections}
                type="button"
              >
                <Trash2 aria-hidden="true" size={17} /> Remove saved corrections
              </button>
            ) : null}
          </div>
        </form>
      </div>
    </details>
  );
}

interface CorrectionFieldProps {
  children: React.ReactNode;
  id: string;
  label: string;
}

function CorrectionField({ children, id, label }: CorrectionFieldProps) {
  return (
    <div className="correction-field">
      <label htmlFor={id}>{label}</label>
      {children}
    </div>
  );
}

interface TransferInputProps {
  field: TransferField;
  formId: string;
  index: number;
  label: string;
  onChange: (key: number, field: TransferField, value: string) => void;
  transfer: TransferDraft;
}

function TransferInput({
  field,
  formId,
  index,
  label,
  onChange,
  transfer,
}: TransferInputProps) {
  const isPrice = field === "sellingPrice" || field === "purchasePrice";
  const id = `${formId}-transfer-${transfer.key}-${field}`;
  return (
    <div className="correction-field">
      <label htmlFor={id}>{label}</label>
      <input
        autoComplete="off"
        id={id}
        inputMode={isPrice ? "decimal" : "numeric"}
        min={isPrice ? "0" : "1"}
        name={`queued-transfer-${index + 1}-${field}`}
        onChange={(event) => onChange(transfer.key, field, event.target.value)}
        placeholder={isPrice ? "6.5…" : "123…"}
        step={isPrice ? "0.1" : "1"}
        type="number"
        value={transfer[field]}
      />
    </div>
  );
}

function loadExistingOverrides(
  state: PublicTeamState,
): TeamStateOverrides | null {
  try {
    return loadTeamStateOverrides(localStorage, state.entryId, state.stateAsOf);
  } catch {
    return null;
  }
}

function parseOptionalTenths(value: string, label: string): number | null {
  const normalized = value.trim();
  if (normalized === "") return null;
  const match = /^(\d+)(?:\.(\d))?$/.exec(normalized);
  if (!match) {
    throw new CorrectionInputError(
      `${label} must be a non-negative amount with at most 1 decimal place.`,
    );
  }
  const whole = Number(match[1]);
  const decimal = Number(match[2] ?? "0");
  const tenths = whole * 10 + decimal;
  if (!Number.isSafeInteger(tenths)) {
    throw new CorrectionInputError(`${label} is outside the supported range.`);
  }
  return tenths;
}

function parseOptionalInteger(value: string, label: string): number | null {
  const normalized = value.trim();
  if (normalized === "") return null;
  if (!/^\d+$/.test(normalized)) {
    throw new CorrectionInputError(`${label} must be a non-negative integer.`);
  }
  const parsed = Number(normalized);
  if (!Number.isSafeInteger(parsed)) {
    throw new CorrectionInputError(`${label} is outside the supported range.`);
  }
  return parsed;
}

function parseRequiredInteger(value: string, label: string): number {
  const parsed = parseOptionalInteger(value, label);
  if (parsed === null || parsed < 1 || parsed > 4_294_967_295) {
    throw new CorrectionInputError(
      `${label} must be a positive FPL element ID.`,
    );
  }
  return parsed;
}

function parseRequiredTenths(value: string, label: string): number {
  const parsed = parseOptionalTenths(value, label);
  if (parsed === null) {
    throw new CorrectionInputError(`${label} is required for each transfer.`);
  }
  return parsed;
}

function parseTransfers(
  transfers: TransferDraft[],
): TeamStateOverrides["queuedTransfers"] {
  if (transfers.length === 0) return null;
  return transfers.map((transfer, index) => ({
    elementOutId: parseRequiredInteger(
      transfer.elementOutId,
      `Transfer ${index + 1} player out`,
    ),
    elementInId: parseRequiredInteger(
      transfer.elementInId,
      `Transfer ${index + 1} player in`,
    ),
    sellingPriceTenths: parseRequiredTenths(
      transfer.sellingPrice,
      `Transfer ${index + 1} selling price`,
    ),
    purchasePriceTenths: parseRequiredTenths(
      transfer.purchasePrice,
      `Transfer ${index + 1} purchase price`,
    ),
  }));
}

function parseAvailableChips(value: string): string[] | null {
  const chips = value
    .split(",")
    .map((chip) => chip.trim())
    .filter(Boolean);
  if (chips.length === 0) return null;
  if (new Set(chips).size !== chips.length) {
    throw new CorrectionInputError("List each available chip once.");
  }
  return chips.sort();
}

function correctionErrorMessage(caught: unknown): string {
  if (caught instanceof CorrectionInputError) return caught.message;
  if (caught instanceof ZodError) {
    return caught.issues[0]?.message ?? "Review the manager corrections.";
  }
  return "Corrections could not be saved in this browser. Check storage access and try again.";
}

function formatTenthsInput(value: number): string {
  return `${Math.floor(value / 10)}.${value % 10}`;
}
