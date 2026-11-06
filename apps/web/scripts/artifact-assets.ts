import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { normalizePath, type Plugin } from "vite";

import {
  PROJECTIONS_SCHEMA_VERSION,
  SEASON_INPUTS_SCHEMA_VERSION,
  requireArtifactVersion,
} from "../src/state/artifact-version";

const WEB_ROOT = fileURLToPath(new URL("..", import.meta.url));
const PREFIX = "\0fpl-artifact:";
const ARTIFACTS = [
  { name: "season-inputs", schemaVersion: SEASON_INPUTS_SCHEMA_VERSION },
  { name: "projections", schemaVersion: PROJECTIONS_SCHEMA_VERSION },
];

export function artifactAssets(): Plugin {
  const documents = ARTIFACTS.map(({ name, schemaVersion }) => {
    const path = normalizePath(resolve(WEB_ROOT, `src/data/${name}.json`));
    const source = readFileSync(path);
    requireArtifactVersion(
      `${name}.json`,
      JSON.parse(source.toString()),
      schemaVersion,
    );
    const sha256 = createHash("sha256").update(source).digest("hex");
    return {
      path,
      source,
      fileName: `artifacts/${name}-${sha256}.json`,
      descriptor: { name: `${name}.json`, schemaVersion, sha256 },
    };
  });
  let building = false;

  return {
    name: "fpl-andres-complete-artifact-assets",
    enforce: "pre",
    configResolved(config) {
      building = config.command === "build";
    },
    async resolveId(source, importer, options) {
      if (options.ssr) return null;
      if (!/\/(season-inputs|projections)\.json$/.test(source)) return null;
      const resolved = await this.resolve(source, importer, { skipSelf: true });
      const document = documents.find(({ path }) => path === resolved?.id);
      return document ? `${PREFIX}${document.path}.js` : null;
    },
    load(id) {
      if (!id.startsWith(PREFIX)) return null;
      const document = documents.find(
        ({ path }) => id === `${PREFIX}${path}.js`,
      );
      if (!document) return null;
      this.addWatchFile(document.path);
      const url = building
        ? `import.meta.ROLLUP_FILE_URL_${this.emitFile({ type: "asset", fileName: document.fileName, source: document.source })}`
        : JSON.stringify(`/${document.fileName}`);
      const loader = normalizePath(
        resolve(WEB_ROOT, "src/state/artifact-fetch.ts"),
      );
      return `import { loadArtifact } from ${JSON.stringify(loader)};
export default await loadArtifact(${url}, ${JSON.stringify(document.descriptor)});`;
    },
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const path = new URL(request.url ?? "", "http://localhost").pathname;
        if (!path.startsWith("/artifacts/")) return next();
        const document = documents.find(
          ({ fileName }) => path === `/${fileName}`,
        );
        response.setHeader("Content-Type", "application/json; charset=utf-8");
        if (!document) {
          response.statusCode = 404;
          response.end(JSON.stringify({ error: "artifact_not_found" }));
          return;
        }
        response.setHeader(
          "Cache-Control",
          "public, max-age=31536000, immutable",
        );
        response.end(document.source);
      });
    },
    configurePreviewServer(server) {
      server.middlewares.use((request, response, next) => {
        const path = new URL(request.url ?? "", "http://localhost").pathname;
        if (!path.startsWith("/artifacts/")) return next();
        if (!documents.some(({ fileName }) => path === `/${fileName}`)) {
          response.statusCode = 404;
          response.setHeader("Content-Type", "application/json; charset=utf-8");
          response.end(JSON.stringify({ error: "artifact_not_found" }));
          return;
        }
        response.setHeader(
          "Cache-Control",
          "public, max-age=31536000, immutable",
        );
        next();
      });
    },
  };
}
