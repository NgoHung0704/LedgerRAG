/** A document's name as it should read beside a claim.
 *
 *  The extension carries no meaning in the margin — every source here is a
 *  document — but a trailing reference number does: it is what tells two
 *  editions of the same fund factsheet apart, so it stays.
 */
export function shortName(filename: string): string {
  return filename.replace(/\.[a-z0-9]{2,4}$/i, "");
}

/** How the source reads inside the sentence it supports.
 *
 *  Clipped from the END, not the middle: "EPSENS FLEXI" is what a reader scans
 *  for, while the trailing reference number identifies nothing on its own — a
 *  middle ellipsis would have kept the digits and dropped the name. The full
 *  name stays on the element's title, and the bibliography under the answer
 *  carries it in full too.
 */
export function inlineLabel(filename: string, page: number, max = 22): string {
  const name = shortName(filename);
  const clipped = name.length > max ? `${name.slice(0, max - 1).trimEnd()}…` : name;
  return `${clipped} · p.${page}`;
}
