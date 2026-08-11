import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  createContactResponse,
  resetContactRateLimiter,
} from "../../../../api/_lib/contact-response";

const PRIVATE_DESTINATION = "private-inbox@example.invalid";
const VISITOR = "reader@example.invalid";
const MESSAGE = "The calibration table helped. I found one source mismatch.";
const ENV = {
  RESEND_API_KEY: "re_test_not_a_secret",
  CONTACT_FROM_EMAIL: "FPL Andres <post@example.invalid>",
  CONTACT_TO_EMAIL: PRIVATE_DESTINATION,
};

function request(
  body: unknown = {
    submissionId: "4f5bc9b8-f258-4b56-b95a-8745ff742b45",
    email: VISITOR,
    message: MESSAGE,
    website: "",
  },
  overrides: {
    method?: string;
    origin?: string | null;
    contentType?: string;
  } = {},
): Request {
  const method = overrides.method ?? "POST";
  const headers = new Headers();
  if (overrides.contentType !== "none") {
    headers.set("Content-Type", overrides.contentType ?? "application/json");
  }
  if (overrides.origin !== null) {
    headers.set("Origin", overrides.origin ?? "https://fpl-andres.vercel.app");
  }
  return new Request("https://fpl-andres.vercel.app/api/contact", {
    method,
    headers,
    ...(method === "GET" ? {} : { body: JSON.stringify(body) }),
  });
}

beforeEach(() => resetContactRateLimiter());
afterEach(() => vi.restoreAllMocks());

describe("contact response boundary", () => {
  it("sends one plain-text email without returning the destination", async () => {
    const send = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        Response.json({ id: "provider-id-must-stay-private" }, { status: 200 }),
      );

    const response = await createContactResponse(request(), {
      clientKey: "192.0.2.20",
      env: ENV,
      fetchApi: send,
    });

    expect(response.status).toBe(202);
    const responseText = await response.text();
    expect(JSON.parse(responseText)).toEqual({
      accepted: true,
      requestId: expect.any(String),
    });
    expect(send).toHaveBeenCalledTimes(1);
    const [url, init] = send.mock.calls[0]!;
    expect(url).toBe("https://api.resend.com/emails");
    expect(init?.headers).toMatchObject({
      Authorization: `Bearer ${ENV.RESEND_API_KEY}`,
      "Idempotency-Key": "contact/4f5bc9b8-f258-4b56-b95a-8745ff742b45",
    });
    const providerBody = JSON.parse(String(init?.body)) as Record<
      string,
      unknown
    >;
    expect(providerBody).toEqual({
      from: ENV.CONTACT_FROM_EMAIL,
      to: [PRIVATE_DESTINATION],
      reply_to: VISITOR,
      subject: "FPL Andres contact",
      text: MESSAGE,
    });
    expect(responseText).not.toContain(PRIVATE_DESTINATION);
  });

  it.each([
    [request({}, { method: "GET" }), 405, "method"],
    [request({}, { contentType: "text/plain" }), 415, "unsupported_media_type"],
    [request({}, { origin: null }), 403, "origin"],
    [request({}, { origin: "https://example.invalid" }), 403, "origin"],
  ])("rejects an invalid request boundary", async (input, status, reason) => {
    const response = await createContactResponse(input, {
      clientKey: "192.0.2.21",
      env: ENV,
      fetchApi: vi.fn<typeof fetch>(),
    });

    expect(response.status).toBe(status);
    await expect(response.json()).resolves.toMatchObject({ reason });
  });

  it("rejects the measured body over 20 KiB", async () => {
    const response = await createContactResponse(
      request({
        submissionId: "4f5bc9b8-f258-4b56-b95a-8745ff742b45",
        email: VISITOR,
        message: "x".repeat(21 * 1024),
        website: "",
      }),
      { clientKey: "192.0.2.22", env: ENV },
    );

    expect(response.status).toBe(413);
    await expect(response.json()).resolves.toMatchObject({
      reason: "payload_too_large",
    });
  });

  it("returns field paths without echoing invalid values", async () => {
    const response = await createContactResponse(
      request({
        submissionId: "not-a-uuid",
        email: "not-an-email",
        message: "short",
        website: "",
        to: PRIVATE_DESTINATION,
      }),
      { clientKey: "192.0.2.23", env: ENV },
    );
    const text = await response.text();

    expect(response.status).toBe(400);
    expect(text).toContain("submissionId");
    expect(text).not.toContain("not-an-email");
    expect(text).not.toContain(PRIVATE_DESTINATION);
  });

  it("silently accepts the honeypot without contacting Resend", async () => {
    const send = vi.fn<typeof fetch>();
    const response = await createContactResponse(
      request({
        submissionId: "4f5bc9b8-f258-4b56-b95a-8745ff742b45",
        email: VISITOR,
        message: MESSAGE,
        website: "https://spam.invalid",
      }),
      { clientKey: "192.0.2.24", env: ENV, fetchApi: send },
    );

    expect(response.status).toBe(202);
    expect(send).not.toHaveBeenCalled();
  });

  it("fails closed when server-only mail configuration is absent", async () => {
    const response = await createContactResponse(request(), {
      clientKey: "192.0.2.25",
      env: {},
      fetchApi: vi.fn<typeof fetch>(),
    });

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toMatchObject({
      accepted: false,
      reason: "unavailable",
    });
  });

  it("rate limits one client before contacting Resend", async () => {
    const send = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json({ id: "opaque" }));
    let response = new Response();
    for (let index = 0; index < 4; index += 1) {
      response = await createContactResponse(
        request({
          submissionId: crypto.randomUUID(),
          email: VISITOR,
          message: MESSAGE,
          website: "",
        }),
        { clientKey: "192.0.2.26", env: ENV, fetchApi: send },
      );
    }

    expect(response.status).toBe(429);
    expect(send).toHaveBeenCalledTimes(3);
  });

  it("logs only an opaque reason when the provider fails", async () => {
    const logged = vi.spyOn(console, "error").mockImplementation(() => {});
    const send = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(`Cannot send to ${PRIVATE_DESTINATION}: ${MESSAGE}`, {
        status: 403,
      }),
    );

    const response = await createContactResponse(request(), {
      clientKey: "192.0.2.27",
      env: ENV,
      fetchApi: send,
    });
    const responseText = await response.text();
    const logText = logged.mock.calls.flat().join(" ");

    expect(response.status).toBe(503);
    for (const leaked of [PRIVATE_DESTINATION, VISITOR, MESSAGE]) {
      expect(responseText).not.toContain(leaked);
      expect(logText).not.toContain(leaked);
    }
    expect(logText).toContain("provider_refused");
  });
});
