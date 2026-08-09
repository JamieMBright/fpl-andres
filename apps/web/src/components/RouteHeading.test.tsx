import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { RouteHeading } from "./RouteHeading";

/**
 * Focus follows a route change, not a query-string change.
 *
 * Every control on the analysis page writes its state to the URL, and each of
 * those pushes a history entry. Treating an entry as an arrival meant the
 * first click on a legend or a slider dragged the reader back to the top of a
 * page they were already reading.
 */

function App({ path }: { readonly path: string }) {
  return (
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<RouteHeading>Home</RouteHeading>} path="/" />
        <Route
          element={<RouteHeading>Analysis</RouteHeading>}
          path="/analysis"
        />
      </Routes>
    </MemoryRouter>
  );
}

describe("RouteHeading", () => {
  it("does not take focus on a first paint", () => {
    render(<App path="/" />);

    expect(screen.getByRole("heading", { name: "Home" })).not.toHaveFocus();
  });

  it("leaves focus alone when only the query string moves", () => {
    const { rerender } = render(<App path="/analysis" />);
    const heading = screen.getByRole("heading", { name: "Analysis" });

    rerender(<App path="/analysis?hl=CHE" />);

    expect(heading).not.toHaveFocus();
  });
});
