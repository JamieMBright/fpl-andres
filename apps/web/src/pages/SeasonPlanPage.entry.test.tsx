import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { TeamEntry } from "./SeasonPlanPage";
import { FixtureEvidenceList } from "./SeasonPlanPage";

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
const STYLES = readFileSync(join(__dirname, "..", "styles.css"), "utf8");

function stepSource(step: string, nextStep?: string): string {
  const marker = `step="${step}"`;
  const markerAt = SOURCE.indexOf(marker);
  const start = SOURCE.lastIndexOf("<PlanStep", markerAt);
  const end =
    nextStep === undefined
      ? SOURCE.indexOf("</PlanStep>", markerAt)
      : SOURCE.lastIndexOf("<PlanStep", SOURCE.indexOf(`step="${nextStep}"`));
  return SOURCE.slice(start, end);
}

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
  it("offers previously declared team IDs from this browser", () => {
    window.localStorage.clear();
    window.localStorage.setItem("fpl-andres:last-team", "212279");
    window.localStorage.setItem("fpl-andres:declared-squad:v1:7654321:1", "{}");

    renderEntry({ status: "idle" });

    expect(screen.getByRole("combobox")).toHaveAttribute(
      "list",
      "plan-team-id-history",
    );
    const options = [
      ...document.querySelectorAll<HTMLOptionElement>(
        "#plan-team-id-history option",
      ),
    ];
    expect(options.map((option) => option.value)).toEqual([
      "212279",
      "7654321",
    ]);
    window.localStorage.clear();
  });

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
    expect(list).toContain("the most expensive player this plan never fields");
    expect(list).not.toContain("the most expensive player in the game");
  });

  it("uses the red signal treatment", () => {
    const start = STYLES.indexOf(".plan-caveats-disclosure {");
    const rule = STYLES.slice(start, STYLES.indexOf("}", start));
    expect(rule).toContain("--fa-signal-red");
  });
});

describe("the numbered Plan boxes", () => {
  it("starts every section collapsed", () => {
    expect(SOURCE).not.toContain("defaultOpen");
  });

  it("keeps manager and season content inside step one", () => {
    const step = stepSource("01", "02");
    for (const content of [
      "<TeamEntry",
      "<DeclaredSquadNote",
      "<AnalysisResult",
    ]) {
      expect(step).toContain(content);
    }
  });

  it("keeps the last gameweek inside step two", () => {
    const step = stepSource("02", "03");
    expect(step).toContain("<Scorecard");
    expect(step).toContain("<Gw1ReviewPitch");
    expect(step).toContain("<LiveSquad");
    expect(step).toContain("teamId === GW1_REVIEW_ENTRY_ID");
  });

  it("keeps objective context inside step three", () => {
    const step = stepSource("03", "04");
    expect(step).toContain("<RankObjectiveForm");
    expect(step).toContain("<MiniLeagueThreats");
  });

  it("keeps solve status and gameweeks inside step four", () => {
    const step = stepSource("04");
    expect(step).toContain("<ChipStrategy");
    expect(step).toContain('className="plan-preamble"');
    expect(step).toContain('className="plan-progress"');
    expect(step).toContain('className="plan-rail"');
    expect(step).toContain('className="plan-caveats-disclosure"');
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

  it("only badges rebuild chips after that gameweek was re-solved", () => {
    expect(SOURCE).toContain(
      "chipCallsByEvent(chipCalls, gameweeks, committedChip)",
    );
    expect(SOURCE).toContain('week.chip === "Free Hit"');
    expect(SOURCE).toContain('"temporary changes"');
    expect(SOURCE).toContain('week.chip === "Wildcard"');
    expect(SOURCE).toContain('"permanent changes"');
    expect(SOURCE).not.toContain("{week.transfersIn.length} free");
  });
});

describe("opening recommendations", () => {
  const step = stepSource("04");

  it("keeps the expanded opening title compact and accessible", () => {
    const start = STYLES.indexOf(
      ".opening-squad-fold .dossier-heading-compact h2",
    );
    const rule = STYLES.slice(start, STYLES.indexOf("}", start));
    expect(rule).toContain("font-size: 19px");
  });

  it("offers acceptance alongside keeping the declared fifteen", () => {
    expect(step).toContain("Use these free changes");
    expect(step).toContain("Keep my fifteen");
  });

  it("persists the solved fifteen as accepted and refreshes the live plan", () => {
    expect(step).toContain('decideOpening("accepted")');
    expect(SOURCE).toContain('decision === "accepted"');
    expect(SOURCE).toContain("[...opener.starters, ...opener.bench]");
    expect(SOURCE).toContain("{ openingDecision: decision }");
    expect(SOURCE).toContain("setDeclaredAt(Date.now())");
  });

  it("states that FPL cannot reveal pre-deadline squad edits", () => {
    expect(step).toContain("does not expose pre-deadline squads");
    expect(step).toContain("cannot be detected automatically");
  });
});

describe("fixture difficulty display", () => {
  it("keeps the easy and very-easy buckets visually distinct", () => {
    const first = STYLES.indexOf(".plan-fdr-1 {");
    const second = STYLES.indexOf(".plan-fdr-2 {");
    expect(first).toBeGreaterThan(-1);
    expect(second).toBeGreaterThan(-1);
    expect(STYLES.slice(first, STYLES.indexOf("}", first))).toContain(
      "background: var(--field-green)",
    );
    expect(STYLES.slice(second, STYLES.indexOf("}", second))).toContain(
      "color-mix",
    );
  });
});

describe("fixture evidence", () => {
  it("shows the exact market values and route adjustments used by the solver", () => {
    render(
      <FixtureEvidenceList
        evidence={{
          MCI: [
            {
              event: 1,
              opponent: "BOU",
              venue: "H",
              kickoff: "2026-08-23T13:00:00+00:00",
              expectedGoals: 2.4223,
              opponentExpectedGoals: 1.0571,
              cleanSheetProbability: 0.3475,
              adjustments: {
                attacking: 1.625,
                cleanSheet: 1.372,
                conceding: 0.709,
                saves: 0.709,
                defensiveContribution: 0.855,
              },
              difficulty: { raw: 1.2, summary: 1.2, clipped: false },
              source: "the-odds-api",
              updatedAt: "2026-08-18T00:04:25.601367+00:00",
              level: "observed",
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("MCI v BOU (H)")).toBeInTheDocument();
    expect(
      screen.getByText(/2\.42 xG · 1\.06 xGA · 34\.8% clean sheet/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Attack 1\.625× · Defence 1\.372× · Conceding 0\.709× · Saves 0\.709× · DefCon 0\.855×/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/the-odds-api/)).toBeInTheDocument();
  });

  it("names a bounded matchup instead of silently clipping its raw value", () => {
    render(
      <FixtureEvidenceList
        evidence={{
          ARS: [
            {
              event: 1,
              opponent: "COV",
              venue: "H",
              kickoff: null,
              expectedGoals: 3,
              opponentExpectedGoals: 0.4,
              cleanSheetProbability: 0.67,
              adjustments: {
                attacking: 2.1,
                cleanSheet: 2.2,
                conceding: 0.4,
                saves: 0.4,
                defensiveContribution: 0.7,
              },
              difficulty: { raw: -0.6, summary: 1, clipped: true },
              source: "example",
              updatedAt: null,
              level: "observed",
            },
          ],
        }}
      />,
    );

    expect(screen.getByText(/raw −0\.6, bounded to 1\.0/)).toBeInTheDocument();
  });
});
