import { describe, expect, it } from "vitest";

import {
  CHIPS,
  NO_CHIPS,
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

  it("returns what was declared", () => {
    const storage = store();
    saveDeclaredChips(storage, 1, {
      committed: { chip: "3xc", event: 12 },
      spent: ["wildcard"],
    });

    expect(readDeclaredChips(storage, 1)).toEqual({
      committed: { chip: "3xc", event: 12 },
      spent: ["wildcard"],
    });
  });

  it("keeps one team's chips out of another's", () => {
    const storage = store();
    saveDeclaredChips(storage, 1, { committed: null, spent: ["bboost"] });

    expect(readDeclaredChips(storage, 2)).toEqual(NO_CHIPS);
  });

  it("refuses to hold a chip as both spent and committed", () => {
    const storage = store();
    const saved = saveDeclaredChips(storage, 1, {
      committed: { chip: "wildcard", event: 9 },
      spent: ["wildcard"],
    });

    expect(saved.committed).toBeNull();
    expect(readDeclaredChips(storage, 1).committed).toBeNull();
  });

  it("does not spend the same chip twice", () => {
    const storage = store();
    const saved = saveDeclaredChips(storage, 1, {
      committed: null,
      spent: ["freehit", "freehit"],
    });

    expect(saved.spent).toEqual(["freehit"]);
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
    expect(chipsRemaining(NO_CHIPS)).toEqual([...CHIPS]);
    expect(
      chipsRemaining({ committed: null, spent: ["wildcard", "bboost"] }),
    ).toEqual(["freehit", "3xc"]);
  });
});
