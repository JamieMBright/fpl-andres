import { TELETEXT_PALETTE } from "../kit/teletext";

/**
 * The mark. It was 43 lines of path data in the middle of the
 * application root, between the theme reducer and the page frame.
 *
 * Every colour comes from `TELETEXT_PALETTE` and nothing is drawn at partial
 * opacity, because Mode 7 had eight colours and no alpha channel at all. The
 * mark used to be near-misses of those eight — a pitch green, an off-white
 * plate, a violet bucket — plus two translucent details, which is a plausible
 * teletext look rather than a teletext one. The shadow and the rim highlight
 * are solid here for the same reason: a Ceefax page could not fade anything,
 * so it drew the darker or lighter colour instead.
 */
const { black, blue, green, white } = TELETEXT_PALETTE;

export function BielsaBucket() {
  return (
    <svg
      aria-hidden="true"
      className="brand-mark"
      viewBox="-6 -32 272 272"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* Grass. Wide enough that the bucket sits inside it rather than on it. */}
      <circle cx="130" cy="104" fill={green} r="128" />
      <ellipse cx="130" cy="186" fill={black} rx="104" ry="6" />
      <path
        d="M 84 30 Q 130 24 176 30 Q 188 30 192 42 C 214 82 226 128 226 168 Q 226 178 216 178 Q 130 184 44 178 Q 34 178 34 168 C 34 128 46 82 68 42 Q 72 30 84 30 Z"
        fill={blue}
      />
      <path
        d="M 88 32 Q 130 26 172 32"
        fill="none"
        stroke={white}
        strokeLinecap="round"
        strokeWidth="3"
      />
      <rect fill={white} height="36" rx="3" width="144" x="58" y="104" />
      <text
        fill={blue}
        fontFamily="'IBM Plex Mono', ui-monospace, monospace"
        fontSize="18"
        fontWeight="700"
        textAnchor="middle"
        x="130"
        y="128"
      >
        @fpl_andres
      </text>
    </svg>
  );
}
