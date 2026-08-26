import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Gw1ReviewPitch } from "./Gw1ReviewPitch";
import { GW1_REVIEW } from "../state/gw1-review";

describe("Gw1ReviewPitch", () => {
  it("renders the observed team against frozen event-specific xPts", () => {
    render(<Gw1ReviewPitch review={GW1_REVIEW} />);

    expect(
      screen.getByRole("heading", { name: "Gameweek 1, reviewed" }),
    ).toBeInTheDocument();
    expect(screen.getByText("56")).toBeInTheDocument();
    expect(screen.getByText(/13 left on the bench/i)).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(15);

    const raya = screen.getByRole("button", { name: /Raya/i });
    expect(raya).toHaveTextContent("6");
    expect(raya).toHaveTextContent("5.9 xPts");
    expect(raya).toHaveTextContent("as projected");
    expect(raya).toHaveTextContent("C");

    const gabriel = screen.getByRole("button", { name: /Gabriel/i });
    expect(gabriel).toHaveTextContent("V");
  });

  it("grades raw points and preserves a detailed table fallback", () => {
    render(<Gw1ReviewPitch review={GW1_REVIEW} />);

    expect(screen.getAllByRole("button", { name: /haul$/i })).toHaveLength(3);
    expect(screen.getAllByRole("button", { name: /above$/i })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: /below$/i })).toHaveLength(8);
    expect(
      screen.getAllByRole("button", { name: /as projected$/i }),
    ).toHaveLength(2);

    const table = screen.getByRole("table", { name: /GW1 review/i });
    const rayaRow = within(table).getByRole("row", { name: /Raya/i });
    expect(rayaRow).toHaveTextContent("6");
    expect(rayaRow).toHaveTextContent("5.91");
    expect(rayaRow).not.toHaveTextContent("12");
  });
});
