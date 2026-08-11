import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import ThanksPage from "./ThanksPage";

function renderPage(entry = "/thanks") {
  render(
    <MemoryRouter initialEntries={[entry]}>
      <ThanksPage />
    </MemoryRouter>,
  );
}

describe("thank-you page", () => {
  it("is useful on a direct visit without implying a purchase", () => {
    renderPage();

    expect(screen.getByRole("heading", { name: "Thank you" })).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Plan my season" }),
    ).toHaveAttribute("href", "/plan");
    expect(
      screen.getByRole("link", { name: "Check the method" }),
    ).toHaveAttribute("href", "/methodology");
    expect(document.body).not.toHaveTextContent(
      /payment|purchase|subscription/i,
    );
    expect(document.querySelector('meta[name="robots"]')).toHaveAttribute(
      "content",
      "noindex, nofollow",
    );
    expect(document.querySelector('link[rel="canonical"]')).toBeNull();
    expect(document.title).toBe("Thank you · FPL Andres");
  });

  it("acknowledges a successful contact message", () => {
    renderPage("/thanks?from=contact");

    expect(screen.getByText("Your message is on its way.")).toBeVisible();
    expect(
      screen.getByText(/aim to reply within two working days/i),
    ).toBeVisible();
  });
});
