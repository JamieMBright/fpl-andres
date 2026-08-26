/**
 * The bound on every public FPL identifier this app will accept.
 *
 * Lived in `App.tsx` alongside eleven components, so anything
 * else needing it had to import the application root.
 *
 * FPL entry IDs are unsigned 32-bit. Beyond that a value is not a large team,
 * it is a typo or a probe, and either way there is nothing to look up.
 */
export const MAX_PUBLIC_ID = 4_294_967_295;

export function parseTeamId(value: string | undefined): number | null {
  if (!value || !/^[1-9]\d{0,9}$/.test(value)) return null;
  const parsed = Number(value);
  return parsed <= MAX_PUBLIC_ID ? parsed : null;
}
