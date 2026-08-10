const REPO = "https://github.com/NgoHung0704/LedgerRAG/blob/main";

/** The exact lines a citation claims, so a reader can check it in one click. */
export const githubUrl = (file: string, from: number, to: number): string =>
  `${REPO}/${file}#L${from}${to > from ? `-L${to}` : ""}`;
