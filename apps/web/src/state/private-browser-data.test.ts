import { describe, expect, it } from "vitest";

import { clearPrivateBrowserData } from "./private-browser-data";

function memoryStorage(entries: Record<string, string>): Storage {
  const held = new Map(Object.entries(entries));
  return {
    get length() {
      return held.size;
    },
    clear: () => held.clear(),
    getItem: (key) => held.get(key) ?? null,
    key: (index) => [...held.keys()][index] ?? null,
    removeItem: (key) => held.delete(key),
    setItem: (key, value) => held.set(key, value),
  } as Storage;
}

describe("clearing private browser data", () => {
  it("removes every manager and planning record owned by this app", () => {
    const storage = memoryStorage({
      "fpl-andres:declared:42": "[]",
      "fpl-andres:declared-squad:v1:42:1": "{}",
      "fpl-andres:chips:42": "{}",
      "fpl-andres:objective:v1:42": "{}",
      "fpl-andres:team-state-overrides:v1:42:deadline": "{}",
      "fpl-andres:public-team-state:v1:42": "{}",
      "fpl-andres:manager-history:v1:42": "{}",
      "fpl-andres:scorecard:v1:42": "[]",
      "fpl-andres:last-team": "42",
    });

    expect(clearPrivateBrowserData(storage)).toBe(9);
    expect(storage.length).toBe(0);
  });

  it("preserves the kit preference and data belonging to another app", () => {
    const storage = memoryStorage({
      "fpl-andres:theme": "light",
      "another-app:team": "42",
      "fpl-andres:declared:42": "[]",
    });

    clearPrivateBrowserData(storage);

    expect(storage.getItem("fpl-andres:theme")).toBe("light");
    expect(storage.getItem("another-app:team")).toBe("42");
    expect(storage.getItem("fpl-andres:declared:42")).toBeNull();
  });
});
