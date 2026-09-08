import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Gw1ReviewPitch } from "./Gw1ReviewPitch";
import { GW1_REVIEW } from "../state/gw1-review";

describe("Gw1ReviewPitch", () => {
  it("renders the observed team against the saved recommendation", () => {
    render(<Gw1ReviewPitch review={GW1_REVIEW} />);

    expect(
      screen.getByRole("heading", { name: "Gameweek 1, reviewed" }),
    ).toBeInTheDocument();
    expect(screen.getByText("56")).toBeInTheDocument();
    expect(screen.getByText(/13 left on the bench/i)).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(15);

    const raya = screen.getByRole("button", { name: /Raya/i });
    expect(raya).toHaveTextContent("6");
    expect(raya).toHaveTextContent("actual points");
    expect(raya).toHaveTextContent("C");

    const gabriel = screen.getByRole("button", { name: /Gabriel/i });
    expect(gabriel).toHaveTextContent("V");
  });

  it("keeps actual scores and preserves a detailed table fallback", () => {
    render(<Gw1ReviewPitch review={GW1_REVIEW} />);

    expect(
      screen.getByText(/What Andres recommended then/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/recommended, not submitted/i)).toBeInTheDocument();

    const table = screen.getByRole("table", { name: /GW1 review/i });
    const rayaRow = within(table).getByRole("row", { name: /Raya/i });
    expect(rayaRow).toHaveTextContent("6");
    expect(rayaRow).toHaveTextContent("6");
    expect(rayaRow).toHaveTextContent("recommended");
  });
});
