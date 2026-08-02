import type { VercelRequest, VercelResponse } from "@vercel/node";

/**
 * Liveness, and which build answered.
 *
 * Audit item #80 asked whether the commit SHA and environment should be gated
 * behind an authenticated probe. Considered, and kept public, for a reason
 * specific to this project rather than a general one.
 *
 * The repository is public. The commit SHA names a commit anybody can already
 * read on GitHub, alongside every line of code it contains, so gating it hides
 * nothing -- it only makes it harder to answer "is the deploy the thing I
 * think it is" during an incident, which is the question this endpoint exists
 * for.
 *
 * That reasoning stops holding the moment the repository stops being public. A
 * test asserts the repository is described as public in SECURITY.md, so this
 * decision fails rather than rots if that changes.
 *
 * Nothing else is exposed: no environment variable names, no dependency
 * versions, no upstream hostnames, and no build path.
 */
export default function healthHandler(
  _request: VercelRequest,
  response: VercelResponse,
): void {
  response.setHeader("Cache-Control", "no-store");
  response.status(200).json({
    status: "ok",
    service: "fpl-andres",
    revision:
      process.env.VERCEL_GIT_COMMIT_SHA ??
      (process.env.VERCEL ? "unknown" : "local"),
  });
}
