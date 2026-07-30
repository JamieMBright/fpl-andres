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
import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
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

interface CorrectionError {
  message: string;
  fieldId?: string;
}

class CorrectionInputError extends Error {
  constructor(
    message: string,
    readonly fieldId?: string,
  ) {
    super(message);
    this.name = "CorrectionInputError";
  }
}

export function TeamStateCorrections({ state }: TeamStateCorrectionsProps) {
  const formId = useId();
  const bankId = `${formId}-bank`;
  const freeTransfersId = `${formId}-free-transfers`;
  const chipsId = `${formId}-chips`;
  const errorId = `${formId}-error`;
  const hintId = `${formId}-hint`;
  const errorRef = useRef<HTMLParagraphElement>(null);
  const keepCorrectionsRef = useRef<HTMLButtonElement>(null);
  const removeConfirmRef = useRef<HTMLButtonElement>(null);
  const removeCorrectionsRef = useRef<HTMLButtonElement>(null);
  const removedStatusRef = useRef<HTMLDivElement>(null);
  const returnToRemoveTrigger = useRef(false);
  const [existing] = useState(() => loadExistingOverrides(state));
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
  const [confirmingRemoval, setConfirmingRemoval] = useState(false);
  const [error, setError] = useState<CorrectionError | null>(null);

  useEffect(() => {
    if (!error) return;
    const target = error.fieldId
      ? document.getElementById(error.fieldId)
      : errorRef.current;
    target?.focus();
  }, [error]);

  useEffect(() => {
    if (confirmingRemoval) {
      keepCorrectionsRef.current?.focus();
    } else if (returnToRemoveTrigger.current) {
      returnToRemoveTrigger.current = false;
      removeCorrectionsRef.current?.focus();
    }
  }, [confirmingRemoval]);

  useEffect(() => {
    if (removedThisSession) removedStatusRef.current?.focus();
  }, [removedThisSession]);

  function addTransfer() {
    setError(null);
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
    setError(null);
    setTransfers((current) =>
      current.map((transfer) =>
        transfer.key === key ? { ...transfer, [field]: value } : transfer,
      ),
    );
  }

  function removeTransfer(key: number) {
    setError(null);
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
        bankTenths: parseOptionalTenths(bank, "Current bank", bankId),
        availableFreeTransfers: parseOptionalInteger(
          freeTransfers,
          "Available free transfers",
          freeTransfersId,
        ),
        currentSquad: null,
        queuedTransfers: parseTransfers(transfers, formId),
        availableChips: parseAvailableChips(availableChips, chipsId),
      });
      setSavedOverrides(overrides);
      setSavedThisSession(true);
      setRemovedThisSession(false);
      setConfirmingRemoval(false);
      setError(null);
    } catch (caught) {
      setSavedThisSession(false);
      setError(correctionError(caught));
    }
  }

  function removeCorrections() {
    try {
      removeTeamStateOverrides(localStorage, state.entryId, state.stateAsOf);
      setBank("");
      setFreeTransfers("");
      setAvailableChips("");
      setTransfers([]);
      nextTransferKey.current = 0;
      setSavedOverrides(null);
      setSavedThisSession(false);
      setConfirmingRemoval(false);
      setRemovedThisSession(true);
      setError(null);
    } catch (caught) {
      setRemovedThisSession(false);
      setError(correctionError(caught));
    }
  }

  function cancelRemoval() {
    returnToRemoveTrigger.current = true;
    setConfirmingRemoval(false);
  }

  function handleDialogKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      cancelRemoval();
      return;
    }
    if (event.key !== "Tab") return;
    const first = keepCorrectionsRef.current;
    const last = removeConfirmRef.current;
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
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
            tabIndex={-1}
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
            ref={removedStatusRef}
            role="status"
            tabIndex={-1}
          >
            <CheckCircle2 aria-hidden="true" size={18} />
            <span>
              <strong>Manager corrections removed</strong>
              <small>The observed FPL snapshot was not changed.</small>
            </span>
          </div>
        ) : null}

        <form
          aria-describedby={error ? `${hintId} ${errorId}` : hintId}
          className="correction-form"
          noValidate
          onSubmit={saveCorrections}
        >
          <p className="field-hint correction-hint" id={hintId}>
            Provide at least 1 balance, available chip or queued transfer to
            save a correction.
          </p>
          <fieldset>
            <legend>Current Balances</legend>
            <div className="correction-field-grid">
              <CorrectionField id={bankId} label="Current bank (£m)">
                <input
                  aria-describedby={
                    error?.fieldId === bankId ? errorId : undefined
                  }
                  aria-invalid={error?.fieldId === bankId}
                  autoComplete="off"
                  id={bankId}
                  inputMode="decimal"
                  min="0"
                  name="current-bank"
                  onChange={(event) => {
                    setBank(event.target.value);
                    setError(null);
                  }}
                  placeholder="1.2…"
                  step="0.1"
                  type="number"
                  value={bank}
                />
              </CorrectionField>
              <CorrectionField
                id={freeTransfersId}
                label="Available free transfers"
              >
                <input
                  aria-describedby={
                    error?.fieldId === freeTransfersId ? errorId : undefined
                  }
                  aria-invalid={error?.fieldId === freeTransfersId}
                  autoComplete="off"
                  id={freeTransfersId}
                  inputMode="numeric"
                  min="0"
                  name="available-free-transfers"
                  onChange={(event) => {
                    setFreeTransfers(event.target.value);
                    setError(null);
                  }}
                  placeholder="2…"
                  step="1"
                  type="number"
                  value={freeTransfers}
                />
              </CorrectionField>
              <CorrectionField id={chipsId} label="Available chips">
                <input
                  aria-describedby={
                    error?.fieldId === chipsId ? errorId : undefined
                  }
                  aria-invalid={error?.fieldId === chipsId}
                  autoComplete="off"
                  id={chipsId}
                  name="available-chips"
                  onChange={(event) => {
                    setAvailableChips(event.target.value);
                    setError(null);
                  }}
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
                      error={error}
                      errorId={errorId}
                      transfer={transfer}
                    />
                    <TransferInput
                      field="elementInId"
                      formId={formId}
                      index={index}
                      label="Player in"
                      onChange={updateTransfer}
                      error={error}
                      errorId={errorId}
                      transfer={transfer}
                    />
                    <TransferInput
                      field="sellingPrice"
                      formId={formId}
                      index={index}
                      label="Selling price (£m)"
                      onChange={updateTransfer}
                      error={error}
                      errorId={errorId}
                      transfer={transfer}
                    />
                    <TransferInput
                      field="purchasePrice"
                      formId={formId}
                      index={index}
                      label="Purchase price (£m)"
                      onChange={updateTransfer}
                      error={error}
                      errorId={errorId}
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
              id={errorId}
              ref={errorRef}
              role="alert"
              tabIndex={-1}
            >
              {error.message}
            </p>
          ) : null}

          <div className="correction-actions">
            <button className="primary-command" type="submit">
              <Save aria-hidden="true" size={18} /> Save corrections
            </button>
            {savedOverrides && !confirmingRemoval ? (
              <button
                className="danger-command"
                onClick={() => setConfirmingRemoval(true)}
                ref={removeCorrectionsRef}
                type="button"
              >
                <Trash2 aria-hidden="true" size={17} /> Remove saved corrections
              </button>
            ) : null}
          </div>
          {savedOverrides && confirmingRemoval ? (
            // The div is interactive by ARIA (role="alertdialog"), which the
            // jsx-a11y rule does not detect. Escape + Tab trap live at the
            // dialog root because both buttons must receive them.
            // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
            <div
              aria-describedby={`${formId}-remove-description`}
              aria-labelledby={`${formId}-remove-title`}
              className="inline-confirmation"
              onKeyDown={handleDialogKeyDown}
              role="alertdialog"
            >
              <strong id={`${formId}-remove-title`}>
                Remove saved corrections?
              </strong>
              <p id={`${formId}-remove-description`}>
                This removes only the local manager record for this team and
                public deadline. The observed FPL snapshot stays unchanged.
              </p>
              <div>
                <button
                  className="secondary-command"
                  onClick={cancelRemoval}
                  ref={keepCorrectionsRef}
                  type="button"
                >
                  Keep corrections
                </button>
                <button
                  className="danger-command"
                  onClick={removeCorrections}
                  ref={removeConfirmRef}
                  type="button"
                >
                  <Trash2 aria-hidden="true" size={17} /> Remove corrections now
                </button>
              </div>
            </div>
          ) : null}
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
  error: CorrectionError | null;
  errorId: string;
  field: TransferField;
  formId: string;
  index: number;
  label: string;
  onChange: (key: number, field: TransferField, value: string) => void;
  transfer: TransferDraft;
}

