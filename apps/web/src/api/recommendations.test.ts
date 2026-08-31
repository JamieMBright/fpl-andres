import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import type { VercelRequest, VercelResponse } from "@vercel/node";
import { describe, expect, it } from "vitest";

import DEADLINES from "../data/deadlines.json";
import INPUTS from "../data/season-inputs.json";
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

  it("does not serve settled prices as the current gameweek's market evidence", () => {
    // The handler imports the shipped artifacts, so the odds it finds depend on
    // what has been ingested. Pinning "stale" pinned one afternoon: once real
    // odds for the current window landed, "ready" became the right answer and
    // the test failed on correct behaviour. What must hold on any data is that
    // nothing from a fixture already played is served as evidence for the round
    // still to come, and that an empty window says so rather than staying quiet.
    const markets = responseBody(marketsHandler, "203.0.113.41") as {
      status: string;
      reason: string | null;
      event: number | null;
      fixtureOdds: { fixtures: { kickoff: string }[] };
      playerOdds: {
        fixtures: { kickoff: string }[];
        players: { kickoff: string }[];
      };
    };

    const upcoming = [...DEADLINES.deadlines]
      .filter((row) => !row.finished)
      .sort(
        (left, right) => Date.parse(left.deadline) - Date.parse(right.deadline),
      );
    const current = upcoming[0];
    const following = upcoming.find((row) => row.event > (current?.event ?? 0));
    expect(current).toBeDefined();
    expect(markets.event).toBe(current!.event);

    const inWindow = (kickoff: string) =>
      Date.parse(kickoff) > Date.parse(current!.deadline) &&
      (following === undefined ||
        Date.parse(kickoff) < Date.parse(following.deadline));

    for (const fixture of markets.fixtureOdds.fixtures) {
      expect(inWindow(fixture.kickoff), fixture.kickoff).toBe(true);
    }
    for (const player of markets.playerOdds.players) {
      expect(inWindow(player.kickoff), player.kickoff).toBe(true);
    }

    const ready = markets.fixtureOdds.fixtures.length > 0;
    expect(markets.status).toBe(ready ? "ready" : "stale");
    expect(markets.reason).toBe(ready ? null : "post-fixture");

    // Market evidence on a player is only honest while a bookmaker is still
    // quoting him for the round ahead, or his last quote was carried forward.
    const xstart = responseBody(xstartHandler, "203.0.113.42") as {
      teams: { players: { evidence: string }[] }[];
    };
    const priced =
      markets.playerOdds.players.length > 0 ||
      Object.keys(INPUTS.marketCarry?.players ?? {}).length > 0;
    expect(
      xstart.teams
        .flatMap((team) => team.players)
        .some((player) => player.evidence === "market"),
    ).toBe(priced);
  });
});
