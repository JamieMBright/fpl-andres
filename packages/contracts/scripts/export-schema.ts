import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { z } from "zod";

import {
  evidenceLevelSchema,
  fplEntrySchema,
  managerTeamPlayerSchema,
  publicTeamPickSchema,
  publicTeamStateSchema,
  queuedTransferSchema,
  sourceSnapshotSchema,
  teamStateOverridesSchema,
} from "../src/index";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const outputPath = resolve(packageRoot, "generated", "contracts.schema.json");

const schemaBundle = {
  $schema: "https://json-schema.org/draft/2020-12/schema",
  generatedFrom: "@fpl-andres/contracts",
  schemas: {
    EvidenceLevel: z.toJSONSchema(evidenceLevelSchema),
    FplEntry: z.toJSONSchema(fplEntrySchema),
    ManagerTeamPlayer: z.toJSONSchema(managerTeamPlayerSchema),
    PublicTeamPick: z.toJSONSchema(publicTeamPickSchema),
    PublicTeamState: z.toJSONSchema(publicTeamStateSchema),
    QueuedTransfer: z.toJSONSchema(queuedTransferSchema),
    SourceSnapshot: z.toJSONSchema(sourceSnapshotSchema),
    TeamStateOverrides: z.toJSONSchema(teamStateOverridesSchema),
  },
};
const serialized = `${JSON.stringify(schemaBundle, null, 2)}\n`;

if (process.argv.includes("--check")) {
  const current = await readFile(outputPath, "utf8").catch(() => "");
  if (current !== serialized) {
    console.error(
      "Generated contracts differ. Run `corepack pnpm contracts:generate` and commit the result.",
    );
    process.exitCode = 1;
  }
} else {
  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, serialized, "utf8");
}
