export const LINE_HEIGHT = 16;
export const BOX_PADDING = 12;
export const LANE_PITCH = 24;
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

/** Symmetric offsets so n parallel edges never share a path. */
export function laneOffsets(count: number): number[] {
  const mid = (count - 1) / 2;
  return Array.from({ length: count }, (_, i) => (i - mid) * LANE_PITCH);
}

/** A column gap must fit the lines crossing it. Five will not live in 40px. */
export const columnGap = (maxLanes: number): number =>
  Math.max(160, maxLanes * LANE_PITCH + 80);

/** A node is sized for the LONGER language, so switching never overflows it. */
export const nodeHeight = (node: { label: { vi: string; en: string } }): number =>
  Math.max(boxHeight(wrapLabel(node.label.vi, LABEL_CHARS)),
           boxHeight(wrapLabel(node.label.en, LABEL_CHARS)));
