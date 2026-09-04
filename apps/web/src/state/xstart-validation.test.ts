import { describe, expect, it } from "vitest";

import validation from "../data/xstart-validation.json";
import {
  averageXStartHits,
  latestSettledWindow,
  latestXStartEvent,
  readXStartValidation,
} from "./xstart-validation";

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

  it("opens a rolling five-gameweek window only when five checks have settled", () => {
    const parsed = readXStartValidation(validation);
    const base = parsed.events[0]!;
    const club = base.clubs[0]!.club;
    const events = Array.from({ length: 6 }, (_, index) => ({
      ...base,
      event: index + 1,
      clubs: base.clubs.map((row) =>
        row.club === club ? { ...row, topElevenHits: index + 1 } : row,
      ),
    }));

    expect(latestSettledWindow(events.slice(0, 4), 5)).toEqual([]);
    expect(
      latestSettledWindow(events.slice(0, 5), 5).map((event) => event.event),
    ).toEqual([1, 2, 3, 4, 5]);
    const latestFive = latestSettledWindow(events, 5);
    expect(latestFive.map((event) => event.event)).toEqual([2, 3, 4, 5, 6]);
    expect(averageXStartHits(latestFive, club)).toBe(4);
  });
});
