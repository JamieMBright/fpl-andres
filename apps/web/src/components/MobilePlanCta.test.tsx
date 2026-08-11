import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { MobilePlanCta } from "./MobilePlanCta";

function draw(pathname: string) {
  render(
    <MemoryRouter initialEntries={[pathname]}>
      <MobilePlanCta />
    </MemoryRouter>,
  );
}

describe("mobile plan CTA", () => {
  it("returns readers to the Team ID form from a content route", () => {
    draw("/results");

    expect(
      screen.getByRole("link", { name: "Analyse my squad" }),
    ).toHaveAttribute("href", "/#team-id");
  });

  it.each(["/", "/plan", "/team/212279", "/thanks"])(
    "does not duplicate the action on %s",
    (pathname) => {
      draw(pathname);
      expect(
        screen.queryByRole("link", { name: "Analyse my squad" }),
      ).not.toBeInTheDocument();
    },
  );
});
