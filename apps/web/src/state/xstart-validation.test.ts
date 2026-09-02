import { describe, expect, it } from "vitest";

import validation from "../data/xstart-validation.json";
import { latestXStartEvent, readXStartValidation } from "./xstart-validation";

describe("xStart validation artifact", () => {
  it("publishes immutable GW1 and GW2 scoring as an event series", () => {
    const parsed = readXStartValidation(validation);

    expect(parsed.events.map((event) => event.event)).toEqual([1, 2]);
    expect(parsed.events[0]?.population.count).toBe(486);
    expect(latestXStartEvent(parsed).event).toBe(2);
    expect(latestXStartEvent(parsed).clubs).toHaveLength(20);
  });

  it("refuses a field with a different meaning", () => {
    const [first, ...rest] = validation.events;
    expect(first).toBeDefined();
    expect(() =>
      readXStartValidation({
        ...validation,
        events: [{ ...first!, field: "probabilityStart" }, ...rest],
      }),
    ).toThrow(/incomplete event/i);
  });
});
