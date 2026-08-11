import { useEffect } from "react";

import { siteUrl } from "../site";

const SUFFIX = "FPL Andres";

interface DocumentMetadata {
  canonicalPath: string | null;
  robots?: "index, follow" | "noindex, nofollow";
}

interface ManagedElement<Element extends HTMLElement> {
  element: Element;
  created: boolean;
}

function metaElement(
  attribute: "name" | "property",
  value: string,
): ManagedElement<HTMLMetaElement> {
  const existing = document.querySelector<HTMLMetaElement>(
    `meta[${attribute}="${value}"]`,
  );
  if (existing) return { element: existing, created: false };

  const element = document.createElement("meta");
  element.setAttribute(attribute, value);
  document.head.append(element);
  return { element, created: true };
}

function canonicalElement(): ManagedElement<HTMLLinkElement> {
  const existing = document.querySelector<HTMLLinkElement>(
    'link[rel="canonical"]',
  );
  if (existing) return { element: existing, created: false };

  const element = document.createElement("link");
  element.rel = "canonical";
  document.head.append(element);
  return { element, created: true };
}

/**
 * Sets the document title and meta description for a route.
 *
 * Every page inherited the static head from index.html, so a shared link, a
 * bookmark and a browser tab all said the same thing regardless of what was on
 * screen. Restores the previous values on unmount so a route that does not set
 * them cannot inherit the last one's.
 */
export function useDocumentTitle(
  title: string,
  description: string,
  { canonicalPath, robots = "index, follow" }: DocumentMetadata,
): void {
  useEffect(() => {
    const previousTitle = document.title;
    const nextTitle = title === SUFFIX ? SUFFIX : `${title} · ${SUFFIX}`;
    const canonicalUrl = canonicalPath === null ? null : siteUrl(canonicalPath);
    const shareUrl = canonicalUrl ?? siteUrl("/");
    document.title = nextTitle;

    const values = [
      [metaElement("name", "description"), description],
      [metaElement("name", "robots"), robots],
      [metaElement("property", "og:title"), nextTitle],
      [metaElement("property", "og:description"), description],
      [metaElement("property", "og:url"), shareUrl],
      [metaElement("name", "twitter:title"), nextTitle],
      [metaElement("name", "twitter:description"), description],
    ] as const;
    const previousValues = values.map(([managed]) => managed.element.content);
    for (const [managed, content] of values) {
      managed.element.content = content;
    }

    const suppressedCanonical =
      canonicalUrl === null
        ? document.querySelector<HTMLLinkElement>('link[rel="canonical"]')
        : null;
    const suppressedParent = suppressedCanonical?.parentElement ?? null;
    suppressedCanonical?.remove();

    const canonical = canonicalUrl === null ? null : canonicalElement();
    const previousCanonical = canonical?.element.href;
    if (canonical && canonicalUrl) canonical.element.href = canonicalUrl;

    return () => {
      document.title = previousTitle;
      for (const [[managed], previous] of values.map(
        (value, index) => [value, previousValues[index]] as const,
      )) {
        if (managed.created) managed.element.remove();
        else if (previous !== undefined) managed.element.content = previous;
      }
      if (canonical?.created) canonical.element.remove();
      else if (canonical && previousCanonical !== undefined)
        canonical.element.href = previousCanonical;
      if (suppressedCanonical && suppressedParent)
        suppressedParent.append(suppressedCanonical);
    };
  }, [canonicalPath, description, robots, title]);
}
