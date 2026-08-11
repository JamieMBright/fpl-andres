export const SITE_URL = "https://fpl-andres.vercel.app";

export function siteUrl(path: string): string {
  return new URL(path, `${SITE_URL}/`).href;
}
