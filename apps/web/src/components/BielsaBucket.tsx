/**
 * The mark. It was 43 lines of path data in the middle of the
 * application root, between the theme reducer and the page frame.
 */
export function BielsaBucket() {
  return (
    <svg
      aria-hidden="true"
      className="brand-mark"
      viewBox="0 0 260 200"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* Grass. The bucket needs something to stand on for the mark to read as
          a badge rather than a cut-out. */}
      <circle cx="130" cy="104" fill="#00a13e" r="98" />
      <ellipse
        cx="130"
        cy="186"
        fill="currentColor"
        opacity="0.25"
        rx="104"
        ry="6"
      />
      <path
        d="M 84 30 Q 130 24 176 30 Q 188 30 192 42 C 214 82 226 128 226 168 Q 226 178 216 178 Q 130 184 44 178 Q 34 178 34 168 C 34 128 46 82 68 42 Q 72 30 84 30 Z"
        fill="currentColor"
      />
      <path
        d="M 88 32 Q 130 26 172 32"
        fill="none"
        stroke="#fff"
        strokeLinecap="round"
        strokeOpacity="0.35"
        strokeWidth="1.4"
      />
      <rect fill="#f8f6ea" height="36" rx="3" width="144" x="58" y="104" />
      <text
        fill="#4a008e"
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
