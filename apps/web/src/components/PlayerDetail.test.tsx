import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { percent } from "../format";
import { allProjections } from "../state/squad-projection";
import { PlayerDetail } from "./PlayerDetail";

describe("PlayerDetail minutes bridge", () => {
  it("keeps true starts separate from reaching 60 minutes", () => {
    const player = allProjections()[0];
    expect(player).toBeDefined();
    if (!HTMLDialogElement.prototype.showModal) {
      HTMLDialogElement.prototype.showModal = vi.fn(function showModal(
        this: HTMLDialogElement,
      ) {
        this.setAttribute("open", "");
      });
    }

    render(
      <PlayerDetail
        onClose={() => undefined}
        player={{
          code: player!.code,
          name: player!.name,
          position: player!.position,
          club: "ARS",
          priceTenths: player!.priceTenths ?? 0,
        }}
      />,
    );

    const starts = screen.getByText("Starts").closest("div");
    const sixty = screen.getByText("Reaches 60").closest("div");
    expect(starts).not.toBeNull();
    expect(sixty).not.toBeNull();
    expect(within(starts!).getByRole("term")).toHaveTextContent("Starts");
    expect(starts).toHaveTextContent(
      player!.probabilityStartModel === undefined
        ? "—"
        : percent.format(player!.probabilityStartModel),
    );
    expect(sixty).toHaveTextContent(
      percent.format(
        player!.probabilitySixtyMinutes ?? player!.probabilityStart,
      ),
    );
  });
});
