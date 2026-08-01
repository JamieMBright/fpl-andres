import meta from "../data/projections-meta.json";

/** Header fields only: the season label costs a kilobyte, not the whole squad. */
export const projectionSeason = meta.season;
export const projectionGeneratedAt = meta.generatedAt;
export const projectionThroughGameweek = meta.throughGameweek;
export const projectionBasis = meta.basis;
