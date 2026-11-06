import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { build, createServer, normalizePath } from "vite";
import { expect, it } from "vitest";

import { artifactAssets } from "../scripts/artifact-assets";

it("keeps server-side JSON imports local rather than fetching browser assets", async () => {
  const server = await createServer({
    configFile: false,
    root: resolve(__dirname, ".."),
    plugins: [artifactAssets()],
    server: { watch: null },
  });
  try {
    const module = await server.ssrLoadModule("/src/data/season-inputs.json");
    const source = JSON.parse(
      readFileSync(resolve(__dirname, "data/season-inputs.json"), "utf8"),
    );
    expect(JSON.stringify(module.default)).toBe(JSON.stringify(source));
  } finally {
    await server.close();
  }
});

it("emits complete content-addressed artifacts instead of embedding their data", async () => {
  const found = new Set<string>();
  await build({
    configFile: false,
    root: resolve(__dirname, ".."),
    logLevel: "silent",
    plugins: [
      artifactAssets(),
      {
        name: "verify-complete-artifacts",
        resolveId(source) {
          return source === "artifact-test-entry" ? source : null;
        },
        load(id) {
          if (id !== "artifact-test-entry") return null;
          return `import inputs from ${JSON.stringify(normalizePath(resolve(__dirname, "data/season-inputs.json")))};
import projections from ${JSON.stringify(normalizePath(resolve(__dirname, "data/projections.json")))};
export { inputs, projections };`;
        },
        generateBundle(_options, bundle) {
          for (const name of ["season-inputs", "projections"]) {
            const source = readFileSync(
              resolve(__dirname, `data/${name}.json`),
            );
            const digest = createHash("sha256").update(source).digest("hex");
            const path = `artifacts/${name}-${digest}.json`;
            const asset = bundle[path];
            expect(asset?.type).toBe("asset");
            if (asset?.type !== "asset") throw new Error(`Missing ${path}`);
            expect(Buffer.from(asset.source)).toEqual(source);
            found.add(name);
          }
          for (const output of Object.values(bundle)) {
            if (output.type !== "chunk") continue;
            expect(output.code).not.toContain('"weeklyFreeTransfers":');
            expect(output.code).toContain("loadArtifact");
          }
        },
      },
    ],
    build: {
      write: false,
      minify: false,
      target: "es2022",
      rollupOptions: {
        input: "artifact-test-entry",
        output: { inlineDynamicImports: true },
      },
    },
  });
  expect([...found].sort()).toEqual(["projections", "season-inputs"]);
}, 30_000);
