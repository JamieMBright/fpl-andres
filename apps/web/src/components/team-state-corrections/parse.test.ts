import { describe, expect, it } from "vitest";
import { z, type ZodError } from "zod";

import {
  CorrectionInputError,
  correctionError,
  formatTenthsInput,
  parseOptionalInteger,
  parseOptionalTenths,
  parseRequiredInteger,
  parseRequiredTenths,
  parseTransfers,
} from "./parse";

/**
 * These eight functions used to live inside a 720-line
 * component, so the only way to reach them was to render it and type. That made
 * their boundaries expensive to test and therefore untested.
 *
 * They matter because they are the seam between what a manager typed and what
 * the optimiser treats as fact. A price parsed as 4.5 instead of 45 would make
 * a player a tenth of their real cost and the squad would look affordable.
 */

describe("parseOptionalTenths", () => {
  it("reads a price as tenths, so 4.5 is 45 and never 4.5", () => {
    expect(parseOptionalTenths("4.5", "Price")).toBe(45);
    expect(parseOptionalTenths("4", "Price")).toBe(40);
    expect(parseOptionalTenths("0.0", "Price")).toBe(0);
    expect(parseOptionalTenths("14.9", "Price")).toBe(149);
  });

  it("treats blank as absent rather than zero", () => {
    // Zero is a real bank balance. Blank means "I did not say", and the two
    // must not collapse: a blank bank should keep the FPL-reported value.
    expect(parseOptionalTenths("   ", "Price")).toBeNull();
    expect(parseOptionalTenths("0", "Price")).toBe(0);
  });

  it("refuses a second decimal place, because FPL has no such price", () => {
    expect(() => parseOptionalTenths("4.55", "Price", "f")).toThrow(
      CorrectionInputError,
    );
  });

  it.each(["-1", "4.", ".5", "4,5", "1e2", "NaN", "Infinity", "4 5"])(
    "refuses %s",
    (value) => {
      expect(() => parseOptionalTenths(value, "Price", "f")).toThrow(
        CorrectionInputError,
      );
    },
  );

  it("names the field so focus can move to the input that failed", () => {
    try {
      parseOptionalTenths("nope", "Bank", "corrections-bank");
      expect.unreachable();
    } catch (caught) {
      expect(caught).toBeInstanceOf(CorrectionInputError);
      expect((caught as CorrectionInputError).fieldId).toBe("corrections-bank");
      expect((caught as CorrectionInputError).message).toContain("Bank");
    }
  });

  it("refuses a value whose tenths would leave the safe integer range", () => {
    const huge = "9".repeat(17);
    expect(() => parseOptionalTenths(huge, "Price", "f")).toThrow(
      /outside the supported range/,
    );
  });
});

describe("parseOptionalInteger", () => {
  it("accepts non-negative integers and blank", () => {
    expect(parseOptionalInteger("0", "Count")).toBe(0);
    expect(parseOptionalInteger("12", "Count")).toBe(12);
    expect(parseOptionalInteger("", "Count")).toBeNull();
  });

  it.each(["-1", "1.5", "1_000", " 1 2", "one"])("refuses %s", (value) => {
    expect(() => parseOptionalInteger(value, "Count", "f")).toThrow(
      CorrectionInputError,
    );
  });

  it("refuses beyond the safe integer range", () => {
    expect(() => parseOptionalInteger("9".repeat(17), "Count", "f")).toThrow(
      /outside the supported range/,
    );
  });
});

describe("parseRequiredInteger", () => {
  it("accepts a plausible FPL element id", () => {
    expect(parseRequiredInteger("427", "Player", "f")).toBe(427);
  });

  it("refuses zero, because element ids start at one", () => {
    expect(() => parseRequiredInteger("0", "Player", "f")).toThrow(
      /positive FPL element ID/,
    );
  });

  it("refuses blank, which parseOptionalInteger would have allowed", () => {
    expect(() => parseRequiredInteger("", "Player", "f")).toThrow(
      /positive FPL element ID/,
    );
  });

  it("holds at the unsigned 32-bit ceiling", () => {
    expect(parseRequiredInteger("4294967295", "Player", "f")).toBe(4294967295);
    expect(() => parseRequiredInteger("4294967296", "Player", "f")).toThrow(
      /positive FPL element ID/,
    );
  });
});

