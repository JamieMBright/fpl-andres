const PRIVATE_KEYS = ["fpl-andres:last-team"] as const;
const PRIVATE_PREFIXES = [
  "fpl-andres:declared:",
  "fpl-andres:declared-squad:v1:",
  "fpl-andres:chips:",
  "fpl-andres:objective:v1:",
  "fpl-andres:team-state-overrides:v1:",
  "fpl-andres:public-team-state:v1:",
  "fpl-andres:public-team-state:v2:",
  "fpl-andres:manager-history:v1:",
  "fpl-andres:scorecard:v1:",
] as const;

function isPrivateKey(key: string): boolean {
  return (
    PRIVATE_KEYS.includes(key as (typeof PRIVATE_KEYS)[number]) ||
    PRIVATE_PREFIXES.some((prefix) => key.startsWith(prefix))
  );
}

/** Remove this app's manager/team records without touching theme or other apps. */
export function clearPrivateBrowserData(storage: Storage): number {
  const keys: string[] = [];
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index);
    if (key !== null && isPrivateKey(key)) keys.push(key);
  }
  for (const key of keys) storage.removeItem(key);
  return keys.length;
}
