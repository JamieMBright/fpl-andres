/**
 * What a player did, drawn rather than listed.
 *
 * A gameweek row reading "2 goals, 1 assist, 3 bonus" is a sentence a reader
 * has to parse. The same row as a ball, a ball, an A and a gold medal is read
 * at a glance and survives being small, which is what a fifteen-card squad
 * needs. Every mark is a block drawing in the teletext palette, on the same
 * integer grid as the shirts.
 *
 * Marks never carry meaning alone: each one has a title a screen reader gets,
 * and the card beside them prints the points.
 */

const BALL = "#f6f4ea";
const BALL_PANEL = "#0a0a0a";
const SHIELD = "#2ec9c0";
const ARM = "#e7f24a";
const STAR = "#e5a02a";
const LETTER = "#e6338c";
const MEDAL: Record<number, string> = {
  3: "#e5a02a",
  2: "#c9c9c9",
  1: "#b06a2c",
};

function Mark({
  children,
  title,
}: {
  readonly children: React.ReactNode;
  readonly title: string;
}) {
  return (
    <svg className="score-mark" role="img" viewBox="0 0 12 12">
      <title>{title}</title>
      {children}
    </svg>
  );
}

/** A goal. A ball drawn as a block circle with the panels cut out of it. */
export function GoalMark() {
  return (
    <Mark title="Goal">
      <rect fill={BALL} height={8} width={4} x={4} y={2} />
      <rect fill={BALL} height={4} width={8} x={2} y={4} />
      <rect fill={BALL_PANEL} height={2} width={2} x={5} y={5} />
      <rect fill={BALL_PANEL} height={1} width={1} x={3} y={3} />
      <rect fill={BALL_PANEL} height={1} width={1} x={8} y={3} />
      <rect fill={BALL_PANEL} height={1} width={1} x={3} y={8} />
      <rect fill={BALL_PANEL} height={1} width={1} x={8} y={8} />
    </Mark>
  );
}

/** An assist. The letter, built from the same blocks as everything else. */
export function AssistMark() {
  return (
    <Mark title="Assist">
      <rect fill={LETTER} height={2} width={4} x={4} y={1} />
      <rect fill={LETTER} height={8} width={2} x={2} y={3} />
      <rect fill={LETTER} height={8} width={2} x={8} y={3} />
      <rect fill={LETTER} height={2} width={4} x={4} y={5} />
    </Mark>
  );
}

/** A clean sheet. A shield, which is what a defence is. */
export function CleanSheetMark() {
  return (
    <Mark title="Clean sheet">
      <rect fill={SHIELD} height={5} width={10} x={1} y={1} />
      <rect fill={SHIELD} height={2} width={8} x={2} y={6} />
      <rect fill={SHIELD} height={2} width={4} x={4} y={8} />
      <rect fill={SHIELD} height={1} width={2} x={5} y={10} />
    </Mark>
  );
}

/** A defensive contribution. An arm, flexed. */
export function DefensiveMark() {
  return (
    <Mark title="Defensive contribution">
      <rect fill={ARM} height={3} width={5} x={1} y={2} />
      <rect fill={ARM} height={4} width={3} x={5} y={2} />
      <rect fill={ARM} height={5} width={3} x={7} y={5} />
      <rect fill={ARM} height={3} width={4} x={1} y={7} />
      <rect fill={ARM} height={2} width={2} x={4} y={8} />
    </Mark>
  );
}

/** Bonus. Gold, silver and bronze, because that is what three, two and one are. */
export function BonusMark({ bonus }: { readonly bonus: number }) {
  const metal = MEDAL[bonus] ?? MEDAL[1];
  const names: Record<number, string> = {
    3: "Three bonus points",
    2: "Two bonus points",
    1: "One bonus point",
  };
  return (
    <Mark title={names[bonus] ?? "Bonus"}>
      <rect fill={metal} height={3} width={2} x={3} y={0} />
      <rect fill={metal} height={3} width={2} x={7} y={0} />
      <rect fill={metal} height={2} width={4} x={4} y={4} />
      <rect fill={metal} height={4} width={8} x={2} y={6} />
      <rect fill={BALL_PANEL} height={2} width={2} x={5} y={7} />
    </Mark>
  );
}

/** A haul. The one mark that is about the size of the score, not its parts. */
export function HaulMark() {
  return (
    <Mark title="Haul">
      <rect fill={STAR} height={4} width={2} x={5} y={0} />
      <rect fill={STAR} height={2} width={12} x={0} y={4} />
      <rect fill={STAR} height={2} width={8} x={2} y={6} />
      <rect fill={STAR} height={2} width={2} x={2} y={8} />
      <rect fill={STAR} height={2} width={2} x={8} y={8} />
      <rect fill={STAR} height={2} width={2} x={0} y={10} />
      <rect fill={STAR} height={2} width={2} x={10} y={10} />
    </Mark>
  );
}

export interface ScoreLine {
  goals: number;
  assists: number;
  cleanSheets: number;
  defensiveContribution: boolean;
  bonus: number;
  /** Set where the score beat what was projected by enough to be a haul. */
  haul: boolean;
}

/**
 * One player's gameweek, as marks.
 *
 * Repeated events repeat the mark rather than carrying a count, because two
 * balls reads as two goals without anybody being told the convention. Above
 * three of anything that stops being true, so it caps and prints the number.
 */
export function ScoreMarks({ line }: { readonly line: ScoreLine }) {
  const goals = Math.min(line.goals, 3);
  const assists = Math.min(line.assists, 3);
  return (
    <span className="score-marks">
      {line.haul ? <HaulMark /> : null}
      {Array.from({ length: goals }, (_, index) => (
        <GoalMark key={`goal-${String(index)}`} />
      ))}
      {line.goals > 3 ? (
        <span className="score-marks-more">×{line.goals}</span>
      ) : null}
      {Array.from({ length: assists }, (_, index) => (
        <AssistMark key={`assist-${String(index)}`} />
      ))}
      {line.assists > 3 ? (
        <span className="score-marks-more">×{line.assists}</span>
      ) : null}
      {line.cleanSheets > 0 ? <CleanSheetMark /> : null}
      {line.defensiveContribution ? <DefensiveMark /> : null}
      {line.bonus > 0 ? <BonusMark bonus={line.bonus} /> : null}
    </span>
  );
}
