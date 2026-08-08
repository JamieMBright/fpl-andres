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

export default defineConfig({
  plugins: [react(), apiRoutes()],
  test: {
    environment: "jsdom",
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    setupFiles: "./src/test/setup.ts",
    // Building a fresh jsdom and module registry per file dominated the run.
    // The suite cleans up after itself rather than relying on isolation, so it
    // was being paid for and not used.
    isolate: false,
  },
});
