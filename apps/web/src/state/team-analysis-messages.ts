import type { TeamAnalysisState } from "./team-analysis";

/**
 * Every sentence the analysis panel can say, and nothing that renders one.
 *
 * Audit item #115. These were three functions inside a 910-line `App.tsx`,
 * which meant the wording of every refusal was only reachable by rendering the
 * route that produces it. They are the part most worth reading on their own:
 * each one is a promise to a manager about what the site does and does not
 * know, and a `Record` keyed by the reason means adding a failure mode without
 * writing its sentence is a type error rather than a blank panel.
 */

export function staleReason(
  reason: Extract<TeamAnalysisState, { status: "stale" }>["reason"],
): string {
  const reasons: Record<typeof reason, string> = {
    fpl_unreachable:
      "FPL is temporarily unreachable. The last verified state remains visible.",
    fpl_source_failed:
      "FPL returned a failed source response. The last verified state remains visible.",
    source_contract_failed:
      "FPL source fields changed or disagreed. The last verified state remains visible.",
    network_error:
      "The refresh request could not connect. The last verified state remains visible.",
    invalid_response:
      "The refresh response failed validation. The last verified state remains visible.",
  };
  return reasons[reason];
}

export function analysisAnnouncement(
  analysis: TeamAnalysisState,
  entryId: number,
): string {
  switch (analysis.status) {
    case "idle":
      return "";
    case "loading":
      return `Loading the verified snapshot for team ${entryId}.`;
    case "refreshing":
      return "Checking for a newer verified snapshot.";
    case "ready":
      return `Verified snapshot ready for team ${entryId}, gameweek ${analysis.state.event}.`;
    case "stale":
      return "Refresh failed. Showing the last verified snapshot, which may be out of date.";
    default:
      // Unavailable and degraded already render a heading and a next step; the
      // announcement names the outcome so it is not just a silent repaint.
      return `Analysis unavailable for team ${entryId}. ${terminalStateMessage(analysis).heading}.`;
  }
}

export function terminalStateMessage(
  analysis: Exclude<
    TeamAnalysisState,
    { status: "idle" | "loading" | "refreshing" | "ready" | "stale" }
  >,
) {
  if (analysis.status === "unavailable") {
    const unavailable = {
      entry_unavailable: {
        heading: "Team Not Available",
        nextStep:
          "Check the Team ID on your official FPL points-page URL, then try again.",
      },
      no_processed_event: {
        heading: "The season hasn\u2019t started",
        nextStep:
          "FPL wipes every squad between seasons, so there is nothing to read " +
          "until the first deadline passes. Your record is below in the " +
          "meantime, and it is the real thing rather than a placeholder.",
      },
      picks_unavailable: {
        heading: "Gameweek Picks Not Available",
        nextStep: `FPL has no public picks for Gameweek ${analysis.event ?? "this event"}. Try again after processing completes.`,
      },
    }[analysis.reason];
    return {
      tone: "unavailable",
      title: "Public state unavailable",
      detail: "No squad snapshot has been inferred or substituted.",
      ...unavailable,
    };
  }

  const failure = {
    fpl_unreachable: {
      heading: "FPL Cannot Be Reached",
      nextStep: "Wait a moment, then retry the analysis.",
    },
    fpl_source_failed: {
      heading: "FPL Source Request Failed",
      nextStep:
        "Retry after FPL has recovered. No partial source data was used.",
    },
    source_contract_failed: {
      heading: "FPL Source Data Changed",
      nextStep:
        "Retry later while the source contract is reviewed. No incompatible data was used.",
    },
    network_error: {
      heading: "Network Request Failed",
      nextStep: "Check your connection, then retry the analysis.",
    },
    invalid_response: {
      heading: "Analysis Response Failed Validation",
      nextStep:
        "Retry later. No unvalidated response has been displayed or cached.",
    },
  }[analysis.reason];
  return {
    tone: "error",
    title: "No verified snapshot available",
    detail: "The analysis stopped instead of manufacturing team state.",
    ...failure,
  };
}
