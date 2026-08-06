import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { TeamEntry } from "./SeasonPlanPage";

/**
 * The plan page, on the things a reader complained about.
 *
 * Only the form is rendered. Mounting the page itself draws thirty-eight
 * gameweek cards, which is slow enough to starve the worker pool and make
 * unrelated timing tests fail.
 *
 * The caveat checks read the source: the claim being made is about what is
 * written in the file, and counting five list items does not need a browser.
 */

const SOURCE = readFileSync(join(__dirname, "SeasonPlanPage.tsx"), "utf8");

function renderEntry(
  team: Parameters<typeof TeamEntry>[0]["team"],
  search = "",
  onChange = vi.fn(),
) {
  render(
    <MemoryRouter>
      <TeamEntry
        team={team}
        params={new URLSearchParams(search)}
        onChange={onChange}
      />
    </MemoryRouter>,
  );
  return onChange;
}

describe("the team ID form", () => {
  it("submits on Enter without reaching for the button", async () => {
    // Asked directly and worth pinning: implicit submission is a platform
    // behaviour that a stray preventDefault or a type="button" would remove,
    // and nothing here would have noticed.
    const user = userEvent.setup();
    const onChange = renderEntry({ status: "idle" });

    await user.type(screen.getByLabelText(/your team id/i), "212279{Enter}");

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0]?.[0].get("team")).toBe("212279");
  });

  it("keeps the button a submit button, which is what makes Enter work", () => {
    renderEntry({ status: "idle" });
    expect(
      screen.getByRole("button", { name: /plan my season/i }),
    ).toHaveAttribute("type", "submit");
  });

  it("offers a way to reach the team builder it names", () => {
    // The message said "build your fifteen on your team page" and linked to
    // nothing, which is a dead end in the state every manager sees preseason.
    renderEntry(
      { status: "failed", reason: "no_processed_event" },
      "team=212279",
    );

    expect(
      screen.getByRole("link", { name: /build your fifteen/i }),
    ).toHaveAttribute("href", "/team/212279");
  });

  it("offers no builder link for a failure a builder cannot fix", () => {
    renderEntry({ status: "failed", reason: "unreachable" }, "team=212279");
    expect(screen.queryByRole("link")).toBeNull();
  });
});

describe("the caveats", () => {
  const start = SOURCE.indexOf("What this plan cannot know");
  const list = SOURCE.slice(start, SOURCE.indexOf("</section>", start));

  it("counts the same number it lists", () => {
    // The heading said "Three" over a list of five for as long as the list had
    // been growing, because a number written in prose is checked by nothing.
    const items = list.match(/<li>/g)?.length ?? 0;
    const words: Record<number, string> = {
      3: "Three",
      4: "Four",
      5: "Five",
      6: "Six",
      7: "Seven",
    };
    expect(SOURCE).toContain(`const CAVEAT_COUNT = "${words[items] ?? "?"}"`);
  });

  it("quotes no player's projected points from memory", () => {
    // The last caveat quoted 4.40, 4.41 and 0.68 for two named players. All
    // three move on every backtest and none was read from the artifact.
    expect(list).not.toMatch(/\d\.\d\d/);
  });

  it("names whoever the plan actually leaves out", () => {
    expect(list).toContain("absentPremium");
    expect(list).not.toContain("Haaland");
  });
});

describe("what a gameweek card counts", () => {
  it("adds a third copy of the captain under Triple Captain", () => {
    // Bench Boost was handled and Triple Captain was not, so the one week the
    // chip is played was short by a whole captain.
    expect(SOURCE).toContain('chip?.chip === "Triple Captain" ? 2 : 1');
  });

  it("does not pass the mean off as a ceiling", () => {
    expect(SOURCE).not.toContain("ceiling: week.expected");
  });
});
