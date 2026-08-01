import { PlayerPoolTable } from "../components/PlayerPoolTable";
import { RouteHeading } from "../components/RouteHeading";

export default function PlayerPoolPage() {
  return (
    <section className="text-page pool-page">
      <p className="eyebrow">The market</p>
      <RouteHeading>Everyone in the game, and what they cost.</RouteHeading>
      <PlayerPoolTable />
    </section>
  );
}
