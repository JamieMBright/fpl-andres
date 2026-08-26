import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { XStartCalibration } from "./XStartCalibration";

describe("XStartCalibration", () => {
  it("shows the shipped field's reliability failure and every club", () => {
    render(<XStartCalibration />);

    expect(
      screen.getByRole("heading", { name: "xStart reliability" }),
    ).toBeVisible();
    const highest = screen.getByText("0.9-1.0").closest('[role="listitem"]');
    expect(highest).not.toBeNull();
    expect(highest).toHaveTextContent("92% / 68%");
    expect(highest).toHaveTextContent("n=28");
    const table = screen.getByRole("table", { name: "xStart score by club" });
    expect(within(table).getAllByRole("row")).toHaveLength(21);
    expect(within(table).getByRole("row", { name: /LEE/i })).toHaveTextContent(
      "0.174",
    );
  });
});
