/**
 * Lazy routes that survive a deploy landing mid-session.
 *
 * A visitor holding an open tab has an `index.html` naming hashed chunks. Deploy
 * again and those files are gone, so the next route change throws
 * "Failed to fetch dynamically imported module" and the page dies on a fault
 * the visitor did nothing to cause and cannot act on.
 *
 * The fix is to reload once, which fetches the new document and its new chunk
 * names. Once, guarded in session storage, because a reload loop on a genuinely
 * missing chunk is worse than the error it replaces.
 */

import { lazy, type ComponentType } from "react";

const RELOAD_KEY = "fpl-andres:chunk-reload";

/** A failed dynamic import, as distinct from the module throwing on execution. */
function isChunkLoadFailure(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  return (
    /Failed to fetch dynamically imported module/i.test(error.message) ||
    /error loading dynamically imported module/i.test(error.message) ||
    /Importing a module script failed/i.test(error.message)
  );
}

export function lazyRoute<T extends ComponentType<unknown>>(
  load: () => Promise<{ default: T }>,
) {
  return lazy(async () => {
    try {
      const module = await load();
      // Reaching a route proves the current chunks resolve, so a later deploy
      // gets its own single reload rather than inheriting a spent one.
      sessionStorage.removeItem(RELOAD_KEY);
      return module;
    } catch (error) {
      if (!isChunkLoadFailure(error)) throw error;
      if (sessionStorage.getItem(RELOAD_KEY)) throw error;
      sessionStorage.setItem(RELOAD_KEY, "1");
      window.location.reload();
      // Never settles: the reload is already under way and resolving here
      // would flash an empty route first.
      return new Promise<{ default: T }>(() => {
        // Intentionally unresolved.
      });
    }
  });
}
