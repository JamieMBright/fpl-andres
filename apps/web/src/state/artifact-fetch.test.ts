import { createHash } from "node:crypto";

import { describe, expect, it, vi } from "vitest";

import { loadArtifact } from "./artifact-fetch";

const document = {
  schemaVersion: 7,
  players: [{ code: 123, fixtures: [1, 38], evidence: { source: "observed" } }],
  extraEvidence: { timestamp: "2026-11-05T00:00:00Z" },
};
const source = JSON.stringify(document);
const descriptor = {
  name: "season-inputs.json",
  schemaVersion: 7,
  sha256: createHash("sha256").update(source).digest("hex"),
};

describe("complete artifact loading", () => {
  it("preserves every field and shares concurrent downloads", async () => {
    const fetcher = vi.fn(async () => Response.json(document));
    const url = "/artifacts/complete.json";
    const [first, second] = await Promise.all([
      loadArtifact(url, descriptor, fetcher),
      loadArtifact(url, descriptor, fetcher),
    ]);

    expect(first).toEqual(document);
    expect(second).toBe(first);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(await loadArtifact(url, descriptor, fetcher)).toBe(first);
  });

  it.each([
    ["missing", () => new Response(null, { status: 404 }), /404/],
    ["html", () => new Response("<html>Not JSON</html>"), /JSON/],
    ["corrupt", () => Response.json({ ...document, players: [] }), /integrity/],
  ])("rejects %s responses and allows retry", async (name, response, error) => {
    const fetcher = vi.fn(async () => response());
    const url = `/artifacts/${name}.json`;
    await expect(loadArtifact(url, descriptor, fetcher)).rejects.toThrow(error);
    fetcher.mockImplementation(async () => Response.json(document));
    await expect(loadArtifact(url, descriptor, fetcher)).resolves.toEqual(
      document,
    );
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("refuses an incompatible schema even when the bytes match", async () => {
    await expect(
      loadArtifact(
        "/artifacts/wrong-schema.json",
        { ...descriptor, schemaVersion: 8 },
        async () => Response.json(document),
      ),
    ).rejects.toThrow(/schema version/);
  });

  it("refuses malformed JSON with a matching digest", async () => {
    const malformed = "{";
    await expect(
      loadArtifact(
        "/artifacts/malformed.json",
        {
          ...descriptor,
          sha256: createHash("sha256").update(malformed).digest("hex"),
        },
        async () =>
          new Response(malformed, {
            headers: { "Content-Type": "application/json" },
          }),
      ),
    ).rejects.toThrow();
  });
});
