import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { ApplicationFrame } from "./ApplicationFrame";

function renderFrame() {
  const router = createMemoryRouter([
    {
      path: "/",
      element: <ApplicationFrame />,
      children: [{ index: true, element: <p>Home</p> }],
    },
  ]);
  render(<RouterProvider router={router} />);
}

describe("ApplicationFrame kit control", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.dataset.theme = "dark";
  });

  it("names the active kit and cycles Third, Home, Away", async () => {
    const user = userEvent.setup();
    renderFrame();

    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    const toggle = screen.getByRole("button", { name: "Third Kit" });

    await user.click(toggle);
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    expect(toggle).toHaveAccessibleName("Home Kit");

    await user.click(toggle);
    expect(document.documentElement).toHaveAttribute("data-theme", "away");
    expect(toggle).toHaveAccessibleName("Away Kit");

    await user.click(toggle);
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(toggle).toHaveAccessibleName("Third Kit");
  });

  it("migrates the old yellow and blue preference to Away Kit", () => {
    localStorage.setItem("fpl-andres:theme", "third");
    renderFrame();

    expect(document.documentElement).toHaveAttribute("data-theme", "away");
    expect(screen.getByRole("button", { name: "Away Kit" })).toBeVisible();
    expect(localStorage.getItem("fpl-andres:theme")).toBe("away");
  });
});
