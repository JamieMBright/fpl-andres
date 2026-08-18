import { describe, expect, it } from "vitest";

import { captainEvidence } from "./captain-evidence";

const significance = [
  {
    label: "form",
    weeks: 100,
    meanPoints: 6,
    improvement: 0.2,
    lower: -0.1,
    upper: 0.5,
    better: false,
  },
];

describe("honest captain evidence", () => {
  it("rejects old shortlist significance without the owned-XI scope", () => {
    expect(captainEvidence({ captainSignificance: significance })).toEqual({
      significance: [],
      seasons: [],
    });
  });

  it("accepts policies measured on model-owned legal elevens", () => {
    const seasons = [
      {
        season: "2025-26",
        ownedCaptainPolicies: [
          {
            label: "form",
            gameweeks: 100,
            meanChosenPoints: 6,
            meanReachableCeiling: 10,
            ownedSquadRegret: 4,
          },
        ],
      },
    ];

    expect(
      captainEvidence({
        captainEvidenceScope: "model_owned_xi",
        captainSignificance: significance,
        seasons,
      }),
    ).toEqual({ significance, seasons });
  });
});
