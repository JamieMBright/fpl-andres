import type { VercelRequest, VercelResponse } from "@vercel/node";

export default function healthHandler(
  _request: VercelRequest,
  response: VercelResponse,
) {
  response.setHeader("Cache-Control", "no-store");
  response.status(200).json({
    status: "ok",
    service: "fpl-andres",
    revision:
      process.env.VERCEL_GIT_COMMIT_SHA ??
      (process.env.VERCEL ? "unknown" : "local"),
  });
}
