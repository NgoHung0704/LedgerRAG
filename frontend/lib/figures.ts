/** Split a run of text into the figures it states and the words around them.
 *
 *  This used to be done by walking the DOM after render and replacing text
 *  nodes. That worked while an answer's paragraphs held nothing but text —
 *  React replaced the whole run and never noticed. Once the citations moved
 *  INTO the sentence, a paragraph held React-rendered buttons interleaved with
 *  rewritten text nodes, and the first re-render after a click threw
 *  "NotFoundError: The child can not be found in the parent". So the split
 *  happens here, before render, and React owns every node again.
 */

// a figure as these documents print them: 2,63 · 1 234,56 · 31,04 % · 12 €
// (the character class carries a non-breaking and a narrow no-break space,
// which is how French sets thousands)
const FIGURE = /\d[\d  .,\s]*\d\s*(?:%|€)?|\d\s*(?:%|€)?/g;

export type FigurePart = { text: string; figure: boolean };

export function splitFigures(text: string): FigurePart[] {
  const parts: FigurePart[] = [];
  let last = 0;
  FIGURE.lastIndex = 0;
  for (let m = FIGURE.exec(text); m; m = FIGURE.exec(text)) {
    const raw = m[0].trim();
    // a lone digit is a list marker or part of a date, not a figure the answer
    // is staking a claim on
    if (!raw || /^\d$/.test(raw)) continue;
    if (m.index > last) parts.push({ text: text.slice(last, m.index), figure: false });
    parts.push({ text: raw, figure: true });
    // whatever trim() dropped stays as ordinary text
    const tail = m[0].slice(raw.length);
    if (tail) parts.push({ text: tail, figure: false });
    last = m.index + m[0].length;
  }
  if (last === 0) return [{ text, figure: false }];
  if (last < text.length) parts.push({ text: text.slice(last), figure: false });
  return parts;
}
