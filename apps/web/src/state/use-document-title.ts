import { useEffect } from "react";

const SUFFIX = "FPL Andres";

/**
 * Sets the document title and meta description for a route.
 *
 * Every page inherited the static head from index.html, so a shared link, a
 * bookmark and a browser tab all said the same thing regardless of what was on
 * screen. Restores the previous values on unmount so a route that does not set
 * them cannot inherit the last one's.
 */
export function useDocumentTitle(title: string, description?: string): void {
  useEffect(() => {
    const previousTitle = document.title;
    document.title = title === SUFFIX ? SUFFIX : `${title} · ${SUFFIX}`;

    const meta = document.querySelector<HTMLMetaElement>(
      'meta[name="description"]',
    );
    const previousDescription = meta?.content;
    if (meta && description) {
      meta.content = description;
    }

    return () => {
      document.title = previousTitle;
      if (meta && previousDescription !== undefined) {
        meta.content = previousDescription;
      }
    };
  }, [title, description]);
}
