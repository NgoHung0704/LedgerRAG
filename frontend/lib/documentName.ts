/** A document's name as it should read beside a claim.
 *
 *  The extension carries no meaning in the margin — every source here is a
 *  document — but a trailing reference number does: it is what tells two
 *  editions of the same fund factsheet apart, so it stays.
 */
export function shortName(filename: string): string {
  return filename.replace(/\.[a-z0-9]{2,4}$/i, "");
}
