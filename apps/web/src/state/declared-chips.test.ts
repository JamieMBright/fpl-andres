import { describe, expect, it } from "vitest";

import {
  CHIPS,
  NO_CHIPS,
  chipsFromHistory,
  chipsRemaining,
  readDeclaredChips,
  saveDeclaredChips,
} from "./declared-chips";

function store(): Storage {
  const held = new Map<string, string>();
  return {
    get length() {
      return held.size;
    },
    clear: () => {
      held.clear();
    },
    getItem: (key: string) => held.get(key) ?? null,
    key: (index: number) => [...held.keys()][index] ?? null,
    removeItem: (key: string) => {
      held.delete(key);
    },
    setItem: (key: string, value: string) => {
      held.set(key, value);
    },
  };
}

describe("declared chips", () => {
  it("knows nothing about a team that has said nothing", () => {
    expect(readDeclaredChips(store(), 1)).toEqual(NO_CHIPS);
  });

  it("infers a spent chip straight off FPL's own history record", () => {
    expect(
      chipsFromHistory([
        { name: "wildcard", event: 5 },
        { name: "bboost", event: 22 },
      ]),
    ).toEqual([
      { chip: "wildcard", half: "first" },
      { chip: "bboost", half: "second" },
    ]);
  });

  it("ignores a chip name FPL has not published, and de-duplicates repeats", () => {
    expect(
      chipsFromHistory([
        { name: "manager_of_the_month" as never, event: 3 },
        { name: "freehit", event: 3 },
        { name: "freehit", event: 3 },
      ]),
    ).toEqual([{ chip: "freehit", half: "first" }]);
  });

  it("infers nothing from an absent history record", () => {
    expect(chipsFromHistory(undefined)).toEqual([]);
  });

  it("returns what was declared", () => {
    const storage = store();
    saveDeclaredChips(storage, 1, {
      committed: { chip: "3xc", event: 12 },
      spent: [{ chip: "wildcard", half: "first" }],
    });

    expect(readDeclaredChips(storage, 1)).toEqual({
      committed: { chip: "3xc", event: 12 },
      spent: [{ chip: "wildcard", half: "first" }],
    });
  });

  it("keeps one team's chips out of another's", () => {
    const storage = store();
    saveDeclaredChips(storage, 1, {
      committed: null,
      spent: [{ chip: "bboost", half: "first" }],
    });

    expect(readDeclaredChips(storage, 2)).toEqual(NO_CHIPS);
  });

  it("refuses to hold a chip as both spent and committed", () => {
    const storage = store();
    const saved = saveDeclaredChips(storage, 1, {
      committed: { chip: "wildcard", event: 9 },
      spent: [{ chip: "wildcard", half: "first" }],
    });

    expect(saved.committed).toBeNull();
    expect(readDeclaredChips(storage, 1).committed).toBeNull();
  });

  it("does not spend the same chip twice", () => {
    const storage = store();
    const saved = saveDeclaredChips(storage, 1, {
      committed: null,
      spent: [
        { chip: "freehit", half: "first" },
        { chip: "freehit", half: "first" },
      ],
    });

    expect(saved.spent).toEqual([{ chip: "freehit", half: "first" }]);
  });

  it("discards a stored value it cannot trust", () => {
    const storage = store();
    storage.setItem("fpl-andres:chips:1", '{"spent":["triple-captain"]}');

    expect(readDeclaredChips(storage, 1)).toEqual(NO_CHIPS);
    expect(storage.getItem("fpl-andres:chips:1")).toBeNull();
  });

  it("discards a stored value that is not JSON", () => {
    const storage = store();
    storage.setItem("fpl-andres:chips:1", "{");

    expect(readDeclaredChips(storage, 1)).toEqual(NO_CHIPS);
    expect(storage.getItem("fpl-andres:chips:1")).toBeNull();
  });

  it("offers the plan only the chips that are left", () => {
    expect(chipsRemaining(NO_CHIPS, "first")).toEqual([...CHIPS]);
    expect(
      chipsRemaining(
        {
          committed: null,
          spent: [
            { chip: "wildcard", half: "first" },
            { chip: "bboost", half: "first" },
          ],
        },
        "first",
      ),
    ).toEqual(["freehit", "3xc"]);
    expect(
      chipsRemaining(
        {
          committed: null,
          spent: [{ chip: "wildcard", half: "first" }],
        },
        "second",
      ),
    ).toEqual([...CHIPS]);
  });

  it("migrates legacy spent chips to the first half", () => {
    const storage = store();
    storage.setItem(
      "fpl-andres:chips:1",
      '{"spent":["wildcard"],"committed":null}',
    );

    expect(readDeclaredChips(storage, 1).spent).toEqual([
      { chip: "wildcard", half: "first" },
    ]);
  });

  it("allows committing the second copy after the first was spent", () => {
    const saved = saveDeclaredChips(store(), 1, {
      spent: [{ chip: "wildcard", half: "first" }],
      committed: { chip: "wildcard", event: 20 },
    });

    expect(saved.committed).toEqual({ chip: "wildcard", event: 20 });
  });
});
