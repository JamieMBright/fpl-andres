import { PlayerPoolTable } from "../components/PlayerPoolTable";
import { RouteHeading } from "../components/RouteHeading";
import { TopPicks } from "../components/TopPicks";
import { useDocumentTitle } from "../state/use-document-title";

export default function PlayerPoolPage() {
  useDocumentTitle(
    "The player pool",
    "Every Fantasy Premier League player priced against their measured record from last season.",
    { canonicalPath: "/players" },
  );
  return (
    <section className="text-page pool-page">
      <p className="eyebrow">The market</p>
      <RouteHeading>Players</RouteHeading>
      <TopPicks />
      <PlayerPoolTable />
    </section>
  );
}
