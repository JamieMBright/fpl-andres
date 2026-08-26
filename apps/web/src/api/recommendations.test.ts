import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import type { VercelRequest, VercelResponse } from "@vercel/node";
import { describe, expect, it } from "vitest";

import latestHandler from "../../../../api/recommendations/latest";
import marketsHandler from "../../../../api/recommendations/markets";
import metaHandler from "../../../../api/recommendations/meta";
import xstartHandler from "../../../../api/recommendations/xstart";

const SOURCE = readFileSync(
  resolve(__dirname, "../../../../api/_lib/recommendations.ts"),
  "utf8",
);

describe("recommendation API deployment", () => {
  function responseBody(handler: typeof marketsHandler, address: string) {
    let status = 0;
    let body: unknown;
    handler(
      {
        method: "GET",
        headers: { "x-real-ip": address },
      } as unknown as VercelRequest,
      {
        setHeader() {
          return this;
        },
        status(value: number) {
          status = value;
          return this;
        },
        json(value: unknown) {
          body = value;
          return this;
        },
      } as unknown as VercelResponse,
    );
    expect(status).toBe(200);
    return body;
  }

  it("statically imports every artifact the serverless function serves", () => {
    expect(SOURCE).not.toContain("readFileSync");
    expect(SOURCE).not.toContain("process.cwd()");
    for (const artifact of [
      "season-plan.json",
      "season-inputs.json",
      "deadlines.json",
      "player-odds.json",
      "fixture-odds.json",
      "xstart-manual-priors.json",
      "xstart-validation.json",
    ]) {
      expect(SOURCE, artifact).toMatch(
        new RegExp(`import [^;]+${artifact.replace(".", "\\.")}`),
      );
    }
  });

  it("serves every endpoint from one traced model artifact", () => {
    const handlers = [
      latestHandler,
      marketsHandler,
      metaHandler,
      xstartHandler,
    ];
    const versions = handlers.map((handler, index) => {
      let status = 0;
      let body: unknown;
      const response = {
        setHeader() {
          return this;
        },
        status(value: number) {
          status = value;
          return this;
        },
        json(value: unknown) {
          body = value;
          return this;
        },
      } as unknown as VercelResponse;
      handler(
        {
          method: "GET",
          headers: { "x-real-ip": `192.0.2.${String(index + 1)}` },
        } as unknown as VercelRequest,
        response,
      );

      expect(status).toBe(200);
      expect(body).toMatchObject({ schemaVersion: 1 });
      return (body as { modelVersion?: unknown }).modelVersion;
    });

    expect(versions[0]).toEqual(expect.any(String));
    expect(new Set(versions).size).toBe(1);

    let latestBody: unknown;
    latestHandler(
      {
        method: "GET",
        headers: { "x-real-ip": "198.51.100.1" },
      } as unknown as VercelRequest,
      {
        setHeader() {
          return this;
        },
        status() {
          return this;
        },
        json(value: unknown) {
          latestBody = value;
          return this;
        },
      } as unknown as VercelResponse,
    );
    expect(latestBody).toMatchObject({
      captain: { position: expect.stringMatching(/^(MID|FWD)$/) },
      viceCaptain: { position: expect.stringMatching(/^(MID|FWD)$/) },
    });

    let xstartBody: unknown;
    xstartHandler(
      {
        method: "GET",
        headers: { "x-real-ip": "198.51.100.2" },
      } as unknown as VercelRequest,
      {
        setHeader() {
          return this;
        },
        status() {
          return this;
        },
        json(value: unknown) {
          xstartBody = value;
          return this;
        },
      } as unknown as VercelResponse,
    );
    expect(xstartBody).toMatchObject({
      shippedFieldValidation: {
        event: 1,
        field: "probabilitySixtyMinutesAsShipped",
        population: { count: 486, brier: 0.230679 },
      },
    });
    expect(SOURCE).toContain("XSTART_VALIDATION_SCHEMA_VERSION");
  });

  it("does not serve settled GW1 prices as GW2 market evidence", () => {
    const markets = responseBody(marketsHandler, "203.0.113.41") as {
      status: string;
      reason: string;
      event: number;
      fixtureOdds: { fixtures: unknown[] };
      playerOdds: { fixtures: unknown[]; players: unknown[] };
    };
    expect(markets).toMatchObject({
      status: "stale",
      reason: "post-fixture",
      event: 2,
    });
    expect(markets.fixtureOdds.fixtures).toEqual([]);
    expect(markets.playerOdds.fixtures.length).toBeGreaterThan(0);
    expect(markets.playerOdds.players).toEqual([]);

    const xstart = responseBody(xstartHandler, "203.0.113.42") as {
      teams: { players: { evidence: string }[] }[];
    };
    expect(
      xstart.teams
        .flatMap((team) => team.players)
        .some((player) => player.evidence === "market"),
    ).toBe(false);
  });
});
