export const LINE_HEIGHT = 16;
export const BOX_PADDING = 12;
export const LANE_PITCH = 20;
export const LABEL_CHARS = 18;

/** SVG <text> does not wrap. Break it here or it runs over its neighbour. */
export function wrapLabel(text: string, maxChars: number): string[] {
  const words = text.split(/\s+/);
  const lines: string[] = [];
  let line = "";
  for (const word of words) {
    const candidate = line ? `${line} ${word}` : word;
    if (candidate.length > maxChars && line) { lines.push(line); line = word; }
    else line = candidate;
  }
  if (line) lines.push(line);
  return lines;
}

export const boxHeight = (lines: string[]): number =>
  lines.length * LINE_HEIGHT + BOX_PADDING * 2;

/** Symmetric offsets so n parallel wires never share a path. */
export function laneOffsets(count: number): number[] {
  const mid = (count - 1) / 2;
  return Array.from({ length: count }, (_, i) => (i - mid) * LANE_PITCH);
}

/** A gap must fit the wires crossing it. Eleven will not live in 40px. */
export const columnGap = (maxLanes: number): number =>
  Math.max(150, maxLanes * LANE_PITCH + 56);

/** A box is sized for the LONGEST language, so switching never overflows it.
 *
 *  Every language the label carries, not a chosen two: French wraps onto more
 *  lines than Vietnamese or English for a fair number of these labels, and a
 *  height measured from two of the three spilled text out of its box. */
export const labelHeight = (label: Record<string, string>): number =>
  Math.max(...Object.values(label)
    .map((text) => boxHeight(wrapLabel(text, LABEL_CHARS))));

export const nodeHeight = (node: { label: Record<string, string> }): number =>
  labelHeight(node.label);

/** An orthogonal wire: out of the source, along its own lane, into the target.
 *
 *  Corners are rounded because a machine's wiring is bent, not mitred. Each
 *  corner's sweep follows the turn it actually makes - the first version used
 *  one sign for both corners and drew a wire that doubled back on itself. */
export function wirePath(
  x1: number, y1: number, turnX: number, x2: number, y2: number, r = 10,
): string {
  if (Math.abs(y1 - y2) < 1) return `M ${x1} ${y1} H ${x2}`;

  const sx = Math.sign(turnX - x1) || 1;   // out of the source
  const sy = Math.sign(y2 - y1);           // along the lane
  const ex = Math.sign(x2 - turnX) || 1;   // into the target

  const radius = Math.max(0, Math.min(
    r, Math.abs(turnX - x1), Math.abs(x2 - turnX), Math.abs(y2 - y1) / 2));

  const cornerIn = sx * sy > 0 ? 1 : 0;
  const cornerOut = sy * ex > 0 ? 0 : 1;

  return [
    `M ${x1} ${y1}`,
    `H ${turnX - sx * radius}`,
    `A ${radius} ${radius} 0 0 ${cornerIn} ${turnX} ${y1 + sy * radius}`,
    `V ${y2 - sy * radius}`,
    `A ${radius} ${radius} 0 0 ${cornerOut} ${turnX + ex * radius} ${y2}`,
    `H ${x2}`,
  ].join(" ");
}
