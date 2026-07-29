import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { routes } from "./App";

function renderApplication() {
  const router = createMemoryRouter(routes, { initialEntries: ["/"] });
  render(<RouterProvider router={router} />);
  return router;
}

describe("team analysis entry", () => {
  it("opens analysis for a valid FPL team ID", async () => {
    const user = userEvent.setup();
    renderApplication();

    expect(
      screen.getByRole("heading", {
        name: "What should your next FPL move be?",
      }),
    ).not.toHaveFocus();
    await user.type(screen.getByLabelText("FPL team ID"), "123456");
    await user.click(screen.getByRole("button", { name: "Analyse team" }));

    const analysisHeading = await screen.findByRole("heading", {
      name: "Analysis for team 123456",
    });
    expect(analysisHeading).toBeInTheDocument();
    expect(analysisHeading).toHaveFocus();
  });

  it("explains why a malformed team ID cannot be analysed", async () => {
    const user = userEvent.setup();
    const router = renderApplication();

    await user.type(screen.getByLabelText("FPL team ID"), "abc");
    await user.click(screen.getByRole("button", { name: "Analyse team" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Enter a numeric FPL team ID.",
    );
    expect(screen.getByLabelText("FPL team ID")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(router.state.location.pathname).toBe("/");
  });
});
