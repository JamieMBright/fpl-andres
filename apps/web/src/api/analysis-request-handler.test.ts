import type { VercelRequest, VercelResponse } from "@vercel/node";
import { afterEach, describe, expect, it, vi } from "vitest";

const insertRow = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);

vi.mock("../../../../api/_lib/supabase-write.js", () => ({
  insertRow,
  readCredentials: () => ({
    url: "https://project.supabase.invalid",
    secret: "not-a-real-secret",
  }),
  SupabaseNotConfigured: class SupabaseNotConfigured extends Error {},
}));

const analysisRequestHandler = (
  await import("../../../../api/analysis-request")
).default;

const VALID_BODY = {
  season: "2026-27",
  entryId: 212_279,
  event: 1,
  transfer: {
    elementOut: 100,
    elementIn: 200,
    pointsCharged: 0,
  },
};

function request(
  overrides: Partial<VercelRequest> & {
    headers?: VercelRequest["headers"];
  } = {},
): VercelRequest {
  const { headers, ...requestOverrides } = overrides;
  return {
    method: "POST",
    body: VALID_BODY,
    headers: {
      "content-type": "application/json",
      "content-length": String(Buffer.byteLength(JSON.stringify(VALID_BODY))),
      origin: "https://fpl-andres.vercel.app",
      "x-forwarded-host": "fpl-andres.vercel.app",
      "x-forwarded-proto": "https",
      "x-vercel-forwarded-for": "192.0.2.80",
      ...headers,
    },
    ...requestOverrides,
  } as unknown as VercelRequest;
}

function response(): {
  vercel: VercelResponse;
  status: () => number;
  body: () => unknown;
} {
  let status = 0;
  let body: unknown;
  const vercel = {
    setHeader() {
      return vercel;
    },
    status(next: number) {
      status = next;
      return vercel;
    },
    json(next: unknown) {
      body = next;
      return vercel;
    },
  } as unknown as VercelResponse;
  return { vercel, status: () => status, body: () => body };
}

afterEach(() => {
  insertRow.mockClear();
});

describe("analysis request boundary", () => {
  it("requires JSON before reading the body", async () => {
    const current = response();

    await analysisRequestHandler(
      request({ headers: { "content-type": "text/plain" } }),
      current.vercel,
    );

    expect(current.status()).toBe(415);
    expect(current.body()).toMatchObject({ reason: "unsupported_media_type" });
    expect(insertRow).not.toHaveBeenCalled();
  });

  it("refuses an oversized body before any database access", async () => {
    const current = response();

    await analysisRequestHandler(
      request({ headers: { "content-length": "4097" } }),
      current.vercel,
    );

    expect(current.status()).toBe(413);
    expect(current.body()).toMatchObject({ reason: "payload_too_large" });
    expect(insertRow).not.toHaveBeenCalled();
  });

  it("requires Content-Length before reading the parsed body", async () => {
    const current = response();

    await analysisRequestHandler(
      request({
        headers: { "content-length": undefined },
      }),
      current.vercel,
    );

    expect(current.status()).toBe(411);
    expect(current.body()).toMatchObject({ reason: "length_required" });
    expect(insertRow).not.toHaveBeenCalled();
  });

  it("measures the parsed body after the framing check", async () => {
    const current = response();

    await analysisRequestHandler(
      request({
        body: { ...VALID_BODY, padding: "x".repeat(4096) },
        headers: { "content-length": "100" },
      }),
      current.vercel,
    );

    expect(current.status()).toBe(413);
    expect(insertRow).not.toHaveBeenCalled();
  });

  it("requires an Origin on this browser-only write route", async () => {
    const current = response();

    await analysisRequestHandler(
      request({ headers: { origin: undefined } }),
      current.vercel,
    );

    expect(current.status()).toBe(403);
    expect(insertRow).not.toHaveBeenCalled();
  });

  it("refuses a cross-origin request before any database access", async () => {
    const current = response();

    await analysisRequestHandler(
      request({ headers: { origin: "https://example.invalid" } }),
      current.vercel,
    );

    expect(current.status()).toBe(403);
    expect(current.body()).toMatchObject({ reason: "origin" });
    expect(insertRow).not.toHaveBeenCalled();
  });

  it("records a bounded same-origin JSON request", async () => {
    const current = response();

    await analysisRequestHandler(request(), current.vercel);

    expect(current.status()).toBe(202);
    expect(current.body()).toEqual({ recorded: true });
    expect(insertRow).toHaveBeenNthCalledWith(
      1,
      "analysis_requests",
      { season: "2026-27", entry_id: 212_279, event: 1 },
      expect.anything(),
    );
    expect(insertRow).toHaveBeenNthCalledWith(
      2,
      "declared_transfers",
      expect.objectContaining({ element_out: 100, element_in: 200 }),
      expect.anything(),
    );
  });
});
