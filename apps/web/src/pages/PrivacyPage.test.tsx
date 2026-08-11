import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import PrivacyPage from "./PrivacyPage";

describe("privacy and data controls", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("states what reaches the server and how long it survives", () => {
    render(
      <MemoryRouter>
        <PrivacyPage />
      </MemoryRouter>,
    );

    expect(
      screen.getByText(/no advertising or visitor analytics/i),
    ).toBeVisible();
    expect(
      screen.getByText(/Team ID, season, gameweek and swap/i),
    ).toBeVisible();
    expect(
      screen.getByText(/request diagnostics are deleted after 30 days/i),
    ).toBeVisible();
    expect(
      screen.getByText(/7 days after that gameweek's deadline/i),
    ).toBeVisible();
    expect(screen.getByText(/never read back into the plan/i)).toBeVisible();
  });

  it("requires confirmation before clearing local manager data", async () => {
    localStorage.setItem("fpl-andres:last-team", "42");
    localStorage.setItem("fpl-andres:theme", "light");
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <PrivacyPage />
      </MemoryRouter>,
    );

    await user.click(
      screen.getByRole("button", { name: "Clear Saved Team Data" }),
    );
    expect(
      screen.getByRole("alertdialog", { name: "Clear Saved Team Data?" }),
    ).toBeVisible();
    expect(localStorage.getItem("fpl-andres:last-team")).toBe("42");

    await user.click(
      screen.getByRole("button", { name: "Clear Team Data Now" }),
    );

    expect(localStorage.getItem("fpl-andres:last-team")).toBeNull();
    expect(localStorage.getItem("fpl-andres:theme")).toBe("light");
    expect(screen.getByRole("status")).toHaveTextContent(
      "Saved team data cleared",
    );
  });
});
