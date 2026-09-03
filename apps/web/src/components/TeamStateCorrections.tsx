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

import { InfoMarker } from "./InfoMarker";
import {
  CorrectionField,
  TransferInput,
} from "./team-state-corrections/fields";
import {
  correctionError,
  formatTenthsInput,
  parseOptionalInteger,
  parseOptionalTenths,
  parseTransfers,
  type CorrectionError,
  type TransferDraft,
  type TransferField,
} from "./team-state-corrections/parse";
import {
  loadTeamStateOverrides,
  removeTeamStateOverrides,
  saveTeamStateOverrides,
} from "../state/team-state-overrides";

interface TeamStateCorrectionsProps {
  state: PublicTeamState;
}

const AVAILABLE_CHIPS = [
  ["wildcard", "Wildcard"],
  ["free_hit", "Free Hit"],
  ["bench_boost", "Bench Boost"],
  ["triple_captain", "Triple Captain"],
] as const;

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
  const [availableChips, setAvailableChips] = useState<ReadonlySet<string>>(
    () => new Set(existing?.availableChips ?? []),
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
      const overrides = saveTeamStateOverrides(
        localStorage,
        state.entryId,
        {
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
          availableChips:
            availableChips.size === 0 ? null : [...availableChips].sort(),
        },
        // What this form was editing. If another tab has written since, the
        // save is refused rather than overwriting a correction nobody knows
        // was lost.
        { expectedUpdatedAt: savedOverrides?.updatedAt ?? null },
      );
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
      setAvailableChips(new Set());
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
          Anything you have changed since the deadline. Stays in this browser.
          <InfoMarker label="manager corrections">
            These values are kept separate from the observed FPL snapshot, so
            the record and your corrections are never mixed. Nothing is sent
            anywhere.
          </InfoMarker>
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
              <fieldset className="correction-chip-options" id={chipsId}>
                <legend>Available chips</legend>
                {AVAILABLE_CHIPS.map(([value, label]) => (
                  <label className="chip-toggle" key={value}>
                    <input
                      checked={availableChips.has(value)}
                      onChange={(event) => {
                        setAvailableChips((current) => {
                          const next = new Set(current);
                          if (event.target.checked) next.add(value);
                          else next.delete(value);
                          return next;
                        });
                        setError(null);
                      }}
                      type="checkbox"
                    />
                    <span>{label}</span>
                  </label>
                ))}
              </fieldset>
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
              aria-describedby={`${formId}-remove-description ${formId}-remove-keys`}
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
              {/* The Escape key and the focus trap were
                  exercised only by a Playwright journey, so the behaviour was
                  documented to the test suite and to nobody using the site.
                  Stated here, in the dialog it applies to, and read out by a
                  screen reader as part of the description. */}
              <p className="keyboard-hint mono" id={`${formId}-remove-keys`}>
                <kbd>Esc</kbd> keeps the corrections. <kbd>Tab</kbd> stays
                inside this prompt until you choose.
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

function loadExistingOverrides(
  state: PublicTeamState,
): TeamStateOverrides | null {
  try {
    return loadTeamStateOverrides(localStorage, state.entryId, state.stateAsOf);
  } catch {
    return null;
  }
}
