/**
 * The declared fifteen, packed small enough to live in the address bar.
 *
 * `localStorage` is where the squad belongs and where it stays: a Team ID is
 * public and enumerable, so a squad that came back from a server could have
 * been written by anybody who guessed the number. But mobile Safari clears
 * script-written storage after a week without a first-party visit, and a
 * manager who came back to check his plan found his fifteen gone.
 *
 * A URL survives that, because a bookmark, a history entry and a link sent to
 * yourself are not script-written storage. So the squad is written into the
 * query string as well. Nothing leaves the browser, and the manager gets a
 * link that restores his own claim on any device.
 *
 * Checksummed rather than trusted. A truncated paste that still decoded would
 * restore a squad the manager never picked, and he would have no way of
 * knowing: fifteen plausible names is exactly what a wrong answer looks like.
 */

import { SQUAD_SIZE } from "./declared-squad";

/** Bumped if the packing changes, so an old link fails rather than misreads. */
const VERSION = 1;

/** Two bytes an id, which covers every element id FPL has ever issued. */
const ID_BYTES = 2;
const MAX_ELEMENT_ID = 65_535;
const PAYLOAD_BYTES = 1 + SQUAD_SIZE * ID_BYTES;
const CODE_BYTES = PAYLOAD_BYTES + 2;

/** FNV-1a, folded to sixteen bits. Catches a truncation or a typo, not an attack. */
function checksum(bytes: Uint8Array): number {
  let hash = 0x811c9dc5;
  for (const byte of bytes) {
    hash = Math.imul(hash ^ byte, 0x01000193) >>> 0;
  }
  return ((hash >>> 16) ^ (hash & 0xffff)) & 0xffff;
}

function toBase64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

function fromBase64Url(code: string): Uint8Array | null {
  if (!/^[A-Za-z0-9_-]+$/.test(code)) return null;
  const padded = code.replace(/-/g, "+").replace(/_/g, "/");
  try {
    const binary = atob(padded);
    return Uint8Array.from(binary, (character) => character.charCodeAt(0));
  } catch {
    return null;
  }
}

/**
 * Fifteen element ids as one URL-safe token, or null when they are not a squad.
 *
 * Refuses rather than truncates: a code for fourteen players would decode into
 * a squad that breaks a rule nobody entered.
 */
export function encodeSquad(elementIds: readonly number[]): string | null {
  if (elementIds.length !== SQUAD_SIZE) return null;
  const bytes = new Uint8Array(CODE_BYTES);
  bytes[0] = VERSION;
  for (const [index, elementId] of elementIds.entries()) {
    if (
      !Number.isInteger(elementId) ||
      elementId < 1 ||
      elementId > MAX_ELEMENT_ID
    ) {
      return null;
    }
    const at = 1 + index * ID_BYTES;
    bytes[at] = (elementId >> 8) & 0xff;
    bytes[at + 1] = elementId & 0xff;
  }
  const sum = checksum(bytes.subarray(0, PAYLOAD_BYTES));
  bytes[PAYLOAD_BYTES] = (sum >> 8) & 0xff;
  bytes[PAYLOAD_BYTES + 1] = sum & 0xff;
  return toBase64Url(bytes);
}

/** The fifteen back, or null for anything that is not exactly this code. */
export function decodeSquad(code: string): number[] | null {
  const bytes = fromBase64Url(code);
  if (!bytes || bytes.length !== CODE_BYTES) return null;
  if (bytes[0] !== VERSION) return null;

  const sum = checksum(bytes.subarray(0, PAYLOAD_BYTES));
  const carried =
    ((bytes[PAYLOAD_BYTES] ?? 0) << 8) | (bytes[PAYLOAD_BYTES + 1] ?? 0);
  if (sum !== carried) return null;

  const elementIds: number[] = [];
  for (let index = 0; index < SQUAD_SIZE; index += 1) {
    const at = 1 + index * ID_BYTES;
    const elementId = ((bytes[at] ?? 0) << 8) | (bytes[at + 1] ?? 0);
    if (elementId < 1) return null;
    elementIds.push(elementId);
  }
  // A squad that names the same player twice is not a squad, and the rest of
  // the validation never sees this code if it is thrown out here.
  if (new Set(elementIds).size !== SQUAD_SIZE) return null;
  return elementIds;
}
