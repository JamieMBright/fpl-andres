/**
 * Writing a row to Supabase from a serverless handler.
 *
 * PostgREST over `fetch` rather than a client library: the Python side already
 * talks to the same endpoint the same way, and a serverless bundle is not the
 * place to carry a dependency for one insert.
 *
 * The secret never leaves this module. Both tables it writes are forced-RLS
 * with no policy, so `service_role` is the only role that can reach them and
 * the browser key could not do this even if it had it.
 */

const URL_ENV = "SUPABASE_URL";
const SECRET_ENV = "SUPABASE_SECRET_KEY";

export class SupabaseNotConfigured extends Error {
  constructor(missing: readonly string[]) {
    super(`missing environment variables: ${missing.join(", ")}`);
    this.name = "SupabaseNotConfigured";
  }
}

export interface SupabaseCredentials {
  url: string;
  secret: string;
}

export function readCredentials(
  environment: Record<string, string | undefined> = process.env,
): SupabaseCredentials {
  const url = environment[URL_ENV]?.trim();
  const secret = environment[SECRET_ENV]?.trim();
  const missing = [...(url ? [] : [URL_ENV]), ...(secret ? [] : [SECRET_ENV])];
  if (!url || !secret) throw new SupabaseNotConfigured(missing);
  return { url: url.replace(/\/+$/, ""), secret };
}

/**
 * Insert one row. Returns nothing on purpose: no caller needs the row back, and
 * `Prefer: return=minimal` keeps a table's contents out of a response body that
 * a browser can read.
 */
export async function insertRow(
  table: string,
  row: Record<string, unknown>,
  credentials: SupabaseCredentials,
  fetchApi: typeof fetch = fetch,
): Promise<void> {
  const response = await fetchApi(
    `${credentials.url}/rest/v1/${encodeURIComponent(table)}`,
    {
      method: "POST",
      headers: {
        apikey: credentials.secret,
        Authorization: `Bearer ${credentials.secret}`,
        "Content-Type": "application/json",
        Prefer: "return=minimal",
      },
      body: JSON.stringify(row),
    },
  );
  if (!response.ok) {
    // The body can echo the row, which is the manager's private team state, so
    // only the status travels.
    throw new Error(
      `supabase insert into ${table} returned ${response.status}`,
    );
  }
}
