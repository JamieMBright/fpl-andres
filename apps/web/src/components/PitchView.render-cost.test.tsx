import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PitchView } from "./PitchView";
import type { PublicTeamPick } from "@fpl-andres/contracts";

/**
 * Memoise pure leaf components so unrelated parent state changes do not
 * re-render the whole pitch or table. Measured, and declined.
 *
 * The re-render is real. The theme toggle lives in the application frame, so
 * flipping it re-renders every route below including all fifteen chips. But
 * "real" and "worth preventing" are different claims, and only one had been
 * checked.
 *
 * Measured here, in jsdom: 4.3 ms for a full re-render of the fifteen-chip
 * pitch with fresh props. jsdom is two to five times slower than a browser, so
 * a browser does it in one to two milliseconds. An animation frame is 16.7 ms.
 *
 * Memoising would also not bite. React charges for a comparison on every
 * render including the cheap ones, and `pick` is a fresh object identity each
 * time the parent re-derives its list, so a shallow memo on `PlayerChip` would
 * compare and then re-render anyway. Making it work would mean memoising the
 * derivation too, or writing a custom comparator -- more moving parts than the
 * thing costs.
 *
 * The bound below is the evidence for the decision, not a performance target.
 * It fails if the component grows into something worth revisiting.
 */

const POSITIONS = ["GKP", "DEF", "DEF", "MID", "FWD"] as const;

function pick(index: number): PublicTeamPick {
  return {
    elementId: 100 + index,
    squadPosition: index + 1,
    multiplier: index === 0 ? 2 : index > 10 ? 0 : 1,
    isCaptain: index === 0,
    isViceCaptain: index === 1,
    identity: {
      webName: `Player ${index}`,
      positionCode: POSITIONS[index % POSITIONS.length] ?? "MID",
      teamShortName: "ARS",
      priceTenths: 45 + index,
      code: 900_000 + index,
    },
  };
}

const PICKS = Array.from({ length: 15 }, (_, index) => pick(index));

function medianMilliseconds(work: () => void, samples: number): number {
  const timings: number[] = [];
  for (let index = 0; index < samples; index += 1) {
    const startedAt = performance.now();
    work();
    timings.push(performance.now() - startedAt);
  }
  timings.sort((one, other) => one - other);
  return timings[Math.floor(timings.length / 2)] ?? 0;
}

/** Fifteen bare elements: the floor cost of re-rendering a list this size. */
function Baseline({ picks }: { picks: PublicTeamPick[] }) {
  return (
    <div>
      {picks.map((entry) => (
        <div key={entry.elementId}>{entry.identity?.webName}</div>
      ))}
    </div>
  );
}

const baselineTree = render(<Baseline picks={PICKS} />);
const pitchTree = render(<PitchView picks={PICKS} />);

function rerenderBaseline(): void {
  baselineTree.rerender(<Baseline picks={[...PICKS]} />);
}

function rerenderPitch(): void {
  // A fresh array each time, which is what an unrelated parent state change
  // actually produces.
  pitchTree.rerender(<PitchView picks={[...PICKS]} />);
}

describe("cost of re-rendering the pitch", () => {
  it("is close enough to bare markup that memoising would not pay for itself", () => {
    // Measured against a baseline of the same number of trivial elements
    // rendered in the same run, not against a wall clock. An absolute bound
    // here would be a test of how busy the CPU is: the same code measures two
    // to three times slower inside a loaded parallel suite, and would fail on
    // a shared runner while passing locally.
    const baseline = medianMilliseconds(() => {
      rerenderBaseline();
    }, 25);
    const pitch = medianMilliseconds(() => {
      rerenderPitch();
    }, 25);

    expect(baseline).toBeGreaterThan(0);
    // Fifteen chips, each an inline SVG and four short lines of text, against
    // fifteen bare divs. On an idle machine the pitch is 4.3 ms and the ratio
    // is under 10. Whatever multiple it is, a re-render that finishes inside a
    // frame is one nobody can see, and memoising it costs a comparison on
    // every render plus a custom comparator -- `pick` is a fresh object each
    // time the parent re-derives its list, so a shallow memo would compare and
    // re-render anyway.
    expect(pitch / baseline).toBeLessThan(40);
  });

  it("renders every pick, so the measurement is of the whole pitch", () => {
    // Otherwise a component that quietly stopped rendering the bench would
    // measure faster and look like an improvement.
    const { container } = render(<PitchView picks={PICKS} />);
    expect(container.querySelectorAll(".pitch-chip")).toHaveLength(15);
  });
});
