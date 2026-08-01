import type { VercelRequest, VercelResponse } from "@vercel/node";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../../api/_lib/fpl-proxy.js", () => ({
  createFplProxyResponse: vi.fn(() => {
    throw new Error(
      "connect ECONNREFUSED 10.0.0.7:443 at /var/task/api/_lib/fpl-proxy.js:88",
    );
  }),
}));

vi.mock("../../../../api/_lib/team-public-state-response.js", () => ({
  createTeamPublicStateResponse: vi.fn(() => {
    throw new Error(
      "connect ECONNREFUSED 10.0.0.7:443 at /var/task/api/_lib/team.js:41",
    );
  }),
}));

const fplProxyHandler = (await import("../../../../api/fpl/[...path]")).default;
const teamPublicStateHandler = (await import("../../../../api/team/[id]"))
  .default;

const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

afterEach(() => {
  vi.restoreAllMocks();
});

function collect() {
  const headers = new Map<string, string>();
  const sent: { body?: Buffer; status?: number } = {};
  const response = {
    setHeader(name: string, value: string) {
      headers.set(name.toLowerCase(), value);
      return this;
    },
    status(status: number) {
      sent.status = status;
      return this;
    },
    send(body: Buffer) {
      sent.body = body;
      return this;
    },
  } as unknown as VercelResponse;
  return { headers, sent, response };
}

const FPL_REQUEST = {
  url: "/api/fpl/bootstrap-static/",
  method: "GET",
} as VercelRequest;
const TEAM_REQUEST = {
  query: { id: "123" },
  method: "GET",
} as unknown as VercelRequest;

describe("a crashed handler leaks nothing to the client", () => {
  it("the fpl proxy answers 502 with a request id and no debug header", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const { headers, sent, response } = collect();

    await fplProxyHandler(FPL_REQUEST, response);

    expect(sent.status).toBe(502);
    expect(headers.has("x-fpl-andres-debug")).toBe(false);
    expect(headers.get("x-fpl-andres-request-id")).toMatch(UUID);
  });

  it("the team handler answers 503 with a request id and no debug header", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const { headers, sent, response } = collect();

    await teamPublicStateHandler(TEAM_REQUEST, response);

    expect(sent.status).toBe(503);
    expect(headers.has("x-fpl-andres-debug")).toBe(false);
    expect(headers.get("x-fpl-andres-request-id")).toMatch(UUID);
  });

  it("no header carries the upstream host, errno or a stack path", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const { headers, response } = collect();

    await fplProxyHandler(FPL_REQUEST, response);

    for (const value of headers.values()) {
      expect(value).not.toContain("ECONNREFUSED");
      expect(value).not.toContain("10.0.0.7");
      expect(value).not.toContain("/var/task");
    }
  });

  it("no response body carries the detail either", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const { headers, sent, response } = collect();

    await fplProxyHandler(FPL_REQUEST, response);

    const body = JSON.parse(String(sent.body));
    expect(body.requestId).toBe(headers.get("x-fpl-andres-request-id"));
    expect(JSON.stringify(body)).not.toContain("ECONNREFUSED");
    expect(JSON.stringify(body)).not.toContain("/var/task");
  });

  it("logs the detail as structured JSON keyed by the same id", async () => {
    const logged = vi.spyOn(console, "error").mockImplementation(() => {});
    const { headers, response } = collect();

    await fplProxyHandler(FPL_REQUEST, response);

    const entry = JSON.parse(String(logged.mock.calls[0]?.[0]));
    expect(entry.requestId).toBe(headers.get("x-fpl-andres-request-id"));
    expect(entry.route).toBe("/api/fpl/*");
    expect(entry.status).toBe(502);
    expect(entry.message).toContain("ECONNREFUSED");
    expect(entry.stack).toContain("/var/task");
    expect(typeof entry.durationMs).toBe("number");
  });

  it("marks the failure no-store and nosniff", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const { headers, response } = collect();

    await fplProxyHandler(FPL_REQUEST, response);

    expect(headers.get("cache-control")).toBe("no-store");
    expect(headers.get("x-content-type-options")).toBe("nosniff");
  });

  it("mints a fresh id per failure so two reports cannot be conflated", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const first = collect();
    const second = collect();

    await fplProxyHandler(FPL_REQUEST, first.response);
    await fplProxyHandler(FPL_REQUEST, second.response);

    expect(first.headers.get("x-fpl-andres-request-id")).not.toBe(
      second.headers.get("x-fpl-andres-request-id"),
    );
  });
});
