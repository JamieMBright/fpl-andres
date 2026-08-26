import { describe, expect, it } from "vitest";

import validation from "../data/xstart-validation.json";
import { readXStartValidation } from "./xstart-validation";

describe("xStart validation artifact", () => {
  it("publishes the immutable GW1 population and Leeds score", () => {
    const parsed = readXStartValidation(validation);

    expect(parsed.population).toMatchObject({
      count: 486,
      brier: 0.230679,
      actualStartRate: 0.44856,
    });
    expect(parsed.clubs.find((club) => club.club === "LEE")).toMatchObject({
      brier: 0.174089,
      topElevenHits: 10,
    });
  });

  it("refuses a field with a different meaning", () => {
    expect(() =>
      readXStartValidation({ ...validation, field: "probabilityStart" }),
    ).toThrow(/missing its population and clubs/i);
  });
});
