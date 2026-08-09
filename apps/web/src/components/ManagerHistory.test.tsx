import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ManagerHistory } from "./ManagerHistory";
import { saveManagerHistory } from "../state/manager-history-cache";

/**
 * A refused request is not a broken contract. The component used to hand null
 * to the parser whenever the response was not ok, so a rate-limited proxy read
 * back as an accusation against the source for something the source never did,
 * and one that points whoever reads it at the wrong repair.
 */

afterEach(() => {
  vi.restoreAllMocks();
});

beforeEach(() => {
  window.localStorage.clear();
});

describe("ManagerHistory", () => {
  it("blames the connection, not the payload, when the request is refused", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(new Response("", { status: 429 })),
    );

    render(<ManagerHistory entryId={212_279} fetchApi={globalThis.fetch} />);

    expect(await screen.findByText(/would not answer just now/i)).toBeVisible();
    expect(screen.queryByText(/shape I do not recognise/i)).toBeNull();
  });

  it("blames the payload only when the payload is genuinely unreadable", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(Response.json({ past: "not a list" })),
    );

    render(<ManagerHistory entryId={212_279} fetchApi={globalThis.fetch} />);

    expect(await screen.findByText(/shape I do not recognise/i)).toBeVisible();
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

    render(<ManagerHistory entryId={212_279} fetchApi={globalThis.fetch} />);

    expect(
      await screen.findByText(
        /FPL answered 403 with none: FPL refused the request from this deployment\./,
      ),
    ).toBeVisible();
    expect(screen.queryByText(/would not answer just now/i)).toBeNull();
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

    render(<ManagerHistory entryId={212_279} fetchApi={globalThis.fetch} />);

    expect(await screen.findByText(/should clear on its own/i)).toBeVisible();
  });

  it("falls back to unreachable when the body says nothing useful", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(new Response("", { status: 500 })),
    );

    render(<ManagerHistory entryId={212_279} fetchApi={globalThis.fetch} />);

    expect(await screen.findByText(/would not answer just now/i)).toBeVisible();
  });

  /**
   * The swept cohort was the other candidate for this and does not work: it
   * holds 2,207 managers filtered on a top-10,000 finish, and 212279's best is
   * 25,598. The reader's own last visit covers the reader.
   */
  it("shows the record from the reader's last visit when FPL refuses", async () => {
    const history = {
      past: [
        {
          season_name: "2020/21",
          total_points: 2457,
          rank: 25_598,
          rank_percentage: "0.3",
        },
      ],
    };
    saveManagerHistory(window.localStorage, 212_279, history);
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockImplementation(async () =>
        Response.json(
          {
            error: "FPL answered 403 with none: refused.",
            reason: "refused",
          },
          { status: 502 },
        ),
      ),
    );

    render(<ManagerHistory entryId={212_279} fetchApi={globalThis.fetch} />);

    expect(
      await screen.findByText(/record from your last visit/i),
    ).toBeVisible();
    expect(screen.getByText(/old rather than wrong/i)).toBeVisible();
    // The refusal is not shown instead of the record it was hiding.
    expect(screen.queryByText(/Retrying will not change it/i)).toBeNull();
  });

  it("keeps saying nothing when a refusal meets an empty store", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockImplementation(async () =>
        Response.json(
          {
            error: "FPL answered 403 with none: refused.",
            reason: "refused",
          },
          { status: 502 },
        ),
      ),
    );

    render(<ManagerHistory entryId={999_999} fetchApi={globalThis.fetch} />);

    expect(
      await screen.findByText(/Retrying will not change it/i),
    ).toBeVisible();
  });
});
