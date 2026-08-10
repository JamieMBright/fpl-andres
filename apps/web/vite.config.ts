import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vitest/config";

type RouteHandler = (path: string, method: string) => Promise<Response>;

/**
 * Serve the deployed API routes from the dev server.
 *
 * Without this the dev server 404s every `/api` call, so the only way to see
 * the product working is to deploy it. The handlers are the same modules
 * Vercel runs, loaded through Vite's own transform pipeline at request time —
 * importing them from the config itself fails, because the config loader
 * cannot resolve the TypeScript workspace packages they depend on.
 */
function apiRoutes(): Plugin {
  return {
    name: "fpl-andres-dev-api",
    configureServer(server) {
      async function handlerFor(
        url: string,
      ): Promise<Promise<Response> | null> {
        const path = new URL(url, "http://localhost").pathname;
        const team = /^\/api\/team\/(\d+)\/?$/.exec(path);
        if (team) {
          const module = (await server.ssrLoadModule(
            "/../../api/_lib/team-public-state-response.ts",
          )) as {
            createTeamPublicStateResponse: (
              entryId: number,
              method: string,
            ) => Promise<Response>;
          };
          return module.createTeamPublicStateResponse(Number(team[1]), "GET");
        }
        if (path.startsWith("/api/fpl/")) {
          const module = (await server.ssrLoadModule(
            "/../../api/_lib/fpl-proxy.ts",
          )) as { createFplProxyResponse: RouteHandler };
          return module.createFplProxyResponse(path, "GET");
        }
        // Hand-rolled rather than loaded: `api/health.ts` is a Vercel handler
        // that writes to a response object, not one that returns a `Response`,
        // and dev had no route for it at all.
        if (path === "/api/health") {
          return Promise.resolve(
            Response.json(
              { status: "ok", service: "fpl-andres", revision: "local" },
              { headers: { "Cache-Control": "no-store" } },
            ),
          );
        }
        return null;
      }

      server.middlewares.use((request, response, next) => {
        const url = request.url ?? "";
        if (!url.startsWith("/api/") || request.method !== "GET") return next();

        void handlerFor(url)
          .then(async (pending) => {
            if (!pending) return next();
            const result = await pending;
            response.statusCode = result.status;
            result.headers.forEach((value, key) => {
              response.setHeader(key, value);
            });
            response.end(Buffer.from(await result.arrayBuffer()));
          })
          .catch(next);
      });
    },
  };
}

/**
 * The tests that actually need a browser.
 *
 * Everything under `components` renders React. The handful of state tests
 * listed after it reach for the real `localStorage` rather than passing a fake
 * one in. Every other test is arithmetic and has no use for a DOM, so building
 * one for it was the single largest cost in the suite.
 */
const DOM_TESTS = [
  "src/**/*.test.tsx",
  "src/state/manager-history-cache.test.ts",
  "src/state/manager-state-wiring.test.ts",
  "src/state/scorecard.test.ts",
  "src/state/team-analysis.test.ts",
  "src/state/team-state-overrides*.test.ts",
];

const NEVER = ["**/node_modules/**", "**/dist/**", "**/test-results/**"];

export default defineConfig({
  plugins: [react(), apiRoutes()],
  test: {
    // One fork per core is twenty-two jsdom documents on this machine, which
    // starves the pool into "failed to start forks worker" long before it runs
    // out of assertions to make.
    maxWorkers: 8,
    projects: [
      {
        extends: true,
        test: {
          name: "dom",
          environment: "jsdom",
          include: DOM_TESTS,
          exclude: NEVER,
          setupFiles: "./src/test/setup.ts",
        },
      },
      {
        extends: true,
        test: {
          name: "node",
          environment: "node",
          include: ["src/**/*.test.ts"],
          exclude: [...NEVER, ...DOM_TESTS],
        },
      },
    ],
  },
});
