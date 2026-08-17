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

  it("names the next kit without making the active colours look swapped", async () => {
    localStorage.setItem("fpl-andres:theme", "light");
    const user = userEvent.setup();
    renderFrame();

    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    const toggle = screen.getByRole("button", {
      name: "Switch to away kit",
    });

    await user.click(toggle);
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(toggle).toHaveAccessibleName("Switch to third kit");

    await user.click(toggle);
    expect(document.documentElement).toHaveAttribute("data-theme", "third");
    expect(toggle).toHaveAccessibleName("Switch to home kit");
  });
});
