import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import AboutPage from "./AboutPage";
import ThanksPage from "./ThanksPage";

function LocationProbe() {
  const location = useLocation();
  return (
    <output aria-label="Current location">
      {location.pathname}
      {location.search}
    </output>
  );
}

function draw() {
  return render(
    <MemoryRouter initialEntries={["/about"]}>
      <Routes>
        <Route path="/about" element={<AboutPage />} />
        <Route path="/thanks" element={<ThanksPage />} />
      </Routes>
      <LocationProbe />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("About contact form", () => {
  it("focuses the first invalid field before sending", async () => {
    const user = userEvent.setup();
    const send = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", send);
    draw();

    await user.type(screen.getByLabelText("Your email"), "reader@example.com");
    await user.type(screen.getByLabelText("Message"), "Too short");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(screen.getByLabelText("Message")).toHaveFocus();
    expect(screen.getByText(/at least 20 characters/i)).toBeVisible();
    expect(send).not.toHaveBeenCalled();
  });

  it("preserves the message after a failed delivery", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(Response.json({ accepted: false }, { status: 503 })),
    );
    draw();

    const email = screen.getByLabelText("Your email");
    const message = screen.getByLabelText("Message");
    await user.type(email, "reader@example.com");
    await user.type(message, "This should remain if the mail provider fails.");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(await screen.findByText(/did not send/i)).toBeVisible();
    expect(email).toHaveValue("reader@example.com");
    expect(message).toHaveValue(
      "This should remain if the mail provider fails.",
    );
  });

  it("opens the thank-you route only after the server accepts it", async () => {
    const user = userEvent.setup();
    const send = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        Response.json(
          { accepted: true, requestId: crypto.randomUUID() },
          { status: 202 },
        ),
      );
    vi.stubGlobal("fetch", send);
    draw();

    const email = screen.getByLabelText("Your email");
    const message = screen.getByLabelText("Message");
    await user.type(email, "reader@example.com");
    await user.type(
      message,
      "This is long enough to be a useful contact message.",
    );
    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(await screen.findByLabelText("Current location")).toHaveTextContent(
      "/thanks?from=contact",
    );
    expect(
      await screen.findByRole("heading", { name: "Thank you" }),
    ).toBeVisible();
    expect(document.querySelector('link[rel="canonical"]')).toBeNull();
    expect(document.querySelector('meta[name="robots"]')).toHaveAttribute(
      "content",
      "noindex, nofollow",
    );
    expect(email).toHaveValue("");
    expect(message).toHaveValue("");
    const [, init] = send.mock.calls[0]!;
    const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
    expect(body).toMatchObject({
      email: "reader@example.com",
      message: "This is long enough to be a useful contact message.",
      website: "",
    });
    expect(body.submissionId).toEqual(expect.any(String));
    expect(JSON.stringify(body)).not.toContain("fpl.andres.socials@gmail.com");
  });
});
