const METAL = {
  1: "#e5a02a",
  2: "#c9c9c9",
  3: "#b06a2c",
} as const;

/** A teletext-block medal for first, second and third place. */
export function RankMedal({ rank }: { readonly rank: 1 | 2 | 3 }) {
  return (
    <svg
      aria-label={`Rank ${String(rank)}`}
      className={`rank-medal is-rank-${String(rank)}`}
      role="img"
      viewBox="0 0 18 20"
    >
      <title>Rank {rank}</title>
      <path d="M4 0h4v6H4zM10 0h4v6h-4z" fill={METAL[rank]} />
      <path d="M3 5h12v3H3zM1 8h16v10H1zM4 18h10v2H4z" fill={METAL[rank]} />
      <text
        dominantBaseline="middle"
        fill="#0a0a0a"
        fontFamily="monospace"
        fontSize="9"
        fontWeight="700"
        textAnchor="middle"
        x="9"
        y="13"
      >
        {rank}
      </text>
    </svg>
  );
}
