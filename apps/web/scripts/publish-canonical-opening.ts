import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import {
  fixtureAtEvent,
  SEASON_DEADLINES,
  SEASON_EVENTS,
  SEASON_PLAYERS,
  solveSeason,
  startFromCodes,
  type SolverPlayer,
} from "../src/state/season-solver";
import inputs from "../src/data/season-inputs.json";

interface OpeningPick {
  code: number;
  name: string;
  position: string;
  club: string;
  priceTenths: number;
  record: number;
  adjusted: number;
  startRate: number;
  starter: boolean;
  run: number | null;
  ratedFixtures: number;
  fixtures: number;
}

interface OpeningArtifact {
  schemaVersion: number;
  generatedAt: string;
  basis: string;
  budgetTenths: number;
  spentTenths: number;
  expectedPoints: number;
  consideredPlayers: number;
  withoutRecord: number;
  unavailable: number;
  bitPart: number;
  startRateFloor: number;
  picks: OpeningPick[];
}

const OUTPUT = fileURLToPath(
  new URL("../src/data/opening-squad.json", import.meta.url),
);
const POSITION_ORDER = ["GKP", "DEF", "MID", "FWD"];
const MAX_PASSES = 15;

function round(value: number): number {
  return Math.round(value * 100) / 100;
}

function signature(players: readonly SolverPlayer[]): string {
  return players
    .map((player) => player.code)
    .sort((left, right) => left - right)
    .join(",");
}

const opening = JSON.parse(await readFile(OUTPUT, "utf8")) as OpeningArtifact;
const event = SEASON_EVENTS[0];
if (event !== 1) {
  throw new Error(
    `expected the published season to begin at GW1, got ${event}`,
  );
}

// GW1 picks are fixed once the deadline passes. Re-solving after the deadline
// would fail: publish_season_inputs sets rules.dataAvailableAt to now(), which
// the solver rejects when it is later than the (now-past) predictionCutoff.
const firstDeadline = (SEASON_DEADLINES as string[])[0];
if (firstDeadline && Date.now() > Date.parse(firstDeadline)) {
  console.log(
    `${OUTPUT} — GW1 deadline passed; canonical squad stands as committed`,
  );
  process.exit(0);
}

let codes = opening.picks.map((pick) => pick.code);
let bankTenths =
  opening.budgetTenths -
  SEASON_PLAYERS.filter((player) => codes.includes(player.code)).reduce(
    (total, player) => total + player.priceTenths,
    0,
  );
const seen = new Set<string>();
let solvedSquad: SolverPlayer[] | undefined;
let starters = new Set<number>();
let expectedPoints = 0;

for (let pass = 0; pass < MAX_PASSES; pass += 1) {
  const start = startFromCodes(codes, {
    bankTenths,
    availableFreeTransfers: 1,
    fromEvent: event,
  });
  if (!start)
    throw new Error(
      "opening seed contains a player outside season-inputs.json",
    );

  const opener = solveSeason(start).next().value;
  if (!opener) throw new Error("the browser solver did not return GW1");
  const current = [...opener.starters, ...opener.bench];
  if (current.length !== opening.picks.length) {
    throw new Error(
      `the browser solver returned ${current.length} players, expected 15`,
    );
  }

  const before = [...codes].sort((left, right) => left - right).join(",");
  const after = signature(current);
  if (before === after) {
    solvedSquad = current;
    starters = new Set(opener.starters.map((player) => player.code));
    expectedPoints = opener.starters.reduce(
      (total, player) => total + (opener.expected[String(player.code)] ?? 0),
      0,
    );
    break;
  }
  if (seen.has(after))
    throw new Error("the browser GW1 solve entered a squad cycle");
  seen.add(before);
  codes = current.map((player) => player.code);
  bankTenths = opener.bankAfterTenths;
}

if (!solvedSquad) {
  throw new Error(
    `the browser GW1 solve did not reach a fixpoint in ${MAX_PASSES} passes`,
  );
}

const picks = solvedSquad
  .map((player): OpeningPick => {
    const fixture = fixtureAtEvent(player, 0);
    const runFixtures = Array.from(
      { length: Math.min(5, SEASON_EVENTS.length) },
      (_, index) => fixtureAtEvent(player, index),
    );
    const fixtureCount = runFixtures.reduce(
      (total, eventFixture) => total + (eventFixture?.opponents.length ?? 0),
      0,
    );
    const runPoints = runFixtures.reduce(
      (total, eventFixture) => total + (eventFixture?.points ?? 0),
      0,
    );
    const run =
      fixtureCount > 0 && player.basePoints > 0
        ? round(runPoints / (player.basePoints * fixtureCount))
        : null;
    return {
      code: player.code,
      name: player.name,
      position: player.position,
      club: player.club,
      priceTenths: player.priceTenths,
      record: round(player.basePoints),
      adjusted: round(fixture?.points ?? 0),
      startRate: round(player.startRate),
      starter: starters.has(player.code),
      run,
      ratedFixtures: fixtureCount,
      fixtures: fixtureCount,
    };
  })
  .sort(
    (left, right) =>
      POSITION_ORDER.indexOf(left.position) -
        POSITION_ORDER.indexOf(right.position) ||
      Number(right.starter) - Number(left.starter) ||
      right.adjusted - left.adjusted,
  );

const payload: OpeningArtifact = {
  ...opening,
  generatedAt: new Date().toISOString(),
  spentTenths: solvedSquad.reduce(
    (total, player) => total + player.priceTenths,
    0,
  ),
  expectedPoints: round(expectedPoints),
  picks,
};

const withoutTimestamp = ({
  generatedAt: _generatedAt,
  ...artifact
}: OpeningArtifact) => artifact;
const unchanged =
  JSON.stringify(withoutTimestamp(opening)) ===
  JSON.stringify(withoutTimestamp(payload));
const alreadyFresh =
  Date.parse(opening.generatedAt) >= Date.parse(inputs.generatedAt);
if (unchanged && alreadyFresh) {
  console.log(`${OUTPUT} unchanged — canonical GW1 squad is already fresh`);
  process.exit(0);
}

await writeFile(OUTPUT, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
console.log(
  `wrote ${OUTPUT} — canonical GW1 squad after ${seen.size + 1} solve passes`,
);
