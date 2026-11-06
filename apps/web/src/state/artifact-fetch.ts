import { requireArtifactVersion } from "./artifact-version";

interface ArtifactDescriptor {
  name: string;
  schemaVersion: number;
  sha256: string;
}

const pending = new Map<string, Promise<unknown>>();

export function loadArtifact(
  url: string,
  descriptor: ArtifactDescriptor,
  fetcher: typeof fetch = fetch,
): Promise<unknown> {
  const key = `${url}:${descriptor.sha256}:${descriptor.schemaVersion}`;
  const existing = pending.get(key);
  if (existing) return existing;

  const request = (async () => {
    const response = await fetcher(url, {
      signal: AbortSignal.timeout(30_000),
    });
    if (!response.ok) {
      throw new Error(
        `${descriptor.name} could not load (HTTP ${response.status}).`,
      );
    }
    if (!response.headers.get("Content-Type")?.includes("application/json")) {
      throw new Error(`${descriptor.name} did not return JSON.`);
    }
    const bytes = await response.arrayBuffer();
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    const sha256 = Array.from(new Uint8Array(digest), (byte) =>
      byte.toString(16).padStart(2, "0"),
    ).join("");
    if (sha256 !== descriptor.sha256) {
      throw new Error(`${descriptor.name} failed its integrity check.`);
    }
    const document: unknown = JSON.parse(new TextDecoder().decode(bytes));
    requireArtifactVersion(descriptor.name, document, descriptor.schemaVersion);
    return document;
  })().catch((error: unknown) => {
    pending.delete(key);
    throw error;
  });

  pending.set(key, request);
  return request;
}
