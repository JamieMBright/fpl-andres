import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ManagerHistory } from "./ManagerHistory";

/**
 * A refused request is not a broken contract. The component used to hand null
 * to the parser whenever the response was not ok, so a rate-limited proxy read
 * back as "FPL answered, but not in the shape I expect" -- an accusation
 * against the source for something the source never did, and one that points
 * whoever reads it at the wrong repair.
 */

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ManagerHistory", () => {
  it("blames the connection, not the payload, when the request is refused", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(new Response("", { status: 429 })),
    );

    render(<ManagerHistory entryId={212_279} />);

    expect(await screen.findByText(/could not reach FPL/i)).toBeVisible();
    expect(screen.queryByText(/not in the shape I expect/i)).toBeNull();
  });

  it("blames the payload only when the payload is genuinely unreadable", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(Response.json({ past: "not a list" })),
    );

    render(<ManagerHistory entryId={212_279} />);

    expect(await screen.findByText(/not in the shape I expect/i)).toBeVisible();
  });
});
