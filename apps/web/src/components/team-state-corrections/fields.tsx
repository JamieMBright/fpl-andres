import type { ReactNode } from "react";

import type { CorrectionError, TransferDraft, TransferField } from "./parse";

/**
 * The two input primitives of the corrections form.
 *
 * Both are presentational and stateless: they own no draft and
 * no error, only how a label, an input and its error wiring are put together.
 * Keeping them here means the form component reads as a list of fields rather
 * than as several hundred lines of near-identical markup, and means the
 * `aria-describedby`/`aria-invalid` pairing is written once instead of once per
 * field.
 */

interface CorrectionFieldProps {
  children: ReactNode;
  id: string;
  label: string;
}

export function CorrectionField({ children, id, label }: CorrectionFieldProps) {
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

export function TransferInput({
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
