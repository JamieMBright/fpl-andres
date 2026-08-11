import { useState } from "react";

import { CeefaxShirt } from "../components/CeefaxShirt";
import { PlayerAvatar } from "../components/PlayerAvatar";
import { RouteHeading } from "../components/RouteHeading";
import { signatureKey, TEAM_KITS } from "../kit/team-kits";
import { useDocumentTitle } from "../state/use-document-title";

/**
 * Every shirt on one page, for looking at.
 *
 * A renderer that quantises twenty kits into eight colours cannot be reviewed
 * one shirt at a time — the only question worth asking is whether any two are
 * indistinguishable, and that needs them side by side.
 */

const SAMPLE_PHOTOS = [
  { code: 118748, name: "Mohamed Salah", club: "LIV", squadNumber: 11 },
  { code: 154561, name: "David Raya", club: "ARS", squadNumber: 22 },
  { code: 99999999, name: "Nobody at all", club: "NEW", squadNumber: 9 },
  { code: 99999998, name: "Nobody, no club", club: null, squadNumber: null },
];

export default function KitPreviewPage() {
  const [numbers, setNumbers] = useState(true);

  useDocumentTitle(
    "Kit preview",
    "Every club shirt as a teletext block graphic, side by side.",
    { canonicalPath: null, robots: "noindex, nofollow" },
  );

  const collisions = new Map<string, string[]>();
  for (const kit of TEAM_KITS) {
    const key = signatureKey(kit);
    collisions.set(key, [...(collisions.get(key) ?? []), kit.shortName]);
  }
  const groups = [...collisions.values()].filter((clubs) => clubs.length > 1);
  const clashing = new Set(groups.flat());

  return (
    <section className="kit-preview" aria-label="Kit preview">
      <div className="section-index" aria-hidden="true">
        QA / KITS
      </div>

      <RouteHeading>Kits</RouteHeading>

      <p className="lede">
        Teletext had eight colours and no anti-aliasing. Every shirt below is
        snapped to that palette by nearest RGB distance, which is perceptually
        the wrong metric and historically the right one — the point is to look
        like a machine from 1974 quantising a photograph.
      </p>

      <p className="plan-honesty">
        {collisions.size} of {TEAM_KITS.length} clubs stay distinguishable.{" "}
        {groups.length} pairs render identically (
        {groups.map((clubs) => clubs.join(" and ")).join(", ")}
        ). Each wears a near-identical real kit, so the palette is reporting a
        genuine similarity rather than losing information — but it is why a
        shirt is never the only label on a player.
      </p>

      <label className="kit-toggle">
        <input
          checked={numbers}
          onChange={(event) => setNumbers(event.target.checked)}
          type="checkbox"
        />
        Squad numbers
      </label>

      <ul className="kit-grid">
        {TEAM_KITS.map((kit, index) => (
          <li key={kit.code}>
            <CeefaxShirt
              className="kit-large"
              kit={kit}
              squadNumber={numbers ? (index % 11) + 1 : null}
            />
            <span className="kit-name">{kit.shortName}</span>
            <span className="kit-pattern mono">{kit.paint.base}</span>
            {clashing.has(kit.shortName) ? (
              <span className="kit-clash mono">clash</span>
            ) : null}
          </li>
        ))}
      </ul>

      <h2>Photographs</h2>
      <p className="lede">
        Lazy-loaded from the official media host. Where there is no photograph
        the player wears his club shirt with his number, which still says who he
        plays for — a silhouette only says the image failed. A missing photo
        returns 403 rather than 404, so the fallback reacts to the load failing
        rather than to a status code.
      </p>

      <ul className="kit-faces">
        {SAMPLE_PHOTOS.map((player) => (
          <li key={player.code}>
            <PlayerAvatar
              club={player.club}
              name={player.name}
              playerCode={player.code}
              squadNumber={player.squadNumber}
            />
            <span className="kit-name">{player.name}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
