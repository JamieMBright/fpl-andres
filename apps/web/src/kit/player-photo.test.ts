import { describe, expect, it } from "vitest";

import { getPlayerPhotoUrl } from "./player-photo";

describe("getPlayerPhotoUrl", () => {
  it("uses the current FPL media collection", () => {
    expect(getPlayerPhotoUrl(489639)).toBe(
      "https://resources.premierleague.com/premierleague25/photos/players/110x140/489639.png",
    );
  });
});
