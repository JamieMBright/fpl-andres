/**
 * Player headshots from the official FPL media host.
 *
 * The same public endpoint the FPL game itself serves photos from. Nothing is
 * fetched at build time and nothing is stored: the URL is derived from the
 * player code and handed to the browser, which caches it like any other image.
 *
 * ## Two things measured rather than assumed
 *
 * **A missing photo returns 403, not 404.** The bucket refuses to confirm what
 * does not exist. Any fallback keyed on 404 specifically would never fire, so
 * `PlayerAvatar` reacts to the `error` event and does not inspect the status.
 *
 * **Each photo is about 108 KB.** A fifteen-player pitch is therefore roughly
 * 1.6 MB of images. They are lazy-loaded and given explicit dimensions so the
 * layout does not move as they arrive.
 */

const HOST = "https://resources.premierleague.com";

/** The only size the FPL front end itself requests. */
const SIZE = "110x140";

export function getPlayerPhotoUrl(playerCode: number): string {
  if (!Number.isInteger(playerCode) || playerCode <= 0) {
    throw new Error(`${playerCode} is not a player code`);
  }
  return `${HOST}/premierleague/photos/players/${SIZE}/p${playerCode}.png`;
}

/**
 * Codes whose photo has already failed to load.
 *
 * In memory rather than `localStorage`, deliberately. The only thing worth
 * remembering is "this one 403s", and remembering that across sessions would
 * keep showing the silhouette for weeks after the Premier League published the
 * photo — for a player who has just transferred in, which is exactly when
 * someone wants to see their face.
 *
 * Bounded, because an unbounded set keyed by anything a page can influence is
 * a slow memory leak. Twenty times a squad is more misses than a session will
 * ever produce.
 */
const MAX_REMEMBERED_MISSES = 300;
const missing = new Set<number>();

export function markPhotoMissing(playerCode: number): void {
  if (missing.size >= MAX_REMEMBERED_MISSES) {
    // Oldest first: Set preserves insertion order.
    const oldest = missing.values().next();
    if (!oldest.done) missing.delete(oldest.value);
  }
  missing.add(playerCode);
}

export function isPhotoKnownMissing(playerCode: number): boolean {
  return missing.has(playerCode);
}

/** Test seam. Production has no reason to call this. */
export function forgetMissingPhotos(): void {
  missing.clear();
}