describe("parseRequiredTenths", () => {
  it("refuses blank with a message about the transfer, not the format", () => {
    expect(() => parseRequiredTenths("", "Selling price", "f")).toThrow(
      /required for each transfer/,
    );
  });

  it("still refuses a malformed value", () => {
    expect(() => parseRequiredTenths("4.55", "Selling price", "f")).toThrow(
      /at most 1 decimal place/,
    );
  });
});

describe("parseTransfers", () => {
  it("returns null for no transfers, distinguishing none from empty", () => {
    expect(parseTransfers([], "form")).toBeNull();
  });

  it("converts a draft into the contract shape", () => {
    const parsed = parseTransfers(
      [
        {
          key: 3,
          elementOutId: "12",
          elementInId: "427",
          sellingPrice: "5.4",
          purchasePrice: "5.0",
        },
      ],
      "corrections",
    );
    expect(parsed).toEqual([
      {
        elementOutId: 12,
        elementInId: 427,
        sellingPriceTenths: 54,
        purchasePriceTenths: 50,
      },
    ]);
  });

  it("numbers the failing transfer from one and keys the field by draft key", () => {
    // The label counts from one because managers do; the field id uses the
    // stable draft key because the index shifts when a row above is removed.
    try {
      parseTransfers(
        [
          {
            key: 7,
            elementOutId: "1",
            elementInId: "2",
            sellingPrice: "5.0",
            purchasePrice: "5.0",
          },
          {
            key: 9,
            elementOutId: "1",
            elementInId: "",
            sellingPrice: "5.0",
            purchasePrice: "5.0",
          },
        ],
        "corrections",
      );
      expect.unreachable();
    } catch (caught) {
      const error = caught as CorrectionInputError;
      expect(error.message).toContain("Transfer 2 player in");
      expect(error.fieldId).toBe("corrections-transfer-9-elementInId");
    }
  });
});

describe("correctionError", () => {
  it("passes through the field id when one was named", () => {
    expect(
      correctionError(new CorrectionInputError("Bad bank", "bank")),
    ).toEqual({ message: "Bad bank", fieldId: "bank" });
  });

  it("omits the field id key entirely when none was named", () => {
    expect(correctionError(new CorrectionInputError("Bad"))).toEqual({
      message: "Bad",
    });
  });

  it("surfaces the first zod issue, which is the contract's own wording", () => {
    const schema = z.object({
      bank: z.number().min(0, "Bank cannot be negative"),
    });
    const result = schema.safeParse({ bank: -1 });
    expect(result.success).toBe(false);
    const error = result.error as ZodError;
    expect(correctionError(error)).toEqual({
      message: "Bank cannot be negative",
    });
  });

  it("never leaks a storage exception's own words to the manager", () => {
    // A QuotaExceededError message names a browser API. Telling a manager
    // "QuotaExceededError" is not an instruction they can follow.
    const quota = new DOMException("Quota exceeded", "QuotaExceededError");
    const shown = correctionError(quota);
    expect(shown.message).not.toContain("Quota");
    expect(shown.message).toContain("storage access");
    expect(shown.fieldId).toBeUndefined();
  });
});

describe("formatTenthsInput", () => {
  it("round-trips through parseOptionalTenths", () => {
    for (const tenths of [0, 5, 40, 45, 149, 1234]) {
      expect(parseOptionalTenths(formatTenthsInput(tenths), "Price")).toBe(
        tenths,
      );
    }
  });

  it("always shows the decimal place, so 4 reads as 4.0", () => {
    expect(formatTenthsInput(40)).toBe("4.0");
    expect(formatTenthsInput(45)).toBe("4.5");
    expect(formatTenthsInput(0)).toBe("0.0");
  });
});
