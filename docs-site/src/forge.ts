// Where this repository is browsable, baked in at build time (see vite.config).
//
// Every citation on this page is a link into real lines of the repo. Pointed at
// the wrong forge they all still render and all go nowhere useful, so this is a
// build variable rather than a constant somebody has to remember to edit.
declare const __FORGE__: string;

/** The exact lines a citation claims, so a reader can check it in one click. */
export const sourceUrl = (file: string, from: number, to: number): string =>
  `${__FORGE__}/${file}#L${from}${to > from ? `-L${to}` : ""}`;
