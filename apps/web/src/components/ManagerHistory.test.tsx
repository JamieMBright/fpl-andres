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

  /**
   * "I could not reach FPL" was true of a timeout and false of everything else.
   * The proxy already knows exactly what happened and says so in the body; the
   * browser was throwing that sentence away and substituting a vaguer one.
   */
  it("repeats what the proxy said when FPL refused the deployment", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        Response.json(
          {
            error:
              "FPL answered 403 with none: FPL refused the request from this deployment.",
            reason: "refused",
          },
          { status: 502 },
        ),
      ),
    );

    render(<ManagerHistory entryId={212_279} />);

    expect(
      await screen.findByText(
        /FPL answered 403 with none: FPL refused the request from this deployment\./,
      ),
    ).toBeVisible();
    expect(screen.queryByText(/could not reach FPL/i)).toBeNull();
  });

  it("says a rate limit is worth waiting out and a refusal is not", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        Response.json(
          {
            error:
              "FPL answered 429 with text/html: this deployment is being rate limited by FPL.",
            reason: "rate_limited",
          },
          { status: 502 },
        ),
      ),
    );

    render(<ManagerHistory entryId={212_279} />);

    expect(await screen.findByText(/should clear on its own/i)).toBeVisible();
  });

  it("falls back to unreachable when the body says nothing useful", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(new Response("", { status: 500 })),
    );

    render(<ManagerHistory entryId={212_279} />);

    expect(await screen.findByText(/could not reach FPL/i)).toBeVisible();
  });
});