function TransferInput({
  error,
  errorId,
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
        aria-describedby={error?.fieldId === id ? errorId : undefined}
        aria-invalid={error?.fieldId === id}
        autoComplete="off"
        id={id}
        inputMode={isPrice ? "decimal" : "numeric"}
        min={isPrice ? "0" : undefined}
        name={`queued-transfer-${index + 1}-${field}`}
        onChange={(event) => onChange(transfer.key, field, event.target.value)}
        placeholder={isPrice ? "6.5…" : "123…"}
        pattern={isPrice ? undefined : "[0-9]*"}
        step={isPrice ? "0.1" : undefined}
        type={isPrice ? "number" : "text"}
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

function parseOptionalTenths(
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

function parseOptionalInteger(
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

function parseRequiredInteger(
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

function parseRequiredTenths(
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

function parseTransfers(
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

function parseAvailableChips(value: string, fieldId: string): string[] | null {
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

function correctionError(caught: unknown): CorrectionError {
  if (caught instanceof CorrectionInputError) {
    return caught.fieldId
      ? { message: caught.message, fieldId: caught.fieldId }
      : { message: caught.message };
  }
  if (caught instanceof ZodError) {
    return {
      message: caught.issues[0]?.message ?? "Review the manager corrections.",
    };
  }
  return {
    message:
      "Corrections could not be saved in this browser. Check storage access and try again.",
  };
}

function formatTenthsInput(value: number): string {
  return `${Math.floor(value / 10)}.${value % 10}`;
}
